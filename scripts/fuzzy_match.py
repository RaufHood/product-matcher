"""
Tier-2 fuzzy matching pass.

Runs AFTER the naive exact-match pipeline (main.py) and links products that
the naive pipeline could not connect. Uses first-token blocking so comparisons
stay O(n * block_size) rather than O(n²).

─── Algorithm selection ────────────────────────────────────────────────────────
Three algorithms are available. Enable the one you want by setting ALGO, or
pass --algo on the command line to compare without editing the file.

  name_only      Blended token_set + token_sort on normalized model name.
                 Fastest. Good baseline.

  name_comp      Name similarity + component overlap (Jaccard on component
                 strings). Penalises candidates missing component data when
                 the anchor has it.

  name_comp_mfr  Name + component + manufacturer brand match.
                 Most signals; best precision on generic products.

─── Usage ──────────────────────────────────────────────────────────────────────
  # Run with default settings (ALGO + DEFAULT_THRESHOLD below)
  python scripts/fuzzy_match.py

  # Compare algorithms without touching the DB
  python scripts/fuzzy_match.py --algo name_only     --threshold 0.70 --dry-run
  python scripts/fuzzy_match.py --algo name_comp     --threshold 0.70 --dry-run
  python scripts/fuzzy_match.py --algo name_comp_mfr --threshold 0.70 --dry-run

  # Actually write links (rebuilds from scratch to stay clean)
  python scripts/main.py && python scripts/fuzzy_match.py --algo name_comp_mfr --threshold 0.70
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cleaning import extract_brand_from_manufacturer

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "electropulse.db"

# ── Config (override with --algo / --threshold flags) ─────────────────────────
ALGO = "name_comp_mfr"   # name_only | name_comp | name_comp_mfr
DEFAULT_THRESHOLD = 0.70

# Weight tuples: (name, component, manufacturer)
# Component weight is redistributed to name when either side has no component data.
WEIGHTS = {
    "name_only":      (1.00, 0.00, 0.00),
    "name_comp":      (0.65, 0.35, 0.00),
    "name_comp_mfr":  (0.55, 0.30, 0.15),
}


# ── Scoring ───────────────────────────────────────────────────────────────────

def _name_sim(a: str, b: str) -> float:
    return fuzz.token_sort_ratio(a, b) / 100.0


def score_pair(a: dict, b: dict, algo: str) -> float:
    w_name, w_comp, w_mfr = WEIGHTS[algo]

    if not a["comp"] or not b["comp"]:
        w_name += w_comp   # redistribute component weight to name
        w_comp = 0.0

    ns = _name_sim(a["norm_name"], b["norm_name"])
    cs = fuzz.token_set_ratio(a["comp"], b["comp"]) / 100.0 if w_comp else 0.0
    ms = (1.0 if a["brand"] and b["brand"]
          and a["brand"].lower() == b["brand"].lower() else 0.0)

    total = w_name + w_comp + w_mfr
    return (w_name * ns + w_comp * cs + w_mfr * ms) / total if total else 0.0


# ── Data loading ──────────────────────────────────────────────────────────────

def load_products(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    rows = conn.execute("""
        SELECT sp.id, m.market_code,
               sp.normalized_model_name,
               sp.normalized_core_components,
               sp.raw_manufacturer_of_record
        FROM source_products sp
        JOIN markets m ON sp.market_id = m.id
        WHERE sp.normalized_model_name IS NOT NULL
          AND sp.normalized_model_name != ''
    """).fetchall()

    by_market: dict[str, list[dict]] = {}
    for pid, mkt, norm_name, comp, mfr in rows:
        brand = extract_brand_from_manufacturer(mfr or "")
        by_market.setdefault(mkt, []).append({
            "id": pid, "market": mkt,
            "norm_name": norm_name or "",
            "comp": comp or "",
            "brand": brand,
        })
    return by_market


def get_matched_ids(conn: sqlite3.Connection) -> set[int]:
    return set(r[0] for r in conn.execute("""
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
    """).fetchall())


def coverage(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM source_products").fetchone()[0]
    matched = conn.execute("""
        SELECT COUNT(DISTINCT sp.id) FROM source_products sp WHERE sp.id IN (
            SELECT DISTINCT sp1.id FROM source_product_models spm1
            JOIN source_product_models spm2 ON spm1.model_id=spm2.model_id
            JOIN source_products sp1 ON spm1.source_product_id=sp1.id
            JOIN source_products sp2 ON spm2.source_product_id=sp2.id
            JOIN markets m1 ON sp1.market_id=m1.id
            JOIN markets m2 ON sp2.market_id=m2.id
            WHERE m1.market_code!=m2.market_code
              AND spm1.match_type!='bundle_part' AND spm2.match_type!='bundle_part'
            UNION
            SELECT DISTINCT sp2.id FROM source_product_models spm1
            JOIN source_product_models spm2 ON spm1.model_id=spm2.model_id
            JOIN source_products sp1 ON spm1.source_product_id=sp1.id
            JOIN source_products sp2 ON spm2.source_product_id=sp2.id
            JOIN markets m1 ON sp1.market_id=m1.id
            JOIN markets m2 ON sp2.market_id=m2.id
            WHERE m1.market_code!=m2.market_code
              AND spm1.match_type!='bundle_part' AND spm2.match_type!='bundle_part')
    """).fetchone()[0]
    return {"total": total, "matched": matched, "unmatched": total - matched}


# ── Fuzzy pass ────────────────────────────────────────────────────────────────

def run_fuzzy_pass(
    conn: sqlite3.Connection,
    algo: str,
    threshold: float,
    dry_run: bool = False,
) -> int:
    """
    For every unmatched product, find its best cross-market fuzzy match within
    the same first-token block. Links it to the candidate's canonical model if
    score >= threshold. Returns number of new links created (or would-be links
    in dry-run mode).
    """
    by_market = load_products(conn)
    matched_ids = get_matched_ids(conn)

    # Build first-token index per market for blocking
    index: dict[str, dict[str, list[dict]]] = {}
    for mkt, products in by_market.items():
        index[mkt] = defaultdict(list)
        for p in products:
            tok = p["norm_name"].split()[0].lower() if p["norm_name"] else "__none__"
            index[mkt][tok].append(p)

    all_unmatched = [
        p for mkt, products in by_market.items()
        for p in products if p["id"] not in matched_ids
    ]
    total = len(all_unmatched)
    new_links = 0

    for i, anchor in enumerate(all_unmatched):
        if (i + 1) % 1000 == 0:
            print(f"  [{i+1}/{total}] new links: {new_links}", end="\r", flush=True)

        tok = anchor["norm_name"].split()[0].lower() if anchor["norm_name"] else "__none__"
        best_score = 0.0
        best_cand = None

        for other_mkt, tok_idx in index.items():
            if other_mkt == anchor["market"]:
                continue
            for cand in tok_idx.get(tok, []):
                s = score_pair(anchor, cand, algo)
                if s > best_score:
                    best_score = s
                    best_cand = cand

        if best_cand and best_score >= threshold:
            if not dry_run:
                model_row = conn.execute(
                    "SELECT model_id FROM source_product_models "
                    "WHERE source_product_id = ? AND match_type = 'direct' LIMIT 1",
                    (best_cand["id"],),
                ).fetchone()
                if model_row:
                    conn.execute(
                        """INSERT INTO source_product_models
                               (source_product_id, model_id, match_type)
                           VALUES (?, ?, 'fuzzy')
                           ON CONFLICT DO NOTHING""",
                        (anchor["id"], model_row[0]),
                    )
            new_links += 1

    if not dry_run:
        conn.commit()

    print()
    return new_links


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Tier-2 fuzzy matching pass.")
    parser.add_argument("--algo", default=ALGO, choices=list(WEIGHTS))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count would-be links without writing to the DB.",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        before = coverage(conn)
        print(f"[naive]  matched={before['matched']:>6} / {before['total']}  "
              f"({100*before['matched']/before['total']:.1f}%)  "
              f"unmatched={before['unmatched']}")

        label = "dry-run" if args.dry_run else "fuzzy"
        print(f"[{label}]  algo={args.algo}  threshold={args.threshold}")

        new_links = run_fuzzy_pass(conn, args.algo, args.threshold, args.dry_run)

        if args.dry_run:
            est = before["matched"] + new_links
            print(f"[result] would-be new links={new_links}  "
                  f"estimated coverage={100*est/before['total']:.1f}%  "
                  f"(+{100*new_links/before['total']:.1f}pp)")
            print("[dry-run] DB unchanged.")
        else:
            after = coverage(conn)
            delta = after["matched"] - before["matched"]
            print(f"[result] new links={new_links}  "
                  f"newly matched products={delta}  "
                  f"({100*after['matched']/after['total']:.1f}% total coverage)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
