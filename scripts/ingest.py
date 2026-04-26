import csv
import sqlite3
from pathlib import Path

from cleaning import normalize_spaces
from db import upsert_market

ROOT = Path(__file__).resolve().parent.parent

MARKET_FILES = [
    ("EU", "Europe",        "final_market_a_eu_catalog.csv"),
    ("US", "United States", "final_market_b_us_catalog.csv"),
    ("ES", "Spain",         "final_market_c_es_catalog.csv"),
    ("CH", "Switzerland",   "final_market_d_ch_catalog.csv"),
]


def _detect_delimiter(file_path: Path) -> str:
    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        first_line = f.readline()
    return ";" if (";" in first_line and "," not in first_line) else ","


def ingest_source_products(conn: sqlite3.Connection) -> int:
    total = 0
    for market_code, market_name, file_name in MARKET_FILES:
        market_id = upsert_market(conn, market_code, market_name)
        file_path = ROOT / "data" / file_name
        delimiter = _detect_delimiter(file_path)

        with file_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                model_name   = normalize_spaces(row.get("model_name", ""))
                manufacturer = normalize_spaces(row.get("manufacturer_of_record", ""))
                raw_components = row.get("core_components")
                raw_components = raw_components.strip() if raw_components else None

                if not model_name or not manufacturer:
                    continue

                conn.execute(
                    """
                    INSERT INTO source_products (
                        market_id, raw_model_name, raw_core_components, raw_manufacturer_of_record
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (market_id, model_name, raw_components, manufacturer),
                )
                total += 1

        conn.commit()
        print(f"[ingest] {market_code} loaded from {file_name}")
    return total
