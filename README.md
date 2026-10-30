# Data Quarantine & Controlled Replay Pipeline

A production-grade, serverless Data Engineering solution built with **Python** and **DuckDB**. This pipeline ingests incoming order records, enforces strict schema, domain, referential integrity, and business rule validations, routes valid records to a target data warehouse (`fact_orders`), isolates invalid records in a rich failure-context **Quarantine Store** (`quarantine_orders`), and provides a **Controlled Replay Engine** to reprocess corrected data without reprocessing successful records or generating duplicates.

---

## Architecture & Data Flow

```
                     ┌────────────────────────┐
                     │   Incoming Raw Data    │
                     │  (CSV / JSON Batches)  │
                     └───────────┬────────────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │   Ingestion & Audit    │
                     │ (Assign unique Run ID) │
                     └───────────┬────────────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │  Validation Engine     │
                     │  • Schema & Required   │
                     │  • Foreign Keys        │
                     │  • Domain Business Rules│
                     │  • Duplicate Checks    │
                     └───────┬────────┬───────┘
                             │        │
             ┌───────────────┘        └────────────────┐
             │ Valid                                   │ Invalid
             ▼                                         ▼
┌────────────────────────┐             ┌────────────────────────┐
│ Target Warehouse       │             │ Quarantine Store       │
│ (`fact_orders`)        │             │ (`quarantine_orders`)  │
│  - Idempotent MERGE    │             │  - Original Raw Payload│
│  - Lineage & Run ID    │             │  - Error Codes & Rules │
└────────────────────────┘             │  - Replay Status       │
                                       └───────────┬────────────┘
                                                   │
                                     Manual / Automated Correction
                                                   │
                                                   ▼
                                       ┌────────────────────────┐
                                       │ Controlled Replay      │
                                       │ Engine                 │
                                       │  - Validates Fixes     │
                                       │  - Merges into Target  │
                                       │  - Updates Replay State│
                                       └────────────────────────┘
```

---

## Tech Stack

- **Python (3.10+)** — Core orchestration, validation logic, and CLI.
- **DuckDB** — Embedded serverless analytical SQL database for storage, vector processing, and idempotent `UPSERT` merging.
- **Pytest** — Automated testing framework for unit and integration testing.

---

## Data Dictionary & Schema

### 1. `dim_customers` (Reference Dimension)
- `customer_id` (VARCHAR, PK) — Unique customer identifier.
- `customer_name` (VARCHAR) — Customer full name.
- `account_status` (VARCHAR) — Status: `ACTIVE`, `SUSPENDED`, `CLOSED`.
- `created_at` (TIMESTAMP) — Account creation timestamp.

### 2. `fact_orders` (Target Data Warehouse)
- `order_id` (VARCHAR, PK) — Unique order transaction identifier.
- `customer_id` (VARCHAR, FK) — Reference to customer.
- `order_date` (TIMESTAMP) — Order timestamp (ISO-8601).
- `total_amount` (DECIMAL) — Monetary transaction amount (> 0).
- `currency` (VARCHAR) — ISO currency code (`USD`, `EUR`, `GBP`, `CAD`, `JPY`).
- `payment_method` (VARCHAR) — Payment type (`CREDIT_CARD`, `PAYPAL`, `BANK_TRANSFER`, `CRYPTO`).
- `status` (VARCHAR) — Order status (`COMPLETED`, `PENDING`, `CANCELLED`).
- `ingestion_run_id` (VARCHAR) — Pipeline run lineage ID.
- `ingested_at` (TIMESTAMP) — Ingestion timestamp.

### 3. `quarantine_orders` (Quarantine Store)
- `quarantine_id` (VARCHAR, PK) — Deterministic unique quarantine entry ID.
- `original_order_id` (VARCHAR) — Order ID if present.
- `raw_payload` (VARCHAR / JSON) — Exact raw source record payload.
- `error_codes` (VARCHAR / JSON Array) — Error tags (e.g. `["ERR_NEGATIVE_AMOUNT"]`).
- `error_messages` (VARCHAR / JSON Array) — Human-readable rule failure explanations.
- `failed_check_stage` (VARCHAR) — Failure category (`SCHEMA_VALIDATION`, `BUSINESS_RULE`, `UNIQUENESS_CHECK`).
- `source_file` (VARCHAR) — Originating file path.
- `run_id` (VARCHAR) — Ingestion run ID.
- `replay_status` (VARCHAR) — Replay state (`PENDING`, `REPLAYED`, `DISCARDED`).
- `replay_run_id` (VARCHAR) — Run ID that successfully replayed the record.

---

## Setup & Quick Start

1. **Clone and Setup Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install duckdb pytest
   ```

2. **Initialize Database:**
   ```bash
   python -m src.cli init-db
   ```

3. **Generate Synthetic Sample Data:**
   ```bash
   python -m src.cli generate --records 1000 --seed 42
   ```

4. **Run Ingestion Pipeline:**
   ```bash
   python -m src.cli ingest --input data/sample_orders.csv
   ```

5. **Run Controlled Replay (for quarantined records):**
   ```bash
   python -m src.cli replay
   ```

6. **Run Reconciliation Audit:**
   ```bash
   python -m src.cli reconcile
   ```

7. **Run Performance Benchmark (50k records):**
   ```bash
   python -m src.cli benchmark --records 50000
   ```

8. **Run Automated Tests:**
   ```bash
   pytest -v
   ```

---

## Design Notes & Trade-Offs

- **Fail-Soft Validation:** Instead of crashing or dropping bad records on the first failure, the validation engine evaluates all rules simultaneously, collecting every failure reason into an error array stored alongside the raw payload.
- **Idempotency:** Re-running ingestion or replay uses SQL `ON CONFLICT DO UPDATE` upserts, preventing duplicate entries in `fact_orders`.
- **Zero Infrastructure:** DuckDB allows enterprise-grade analytical storage and querying in a single local file (`data/pipeline.duckdb`) with zero external daemon configuration required.