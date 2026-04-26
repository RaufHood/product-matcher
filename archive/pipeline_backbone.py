import argparse
import csv
import re
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent

MARKET_FILES = [
    ("EU", "Europe", "final_market_a_eu_catalog.csv"),
    ("US", "United States", "final_market_b_us_catalog.csv"),
    ("ES", "Spain", "final_market_c_es_catalog.csv"),
    ("CH", "Switzerland", "final_market_d_ch_catalog.csv"),
]


NOISE_PATTERN = re.compile(
    r"\b("
    r"\d+(?:gb|tb)|"
    r"dual[-\s]?sim|"
    r"starter\s+kit|"
    r"refurbished|"
    r"bundle|"
    r"lite|"
    r"gen\s*\d+"
    r")\b",
    flags=re.IGNORECASE,
)


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_model_name(raw_model_name: str) -> str:
    text = raw_model_name.replace("‑", "-")
    text = NOISE_PATTERN.sub(" ", text)
    text = re.sub(r"\s*[/,&]\s*", " ", text)
    text = re.sub(r"\s+\band\b\s+", " ", text, flags=re.IGNORECASE)
    return normalize_spaces(text)


def normalize_manufacturer(raw_manufacturer: str) -> str:
    return normalize_spaces(raw_manufacturer.replace("‑", "-"))


def split_components(raw_components: str | None) -> list[str]:
    if not raw_components:
        return []
    text = raw_components.replace("‑", "-")
    parts = re.split(r"\s*(?:/|,|;|\+|&|\band\b)\s*", text, flags=re.IGNORECASE)
    return [normalize_spaces(p) for p in parts if normalize_spaces(p)]


def detect_delimiter(file_path: Path) -> str:
    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        first_line = f.readline()
    if ";" in first_line and "," not in first_line:
        return ";"
    return ","


def execute_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()


def upsert_market(conn: sqlite3.Connection, market_code: str, market_name: str) -> int:
    conn.execute(
        """
        INSERT INTO markets (market_code, market_name)
        VALUES (?, ?)
        ON CONFLICT(market_code) DO UPDATE SET market_name = excluded.market_name
        """,
        (market_code, market_name),
    )
    row = conn.execute("SELECT id FROM markets WHERE market_code = ?", (market_code,)).fetchone()
    return int(row[0])


def upsert_name_entity(conn: sqlite3.Connection, table_name: str, column_name: str, value: str) -> int:
    conn.execute(
        f"INSERT INTO {table_name} ({column_name}) VALUES (?) ON CONFLICT({column_name}) DO NOTHING",
        (value,),
    )
    row = conn.execute(f"SELECT id FROM {table_name} WHERE {column_name} = ?", (value,)).fetchone()
    return int(row[0])


def ingest_source_products(conn: sqlite3.Connection) -> int:
    total_rows = 0
    for market_code, market_name, file_name in MARKET_FILES:
        market_id = upsert_market(conn, market_code, market_name)
        file_path = ROOT / file_name
        delimiter = detect_delimiter(file_path)

        with file_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                model_name = normalize_spaces(row.get("model_name", ""))
                manufacturer = normalize_spaces(row.get("manufacturer_of_record", ""))
                core_components = row.get("core_components")
                core_components = core_components.strip() if core_components else None

                if not model_name or not manufacturer:
                    continue

                conn.execute(
                    """
                    INSERT INTO source_products (
                        market_id,
                        raw_model_name,
                        raw_core_components,
                        raw_manufacturer_of_record
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (market_id, model_name, core_components, manufacturer),
                )
                total_rows += 1

        conn.commit()
        print(f"[ingest] {market_code} loaded from {file_name}")
    return total_rows


def run_naive_matching_pipeline(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, raw_model_name, raw_core_components, raw_manufacturer_of_record
        FROM source_products
        ORDER BY id
        """
    ).fetchall()

    for source_product_id, raw_model, raw_components, raw_manufacturer in rows:
        normalized_model = normalize_model_name(raw_model)
        normalized_manufacturer = normalize_manufacturer(raw_manufacturer)
        parsed_components = split_components(raw_components)
        normalized_components = " | ".join(parsed_components) if parsed_components else None

        manufacturer_id = upsert_name_entity(
            conn, "manufacturers", "canonical_name", normalized_manufacturer
        )
        model_id = upsert_name_entity(conn, "models", "canonical_model_name", normalized_model)

        conn.execute(
            """
            UPDATE source_products
            SET manufacturer_id = ?, normalized_model_name = ?, normalized_core_components = ?
            WHERE id = ?
            """,
            (manufacturer_id, normalized_model, normalized_components, source_product_id),
        )

        conn.execute(
            """
            INSERT INTO source_product_models (source_product_id, model_id, match_type)
            VALUES (?, ?, 'direct')
            ON CONFLICT(source_product_id, model_id) DO NOTHING
            """,
            (source_product_id, model_id),
        )

        for comp in parsed_components:
            component_id = upsert_name_entity(conn, "components", "canonical_name", comp)
            conn.execute(
                """
                INSERT INTO source_product_components (source_product_id, component_id)
                VALUES (?, ?)
                ON CONFLICT(source_product_id, component_id) DO NOTHING
                """,
                (source_product_id, component_id),
            )
            conn.execute(
                """
                INSERT INTO model_components (model_id, component_id)
                VALUES (?, ?)
                ON CONFLICT(model_id, component_id) DO NOTHING
                """,
                (model_id, component_id),
            )

    conn.commit()


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
    parser = argparse.ArgumentParser(
        description="Create local DB, ingest CSVs, and run naive matching pipeline."
    )
    parser.add_argument("--db-path", default="electropulse.db", help="SQLite DB path")
    parser.add_argument(
        "--schema-path",
        default="schema_sqlite.sql",
        help="SQLite schema SQL file path",
    )
    args = parser.parse_args()

    db_path = ROOT / args.db_path
    schema_path = ROOT / args.schema_path

    conn = sqlite3.connect(db_path)
    try:
        execute_schema(conn, schema_path)
        loaded = ingest_source_products(conn)
        print(f"[ingest] total rows loaded: {loaded}")
        run_naive_matching_pipeline(conn)
        print("[match] naive pipeline completed")
        print_summary(conn)
        print(f"\nDone. SQLite DB created at: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
