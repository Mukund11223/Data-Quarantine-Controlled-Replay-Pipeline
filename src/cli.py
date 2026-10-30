import argparse
from db import init_db
from generator import generate_synthetic_data
from pipeline import run_pipeline
from replay import run_replay
from reconcile import run_reconciliation
from benchmark import run_benchmark

def main():
    parser = argparse.ArgumentParser(description="Data Quarantine & Controlled Replay Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db
    subparsers.add_parser("init-db", help="Initialize the DuckDB database and tables")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate synthetic sample dataset")
    gen_parser.add_argument("--records", type=int, default=1000, help="Number of records to generate")
    gen_parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    gen_parser.add_argument("--output", type=str, default="data/sample_orders.csv", help="Output CSV path")

    # ingest
    ing_parser = subparsers.add_parser("ingest", help="Run the ingestion & validation pipeline")
    ing_parser.add_argument("--input", type=str, default="data/sample_orders.csv", help="Input CSV path")

    # replay
    subparsers.add_parser("replay", help="Run controlled replay of pending quarantined records")

    # reconcile
    subparsers.add_parser("reconcile", help="Run audit and reconciliation report")

    # benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Run performance benchmark")
    bench_parser.add_argument("--records", type=int, default=50000, help="Number of benchmark records")

    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "generate":
        generate_synthetic_data(num_records=args.records, seed=args.seed, output_path=args.output)
    elif args.command == "ingest":
        run_pipeline(input_csv_path=args.input)
    elif args.command == "replay":
        run_replay()
    elif args.command == "reconcile":
        run_reconciliation()
    elif args.command == "benchmark":
        run_benchmark(num_records=args.records)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()