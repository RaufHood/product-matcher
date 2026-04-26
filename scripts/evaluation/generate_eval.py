"""
Generate evaluation data for the matching algorithm.

Outputs
-------
data/eval_pairs.csv
    100 auto-labeled positive pairs found by the naive pipeline (label=1).
    25 per market: EU/US/ES anchor on the left side, CH on the right side
    (CH source IDs are always higher in this DB, so it only appears as id_b).

data/manual_candidates.csv
    100 unmatched products (25 per market) the naive pipeline could not link
    to any other market. Use these as the starting point for manual labeling.

Run from any directory:
    python scripts/generate_eval.py
"""

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "electropulse.db"
EVAL_PAIRS_PATH = ROOT / "data" / "eval_pairs.csv"
MANUAL_CANDIDATES_PATH = ROOT / "data" / "manual_candidates.csv"

SAMPLE_SIZE = 25


def get_naive_pairs_anchored_left(
    conn: sqlite3.Connection, market_a: str, limit: int
) -> list[tuple]:
    """Cross-market positive pairs where market_a is on the left (lower id)."""
    return conn.execute(
        """
        SELECT
            sp1.id, sp2.id,
            m1.market_code, m2.market_code,
            sp1.raw_model_name, sp2.raw_model_name,
            sp1.normalized_model_name, sp2.normalized_model_name
        FROM source_product_models spm1
        JOIN source_product_models spm2 ON spm1.model_id = spm2.model_id
        JOIN source_products sp1 ON spm1.source_product_id = sp1.id
        JOIN source_products sp2 ON spm2.source_product_id = sp2.id
        JOIN markets m1 ON sp1.market_id = m1.id
        JOIN markets m2 ON sp2.market_id = m2.id
        WHERE sp1.id < sp2.id
          AND m1.market_code != m2.market_code
          AND m1.market_code = ?
          AND spm1.match_type = 'direct'
          AND spm2.match_type = 'direct'
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (market_a, limit),
    ).fetchall()


def get_naive_pairs_anchored_right(
    conn: sqlite3.Connection, market_b: str, limit: int
) -> list[tuple]:
    """Cross-market positive pairs where market_b is on the right (higher id).
    Used for CH which always has higher source IDs in this DB."""
    return conn.execute(
        """
        SELECT
            sp1.id, sp2.id,
            m1.market_code, m2.market_code,
            sp1.raw_model_name, sp2.raw_model_name,
            sp1.normalized_model_name, sp2.normalized_model_name
        FROM source_product_models spm1
        JOIN source_product_models spm2 ON spm1.model_id = spm2.model_id
        JOIN source_products sp1 ON spm1.source_product_id = sp1.id
        JOIN source_products sp2 ON spm2.source_product_id = sp2.id
        JOIN markets m1 ON sp1.market_id = m1.id
        JOIN markets m2 ON sp2.market_id = m2.id
        WHERE sp1.id < sp2.id
          AND m1.market_code != m2.market_code
          AND m2.market_code = ?
          AND spm1.match_type = 'direct'
          AND spm2.match_type = 'direct'
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (market_b, limit),
    ).fetchall()


