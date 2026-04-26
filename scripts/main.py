import argparse
import sqlite3
from pathlib import Path

from aliases import load_canonical_components
from db import execute_schema
from ingest import ingest_source_products
from matching import run_matching_pipeline

ROOT = Path(__file__).resolve().parent.parent


def print_summary(conn: sqlite3.Connection) -> None:
    tables = [
        "markets",
        "source_products",
        "models",
        "manufacturers",
        "components",
        "source_product_models",
        "source_product_components",
        "model_components",
    ]
    print("\n=== Row counts ===")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:25s} {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest and match ElectroPulse catalog data.")
    parser.add_argument("--db-path",     default=str(ROOT / "electropulse.db"))
    parser.add_argument("--schema-path", default=str(ROOT / "sql" / "schema_sqlite.sql"))
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        execute_schema(conn, Path(args.schema_path))
        load_canonical_components(conn)
        loaded = ingest_source_products(conn)
        print(f"[ingest] total rows loaded: {loaded}")
        run_matching_pipeline(conn)
        print("[match] pipeline completed")
        print_summary(conn)
        print(f"\nDone. DB at: {args.db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
