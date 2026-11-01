import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
import duckdb
from .db import get_connection

SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "CAD", "JPY"]
PAYMENT_METHODS = ["CREDIT_CARD", "PAYPAL", "BANK_TRANSFER", "CRYPTO"]
STATUSES = ["COMPLETED", "PENDING", "CANCELLED"]

def get_utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def generate_synthetic_data(num_records: int = 1000, seed: int = 42, output_path: str = "data/sample_orders.csv"):
    random.seed(seed)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # First, let's seed some reference customers in the database
    conn = get_connection()
    conn.execute("DELETE FROM fact_orders")
    conn.execute("DELETE FROM quarantine_orders")
    conn.execute("DELETE FROM dim_customers")

    customers = []
    for i in range(1, 201):
        cust_id = f"CUST_{i:04d}"
        name = f"Customer {i}"
        # 5% chance customer is suspended or closed
        status = "ACTIVE"
        if i % 20 == 0:
            status = "SUSPENDED"
        elif i % 35 == 0:
            status = "CLOSED"

        created_at = (get_utc_now() - timedelta(days=random.randint(30, 365))).isoformat()
        customers.append((cust_id, name, status, created_at))

    conn.executemany(
        "INSERT INTO dim_customers (customer_id, customer_name, account_status, created_at) VALUES (?, ?, ?, ?)",
        customers
    )
    conn.close()

    valid_customer_ids = [c[0] for c in customers if c[2] == "ACTIVE"]
    suspended_customer_ids = [c[0] for c in customers if c[2] != "ACTIVE"]

    fields = ["order_id", "customer_id", "order_date", "total_amount", "currency", "payment_method", "status"]

    records = []
    base_time = get_utc_now() - timedelta(days=7)

    seen_order_ids = set()

    for i in range(1, num_records + 1):
        order_id = f"ORD_{i:06d}"

        # Determine anomaly distribution
        # 85% clean, 15% various edge cases / invalid records
        anomaly_roll = random.random()

        # Defaults
        cust_id = random.choice(valid_customer_ids)
        order_date = (base_time + timedelta(hours=random.randint(0, 168))).isoformat()
        amount = round(random.uniform(10.0, 1500.0), 2)
        currency = random.choice(SUPPORTED_CURRENCIES)
        pay_method = random.choice(PAYMENT_METHODS)
        status = random.choice(STATUSES)

        if anomaly_roll < 0.85:
            # Clean record
            pass
        elif anomaly_roll < 0.88:
            # Negative or zero amount (Domain rule error)
            amount = round(random.uniform(-500.0, 0.0), 2)
        elif anomaly_roll < 0.91:
            # Missing required field (Schema error)
            order_id = "" if i % 2 == 0 else order_id
            amount = "" if i % 2 != 0 else amount
        elif anomaly_roll < 0.94:
            # Invalid customer / Foreign key violation or inactive customer
            if i % 2 == 0:
                cust_id = "CUST_UNKNOWN_9999"
            else:
                cust_id = random.choice(suspended_customer_ids) if suspended_customer_ids else "CUST_SUSP_1"
        elif anomaly_roll < 0.96:
            # Duplicate key in batch
            if records:
                order_id = records[0]["order_id"]
        elif anomaly_roll < 0.98:
            # Malformed date / future date
            if i % 2 == 0:
                order_date = "INVALID-DATE-STRING"
            else:
                order_date = (base_time + timedelta(days=30)).isoformat() # Future date
        else:
            # Unsupported currency
            currency = "XXX"

        if order_id and order_id in seen_order_ids and anomaly_roll >= 0.96:
            # Duplicate
            pass
        elif order_id:
            seen_order_ids.add(order_id)

        record = {
            "order_id": order_id,
            "customer_id": cust_id,
            "order_date": order_date,
            "total_amount": amount,
            "currency": currency,
            "payment_method": pay_method,
            "status": status
        }
        records.append(record)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    print(f"Generated {num_records} sample records at {output_path} (seed={seed})")
    return output_path

if __name__ == "__main__":
    generate_synthetic_data(num_records=1000)