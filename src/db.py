import duckdb
import os
from pathlib import Path

DB_PATH = Path("data/pipeline.duckdb")

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    return conn

def init_db():
    conn = get_connection()

    # 1. Reference dimension table: customers
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_customers (
            customer_id VARCHAR PRIMARY KEY,
            customer_name VARCHAR NOT NULL,
            account_status VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)

    # 2. Target analytical table: fact_orders
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fact_orders (
            order_id VARCHAR PRIMARY KEY,
            customer_id VARCHAR NOT NULL,
            order_date TIMESTAMP NOT NULL,
            total_amount DECIMAL(12, 2) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            payment_method VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            ingestion_run_id VARCHAR NOT NULL,
            ingested_at TIMESTAMP NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES dim_customers(customer_id)
        )
    """)

    # 3. Quarantine store for invalid records
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quarantine_orders (
            quarantine_id VARCHAR PRIMARY KEY,
            original_order_id VARCHAR,
            raw_payload VARCHAR NOT NULL,
            error_codes VARCHAR NOT NULL,
            error_messages VARCHAR NOT NULL,
            failed_check_stage VARCHAR NOT NULL,
            source_file VARCHAR,
            run_id VARCHAR NOT NULL,
            replay_status VARCHAR NOT NULL DEFAULT 'PENDING',
            replay_run_id VARCHAR,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)

    # 4. Pipeline audit & observability log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id VARCHAR PRIMARY KEY,
            run_type VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            records_read INTEGER NOT NULL DEFAULT 0,
            records_valid INTEGER NOT NULL DEFAULT 0,
            records_quarantined INTEGER NOT NULL DEFAULT 0,
            records_replayed INTEGER NOT NULL DEFAULT 0,
            error_summary VARCHAR
        )
    """)

    conn.close()
    print("Database initialized successfully at:", DB_PATH)

if __name__ == "__main__":
    init_db()