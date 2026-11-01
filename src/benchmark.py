import time
from .generator import generate_synthetic_data
from .pipeline import run_pipeline
from .reconcile import run_reconciliation

def run_benchmark(num_records: int = 100000):
    print(f"=== STARTING PERFORMANCE BENCHMARK ({num_records:,} records) ===")

    start_gen = time.time()
    csv_path = generate_synthetic_data(num_records=num_records, seed=123, output_path="data/benchmark_orders.csv")
    gen_duration = time.time() - start_gen
    print(f"Generated {num_records:,} records in {gen_duration:.2f} seconds.")

    start_pipe = time.time()
    summary = run_pipeline(input_csv_path=csv_path, run_id="benchmark_run_01")
    pipe_duration = time.time() - start_pipe
    print(f"Ingested & validated {num_records:,} records in {pipe_duration:.2f} seconds.")

    throughput = num_records / pipe_duration
    print(f"Throughput: {throughput:,.2f} records/second.")

    run_reconciliation()
    print("=== BENCHMARK COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_benchmark(num_records=50000)