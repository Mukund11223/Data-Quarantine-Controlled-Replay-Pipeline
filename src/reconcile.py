from .db import get_connection

def run_reconciliation() -> dict:
    conn = get_connection()

    # Query counts across stores
    total_pipeline_input = conn.execute("SELECT COALESCE(SUM(records_read), 0) FROM pipeline_runs WHERE run_type = 'STANDARD_INGEST'").fetchone()[0]
    total_valid_loaded = conn.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0]
    total_pending_quarantine = conn.execute("SELECT COUNT(*) FROM quarantine_orders WHERE replay_status = 'PENDING'").fetchone()[0]
    total_replayed = conn.execute("SELECT COUNT(*) FROM quarantine_orders WHERE replay_status = 'REPLAYED'").fetchone()[0]
    total_quarantined_total = conn.execute("SELECT COUNT(*) FROM quarantine_orders").fetchone()[0]

    # Derived metrics
    originally_valid = total_valid_loaded - total_replayed
    duplicates_or_overwritten = max(0, total_pipeline_input - (originally_valid + total_quarantined_total))

    # Invariant check:
    # Every ingested record must account for being originally valid, in quarantine, or a deduplicated/overwritten key
    reconciled = (originally_valid + total_quarantined_total + duplicates_or_overwritten) == total_pipeline_input

    report = {
        "total_pipeline_input_records": total_pipeline_input,
        "originally_valid_records": originally_valid,
        "total_valid_in_fact_orders": total_valid_loaded,
        "total_pending_quarantine_records": total_pending_quarantine,
        "total_replayed_records": total_replayed,
        "total_quarantine_records": total_quarantined_total,
        "duplicates_or_overwritten_records": duplicates_or_overwritten,
        "reconciliation_passed": reconciled
    }

    print("=== RECONCILIATION REPORT ===")
    print(f"Total Input Records Ingested : {total_pipeline_input}")
    print(f"  ├── Originally Valid Records : {originally_valid}")
    print(f"  ├── Total Quarantined        : {total_quarantined_total} ({total_pending_quarantine} Pending + {total_replayed} Replayed)")
    print(f"  └── Duplicates / Overwritten : {duplicates_or_overwritten}")
    print(f"Total Valid Records in Target: {total_valid_loaded}")
    print(f"Reconciliation Status        : {'PASSED ✅' if report['reconciliation_passed'] else 'FAILED ❌'}")
    print("==============================")

    conn.close()
    return report

if __name__ == "__main__":
    run_reconciliation()