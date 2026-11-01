import json
import uuid
from datetime import datetime, timezone
from .db import get_connection
from .validator import validate_record

def get_utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def run_replay(run_id: str = None) -> dict:
    if not run_id:
        run_id = f"replay_{get_utc_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    start_time = get_utc_now()
    conn = get_connection()

    # Log replay run start
    conn.execute(
        """
        INSERT INTO pipeline_runs (run_id, run_type, status, start_time, records_read, records_valid, records_quarantined, records_replayed)
        VALUES (?, 'CONTROLLED_REPLAY', 'IN_PROGRESS', ?, 0, 0, 0, 0)
        """,
        [run_id, start_time]
    )

    # Fetch all pending quarantined records
    pending_records = conn.execute(
        """
        SELECT quarantine_id, raw_payload FROM quarantine_orders WHERE replay_status = 'PENDING'
        """
    ).fetchall()

    if not pending_records:
        print("No pending quarantined records found to replay.")
        conn.execute(
            "UPDATE pipeline_runs SET status = 'SUCCESS', end_time = ? WHERE run_id = ?",
            [get_utc_now(), run_id]
        )
        conn.commit()
        conn.close()
        return {"run_id": run_id, "status": "SUCCESS", "records_replayed": 0}

    # Load reference customer sets
    cust_rows = conn.execute("SELECT customer_id, account_status FROM dim_customers").fetchall()
    valid_customers = {row[0] for row in cust_rows}
    active_customers = {row[0] for row in cust_rows if row[1] == "ACTIVE"}

    records_read = len(pending_records)
    records_replayed = 0
    records_still_quarantined = 0

    conn.begin()

    for quarantine_id, raw_payload_str in pending_records:
        record = json.loads(raw_payload_str)

        # In a real replay scenario, operators might patch fields or fix reference data.
        # Here we re-validate. If reference data (like customer) was added/activated or payload corrected, it passes.
        is_valid, err_codes, err_msgs, stage = validate_record(
            record, valid_customers, active_customers, seen_batch_ids=set()
        )

        if is_valid:
            records_replayed += 1
            order_id = str(record["order_id"]).strip()

            # Insert / Upsert into target fact_orders
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
                [
                    order_id,
                    record["customer_id"].strip(),
                    record["order_date"].strip(),
                    float(record["total_amount"]),
                    record["currency"].strip().upper(),
                    record["payment_method"].strip(),
                    record["status"].strip(),
                    run_id,
                    get_utc_now()
                ]
            )

            # Update quarantine record to REPLAYED
            conn.execute(
                """
                UPDATE quarantine_orders
                SET replay_status = 'REPLAYED', replay_run_id = ?, updated_at = ?
                WHERE quarantine_id = ?
                """,
                [run_id, get_utc_now(), quarantine_id]
            )
        else:
            records_still_quarantined += 1
            # Update error log on quarantine record
            conn.execute(
                """
                UPDATE quarantine_orders
                SET error_codes = ?, error_messages = ?, failed_check_stage = ?, updated_at = ?
                WHERE quarantine_id = ?
                """,
                [json.dumps(err_codes), json.dumps(err_msgs), stage, get_utc_now(), quarantine_id]
            )

    end_time = get_utc_now()
    conn.execute(
        """
        UPDATE pipeline_runs
        SET status = 'SUCCESS', end_time = ?, records_read = ?, records_valid = ?, records_quarantined = ?, records_replayed = ?
        WHERE run_id = ?
        """,
        [end_time, records_read, records_replayed, records_still_quarantined, records_replayed, run_id]
    )

    conn.commit()
    conn.close()

    summary = {
        "run_id": run_id,
        "status": "SUCCESS",
        "records_read": records_read,
        "records_replayed": records_replayed,
        "records_still_quarantined": records_still_quarantined
    }
    print(f"Replay Run Completed: {summary}")
    return summary

if __name__ == "__main__":
    run_replay()