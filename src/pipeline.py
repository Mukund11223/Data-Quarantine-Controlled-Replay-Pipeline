import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .db import get_connection
from .validator import validate_record


def get_utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_pipeline(input_csv_path: str = "data/sample_orders.csv", run_id: str = None) -> dict:
    if not run_id:
        run_id = f"run_{get_utc_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    start_time = get_utc_now()
    conn = get_connection()

    # Log pipeline run start
    conn.execute(
        """
        INSERT INTO pipeline_runs (run_id, run_type, status, start_time, records_read, records_valid, records_quarantined)
        VALUES (?, 'STANDARD_INGEST', 'IN_PROGRESS', ?, 0, 0, 0)
        """,
        [run_id, start_time]
    )

    # Load reference customer sets for fast lookup
    cust_rows = conn.execute("SELECT customer_id, account_status FROM dim_customers").fetchall()
    valid_customers = {row[0] for row in cust_rows}
    active_customers = {row[0] for row in cust_rows if row[1] == "ACTIVE"}

    records_read = 0
    records_valid = 0
    records_quarantined = 0
    seen_batch_ids = set()

    valid_batch = []
    quarantine_batch = []

    try:
        with open(input_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records_read += 1
                is_valid, err_codes, err_msgs, stage = validate_record(
                    row, valid_customers, active_customers, seen_batch_ids
                )

                order_id = str(row.get("order_id", "")).strip()
                if order_id:
                    seen_batch_ids.add(order_id)

                if is_valid:
                    records_valid += 1
                    valid_batch.append((
                        order_id,
                        row["customer_id"].strip(),
                        row["order_date"].strip(),
                        float(row["total_amount"]),
                        row["currency"].strip().upper(),
                        row["payment_method"].strip(),
                        row["status"].strip(),
                        run_id,
                        get_utc_now()
                    ))
                else:
                    records_quarantined += 1
                    quarantine_id = f"q_{uuid.uuid4().hex}"
                    raw_payload = json.dumps(row)
                    quarantine_batch.append((
                        quarantine_id,
                        order_id if order_id else None,
                        raw_payload,
                        json.dumps(err_codes),
                        json.dumps(err_msgs),
                        stage,
                        input_csv_path,
                        run_id,
                        'PENDING',
                        None,
                        get_utc_now(),
                        get_utc_now()
                    ))

        # Perform database updates in a transaction
        conn.begin()

        # Idempotent load for valid records into fact_orders (Upsert via delete + insert or MERGE)
        for v in valid_batch:
            conn.execute(
                """
                INSERT INTO fact_orders (order_id, customer_id, order_date, total_amount, currency, payment_method, status, ingestion_run_id, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    order_date = EXCLUDED.order_date,
                    total_amount = EXCLUDED.total_amount,
                    currency = EXCLUDED.currency,
                    payment_method = EXCLUDED.payment_method,
                    status = EXCLUDED.status,
                    ingestion_run_id = EXCLUDED.ingestion_run_id,
                    ingested_at = EXCLUDED.ingested_at
                """,
                v
            )

        # Insert into quarantine_orders
        for q in quarantine_batch:
            conn.execute(
                """
                INSERT INTO quarantine_orders (quarantine_id, original_order_id, raw_payload, error_codes, error_messages, failed_check_stage, source_file, run_id, replay_status, replay_run_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                q
            )

        end_time = get_utc_now()
        status = "SUCCESS" if records_quarantined == 0 else "PARTIAL_SUCCESS"

        # Update pipeline run log
        conn.execute(
            """
            UPDATE pipeline_runs
            SET status = ?, end_time = ?, records_read = ?, records_valid = ?, records_quarantined = ?
            WHERE run_id = ?
            """,
            [status, end_time, records_read, records_valid, records_quarantined, run_id]
        )

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.execute(
            """
            UPDATE pipeline_runs
            SET status = 'FAILED', end_time = ?, error_summary = ?
            WHERE run_id = ?
            """,
            [get_utc_now(), str(e), run_id]
        )
        conn.commit()
        conn.close()
        raise e

    conn.close()

    summary = {
        "run_id": run_id,
        "status": status,
        "records_read": records_read,
        "records_valid": records_valid,
        "records_quarantined": records_quarantined,
        "input_file": input_csv_path
    }
    print(f"Pipeline Run Completed: {summary}")
    return summary


if __name__ == "__main__":
    run_pipeline()