def get_unmatched_candidates(
    conn: sqlite3.Connection, market_code: str, limit: int
) -> list[tuple]:
    """Products from this market that have no cross-market naive match."""
    return conn.execute(
        """
        SELECT
            sp.id,
            m.market_code,
            sp.raw_model_name,
            sp.normalized_model_name,
            sp.raw_core_components,
            sp.raw_manufacturer_of_record
        FROM source_products sp
        JOIN markets m ON sp.market_id = m.id
        WHERE m.market_code = ?
          AND sp.id NOT IN (
              SELECT DISTINCT sp1.id
              FROM source_product_models spm1
              JOIN source_product_models spm2 ON spm1.model_id = spm2.model_id
              JOIN source_products sp1 ON spm1.source_product_id = sp1.id
              JOIN source_products sp2 ON spm2.source_product_id = sp2.id
              JOIN markets m1 ON sp1.market_id = m1.id
              JOIN markets m2 ON sp2.market_id = m2.id
              WHERE m1.market_code != m2.market_code
                AND spm1.match_type != 'bundle_part'
                AND spm2.match_type != 'bundle_part'
              UNION
              SELECT DISTINCT sp2.id
              FROM source_product_models spm1
              JOIN source_product_models spm2 ON spm1.model_id = spm2.model_id
              JOIN source_products sp1 ON spm1.source_product_id = sp1.id
              JOIN source_products sp2 ON spm2.source_product_id = sp2.id
              JOIN markets m1 ON sp1.market_id = m1.id
              JOIN markets m2 ON sp2.market_id = m2.id
              WHERE m1.market_code != m2.market_code
                AND spm1.match_type != 'bundle_part'
                AND spm2.match_type != 'bundle_part'
          )
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (market_code, limit),
    ).fetchall()


def main() -> None:
    if not DB_PATH.exists():
        print(f"[error] DB not found at {DB_PATH} — run main.py first.")
        return

    conn = sqlite3.connect(DB_PATH)

    # ── eval_pairs.csv ────────────────────────────────────────────────────────
    pair_fieldnames = [
        "id_a", "id_b", "market_a", "market_b",
        "name_a", "name_b", "norm_name_a", "norm_name_b",
        "label", "match_type", "notes",
    ]
    pair_rows = []

    for market in ["EU", "US", "ES"]:
        pairs = get_naive_pairs_anchored_left(conn, market, SAMPLE_SIZE)
        for id_a, id_b, mkt_a, mkt_b, na, nb, nna, nnb in pairs:
            pair_rows.append({
                "id_a": id_a, "id_b": id_b,
                "market_a": mkt_a, "market_b": mkt_b,
                "name_a": na, "name_b": nb,
                "norm_name_a": nna, "norm_name_b": nnb,
                "label": 1, "match_type": "naive", "notes": "",
            })
        print(f"[eval_pairs] {market}: {len(pairs)} pairs collected")

    # CH always appears as id_b (higher IDs), so anchor on the right
    ch_pairs = get_naive_pairs_anchored_right(conn, "CH", SAMPLE_SIZE)
    for id_a, id_b, mkt_a, mkt_b, na, nb, nna, nnb in ch_pairs:
        pair_rows.append({
            "id_a": id_a, "id_b": id_b,
            "market_a": mkt_a, "market_b": mkt_b,
            "name_a": na, "name_b": nb,
            "norm_name_a": nna, "norm_name_b": nnb,
            "label": 1, "match_type": "naive", "notes": "",
        })
    print(f"[eval_pairs] CH (right-anchored): {len(ch_pairs)} pairs collected")

    with EVAL_PAIRS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=pair_fieldnames)
        writer.writeheader()
        writer.writerows(pair_rows)
    print(f"[eval_pairs] wrote {len(pair_rows)} rows -> {EVAL_PAIRS_PATH.name}\n")

    # ── manual_candidates.csv ─────────────────────────────────────────────────
    candidate_fieldnames = [
        "id", "market",
        "raw_model_name", "normalized_model_name",
        "raw_core_components", "manufacturer",
    ]
    candidate_rows = []

    for market in ["EU", "US", "ES", "CH"]:
        candidates = get_unmatched_candidates(conn, market, SAMPLE_SIZE)
        for id_, mkt, raw_name, norm_name, raw_comp, raw_mfr in candidates:
            candidate_rows.append({
                "id": id_, "market": mkt,
                "raw_model_name": raw_name,
                "normalized_model_name": norm_name,
                "raw_core_components": raw_comp or "",
                "manufacturer": raw_mfr,
            })
        print(f"[candidates] {market}: {len(candidates)} unmatched products")

    with MANUAL_CANDIDATES_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=candidate_fieldnames)
        writer.writeheader()
        writer.writerows(candidate_rows)
    print(f"[candidates] wrote {len(candidate_rows)} rows -> {MANUAL_CANDIDATES_PATH.name}")

    conn.close()


if __name__ == "__main__":
    main()
