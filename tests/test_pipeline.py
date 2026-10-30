import os
import pytest
from src.db import init_db, get_connection
from src.generator import generate_synthetic_data
from src.pipeline import run_pipeline
from src.replay import run_replay
from src.reconcile import run_reconciliation


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    # Clear tables before each test
    conn = get_connection()
    conn.execute("DELETE FROM fact_orders")
    conn.execute("DELETE FROM quarantine_orders")
    conn.execute("DELETE FROM pipeline_runs")
    conn.execute("DELETE FROM dim_customers")
    conn.close()


def test_happy_path_and_quarantine_routing():
    # Generate small dataset with fixed seed
    csv_path = generate_synthetic_data(num_records=200, seed=42, output_path="data/test_orders.csv")

    summary = run_pipeline(input_csv_path=csv_path, run_id="test_run_01")

    assert summary["records_read"] == 200
    assert summary["records_valid"] > 0
    assert summary["records_quarantined"] > 0

    conn = get_connection()
    valid_count = conn.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0]
    quarantine_count = conn.execute("SELECT COUNT(*) FROM quarantine_orders").fetchone()[0]
    conn.close()

    assert valid_count == summary["records_valid"]
    assert quarantine_count == summary["records_quarantined"]


def test_idempotent_ingestion():
    csv_path = generate_synthetic_data(num_records=50, seed=123, output_path="data/test_idempotent.csv")

    # Run pipeline twice with same input
    summary1 = run_pipeline(input_csv_path=csv_path, run_id="run_1")
    summary2 = run_pipeline(input_csv_path=csv_path, run_id="run_2")

    conn = get_connection()
    count_fact = conn.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0]
    conn.close()

    # Target table should not duplicate records due to upsert/idempotency
    assert count_fact == summary1["records_valid"]


def test_controlled_replay():
    csv_path = generate_synthetic_data(num_records=100, seed=99, output_path="data/test_replay.csv")
    run_pipeline(input_csv_path=csv_path, run_id="run_initial")

    conn = get_connection()
    pending_before = conn.execute("SELECT COUNT(*) FROM quarantine_orders WHERE replay_status = 'PENDING'").fetchone()[0]
    conn.close()

    if pending_before > 0:
        replay_summary = run_replay(run_id="replay_run_01")
        assert replay_summary["records_replayed"] >= 0

        conn = get_connection()
        pending_after = conn.execute("SELECT COUNT(*) FROM quarantine_orders WHERE replay_status = 'PENDING'").fetchone()[0]
        replayed_count = conn.execute("SELECT COUNT(*) FROM quarantine_orders WHERE replay_status = 'REPLAYED'").fetchone()[0]
        conn.close()

        assert pending_after < pending_before or pending_after == 0
        assert replayed_count == replay_summary["records_replayed"]


def test_reconciliation():
    csv_path = generate_synthetic_data(num_records=100, seed=77, output_path="data/test_recon.csv")
    run_pipeline(input_csv_path=csv_path, run_id="recon_run")

    recon = run_reconciliation()
    assert recon["reconciliation_passed"] is True