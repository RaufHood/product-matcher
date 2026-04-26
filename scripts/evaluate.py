"""
Evaluate the matching pipeline against data/eval_pairs.csv.

What this script does
---------------------
1. Loads all source products + their components from the DB
2. Scores every pair in eval_pairs.csv:
     score = w1 * name_similarity          (rapidfuzz token_set_ratio)
           + w2 * component_overlap        (Jaccard on canonical component sets)
           + w3 * manufacturer_match       (exact=1.0  family~=0.5  different=0.0)
   Equal weights (1/3 each) to start.
3. Reports blocking recall (% of positive pairs that share a manufacturer or first token)
4. Sweeps thresholds 0.50->0.95, prints Precision/Recall/F1 table
5. --plot: saves and shows a two-panel matplotlib figure

Usage
-----
    python scripts/evaluate.py
    python scripts/evaluate.py --plot
    python scripts/evaluate.py --weights 0.5 0.3 0.2   # tune name/comp/mfr weights
"""

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz as _rfuzz

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT          = Path(__file__).resolve().parent.parent
DB_PATH       = ROOT / "electropulse.db"
EVAL_PATH     = ROOT / "data" / "eval_pairs.csv"
PLOT_OUT_PATH = ROOT / "data" / "eval_results.png"


# ── similarity helpers ────────────────────────────────────────────────────────

def name_sim(a: str, b: str) -> float:
    return _rfuzz.token_set_ratio(a or "", b or "") / 100.0


def jaccard(set_a: set, set_b: set) -> float:
    """Component overlap. Both empty → 0.0 (no signal, not a match indicator)."""
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def mfr_score(name_a: str, name_b: str, id_a: int | None, id_b: int | None) -> float:
    if id_a is not None and id_a == id_b:
        return 1.0
    # family similarity — e.g. "Harbor Systems Inc." vs "Harbor Holdings Inc."
    if name_sim(name_a, name_b) >= 0.6:
        return 0.5
    return 0.0


def score_pair(pa: dict, pb: dict, mfr_names: dict, w: tuple) -> dict:
    ns = name_sim(pa["norm_name"], pb["norm_name"])
    co = jaccard(pa["components"], pb["components"])
    ms = mfr_score(
        mfr_names.get(pa["mfr_id"], pa["raw_mfr"]),
        mfr_names.get(pb["mfr_id"], pb["raw_mfr"]),
        pa["mfr_id"], pb["mfr_id"],
    )
    total = w[0] * ns + w[1] * co + w[2] * ms
    return {"name_sim": ns, "comp_overlap": co, "mfr_match": ms, "score": total}


# ── blocking ──────────────────────────────────────────────────────────────────

def survives_blocking(pa: dict, pb: dict) -> bool:
    same_mfr   = pa["mfr_id"] is not None and pa["mfr_id"] == pb["mfr_id"]
    same_token = bool(pa["first_token"]) and pa["first_token"] == pb["first_token"]
    return same_mfr or same_token


# ── DB loaders ────────────────────────────────────────────────────────────────

def load_products(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        SELECT sp.id, m.market_code, sp.normalized_model_name,
               sp.raw_manufacturer_of_record, sp.manufacturer_id
        FROM source_products sp
        JOIN markets m ON sp.market_id = m.id
        """
    ).fetchall()
    products = {}
    for id_, mkt, norm, raw_mfr, mfr_id in rows:
        first = (norm or "").split()[0].lower() if norm else ""
        products[id_] = {
            "market": mkt, "norm_name": norm or "",
            "raw_mfr": raw_mfr or "", "mfr_id": mfr_id,
            "first_token": first, "components": set(),
        }
    return products


def load_components(conn: sqlite3.Connection, products: dict) -> None:
    rows = conn.execute(
        """
        SELECT spc.source_product_id, c.canonical_name
        FROM source_product_components spc
        JOIN components c ON spc.component_id = c.id
        """
    ).fetchall()
    for pid, cname in rows:
        if pid in products:
            products[pid]["components"].add(cname.lower())


def load_mfr_names(conn: sqlite3.Connection) -> dict:
    return dict(conn.execute("SELECT id, canonical_name FROM manufacturers").fetchall())


def load_eval_pairs(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run generate_eval.py first.")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(scored: list[dict], threshold: float) -> dict:
    tp = fp = fn = tn = 0
    for s in scored:
        pred   = s["score"] >= threshold
        actual = int(s["label"]) == 1
        if pred and actual:     tp += 1
        elif pred and not actual: fp += 1
        elif not pred and actual: fn += 1
        else:                     tn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return dict(threshold=threshold, precision=precision, recall=recall,
                f1=f1, tp=tp, fp=fp, fn=fn, tn=tn)


# ── reporting ─────────────────────────────────────────────────────────────────

def report_score_breakdown(scored: list[dict]) -> None:
    positives = [s for s in scored if s["label"] == 1]
    negatives = [s for s in scored if s["label"] == 0]

    label_dist = f"  label=1: {len(positives)}   label=0: {len(negatives)}"
    if not negatives:
        label_dist += "  [!] no negatives yet — add label=0 pairs to eval_pairs.csv for full precision"
    print(f"\n=== Label distribution ===\n{label_dist}")

    if positives:
        sc = [s["score"] for s in positives]
        ns = [s["name_sim"] for s in positives]
        co = [s["comp_overlap"] for s in positives]
        ms = [s["mfr_match"] for s in positives]
        print(f"\n=== Score breakdown (label=1, n={len(positives)}) ===")
        print(f"  {'':15s} {'min':>6} {'mean':>6} {'max':>6}")
        print(f"  {'score':15s} {min(sc):>6.3f} {sum(sc)/len(sc):>6.3f} {max(sc):>6.3f}")
        print(f"  {'name_sim':15s} {min(ns):>6.3f} {sum(ns)/len(ns):>6.3f} {max(ns):>6.3f}")
        print(f"  {'comp_overlap':15s} {min(co):>6.3f} {sum(co)/len(co):>6.3f} {max(co):>6.3f}")
        print(f"  {'mfr_match':15s} {min(ms):>6.3f} {sum(ms)/len(ms):>6.3f} {max(ms):>6.3f}")

    # Blocking recall
    pos_surviving = sum(1 for s in positives if s["survives_blocking"])
    if positives:
        print(f"\n=== Blocking recall ===")
        print(f"  {pos_surviving}/{len(positives)} positive pairs survive blocking ({pos_surviving/len(positives):.1%})")
        if pos_surviving < len(positives):
            print(f"  Pairs blocked out (will never be found at any threshold):")
            for s in positives:
                if not s["survives_blocking"]:
                    print(f"    [{s['market_a']}] '{s['name_a']}' <-> [{s['market_b']}] '{s['name_b']}'")

    # Worst-scoring positives (hardest cases)
    worst = sorted(positives, key=lambda x: x["score"])[:5]
    if worst:
        print(f"\n=== Lowest-scoring positive pairs (hardest for the algorithm) ===")
        for s in worst:
            block = "blocks:yes" if s["survives_blocking"] else "blocks:NO"
            print(f"  score={s['score']:.3f} ns={s['name_sim']:.2f} co={s['comp_overlap']:.2f} mfr={s['mfr_match']:.2f} {block}")
            print(f"    [{s['market_a']}] {s['name_a']}")
            print(f"    [{s['market_b']}] {s['name_b']}")


def report_threshold_sweep(results: list[dict]) -> None:
    best_f1 = max(r["f1"] for r in results)
    print(f"\n=== Threshold sweep ===")
    print(f"  {'Thresh':>7} {'Prec':>7} {'Recall':>7} {'F1':>7} {'TP':>5} {'FP':>5} {'FN':>5}")
    print(f"  {'-'*50}")
    for r in results:
        marker = " <-- best F1" if r["f1"] == best_f1 else ""
        print(
            f"  {r['threshold']:>7.2f} {r['precision']:>7.3f} {r['recall']:>7.3f} "
            f"{r['f1']:>7.3f} {r['tp']:>5} {r['fp']:>5} {r['fn']:>5}{marker}"
        )


# ── plot ──────────────────────────────────────────────────────────────────────

def plot_results(results: list[dict], scored: list[dict]) -> None:
    import matplotlib.pyplot as plt

    thresholds = [r["threshold"]  for r in results]
    precisions = [r["precision"]  for r in results]
    recalls    = [r["recall"]     for r in results]
    f1s        = [r["f1"]         for r in results]
    best_t     = thresholds[f1s.index(max(f1s))]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("Matching evaluation — equal weights (name 1/3 + component 1/3 + manufacturer 1/3)", fontsize=11)

    # Panel 1: P / R / F1 vs threshold
    ax1.plot(thresholds, precisions, "b-o", label="Precision", linewidth=2)
    ax1.plot(thresholds, recalls,    "r-o", label="Recall",    linewidth=2)
    ax1.plot(thresholds, f1s,        "g-o", label="F1",        linewidth=2, zorder=5)
    ax1.axvline(best_t, color="gray", linestyle="--", alpha=0.6, label=f"Best F1 @ {best_t:.2f}")
    ax1.set_xlabel("Threshold")
    ax1.set_ylabel("Score")
    ax1.set_title("Precision / Recall / F1 vs Threshold")
    ax1.legend()
    ax1.set_ylim(0, 1.05)
    ax1.grid(alpha=0.3)

    # Panel 2: score histogram by label
    pos_scores = [s["score"] for s in scored if s["label"] == 1]
    neg_scores = [s["score"] for s in scored if s["label"] == 0]
    bins = [i * 0.05 for i in range(21)]

    if pos_scores:
        ax2.hist(pos_scores, bins=bins, alpha=0.65, color="steelblue", label=f"Positive  n={len(pos_scores)}")
    if neg_scores:
        ax2.hist(neg_scores, bins=bins, alpha=0.65, color="tomato",    label=f"Negative  n={len(neg_scores)}")
    else:
        ax2.text(0.5, 0.5, "Add label=0 pairs\nto eval_pairs.csv\nto see negatives",
                 ha="center", va="center", transform=ax2.transAxes, fontsize=11, color="gray",
                 style="italic")
    ax2.axvline(best_t, color="gray", linestyle="--", alpha=0.6, label=f"Best F1 threshold")
    ax2.set_xlabel("Composite score")
    ax2.set_ylabel("Count")
    ax2.set_title("Score Distribution by Label")
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(PLOT_OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"\n[plot] saved -> {PLOT_OUT_PATH}")
    plt.show()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot",    action="store_true", help="Save and show P/R/F1 plot")
    parser.add_argument("--weights", nargs=3, type=float, default=[1/3, 1/3, 1/3],
                        metavar=("W_NAME", "W_COMP", "W_MFR"),
                        help="Scoring weights (must sum to 1). Default: equal thirds.")
    args = parser.parse_args()

    w = tuple(args.weights)
    w_sum = sum(w)
    if abs(w_sum - 1.0) > 0.01:
        print(f"[warn] weights sum to {w_sum:.3f}, normalizing to 1.0")
        w = tuple(x / w_sum for x in w)
    print(f"[config] weights  name={w[0]:.3f}  component={w[1]:.3f}  manufacturer={w[2]:.3f}")

    eval_pairs = load_eval_pairs(EVAL_PATH)
    print(f"[data] {len(eval_pairs)} eval pairs loaded from {EVAL_PATH.name}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        products  = load_products(conn)
        load_components(conn, products)
        mfr_names = load_mfr_names(conn)
        print(f"[data] {len(products)} source products  |  {sum(len(p['components']) for p in products.values())} component links")

        # Score all eval pairs
        scored = []
        missing = 0
        for pair in eval_pairs:
            id_a, id_b = int(pair["id_a"]), int(pair["id_b"])
            if id_a not in products or id_b not in products:
                missing += 1
                continue
            pa, pb = products[id_a], products[id_b]
            s = score_pair(pa, pb, mfr_names, w)
            s.update({
                "label":             int(pair["label"]),
                "id_a": id_a,        "id_b": id_b,
                "market_a":          pa["market"],
                "market_b":          pb["market"],
                "name_a":            pair.get("name_a", ""),
                "name_b":            pair.get("name_b", ""),
                "survives_blocking": survives_blocking(pa, pb),
            })
            scored.append(s)

        if missing:
            print(f"[warn] {missing} pairs skipped — IDs not found in DB (re-run main.py?)")

        report_score_breakdown(scored)

        thresholds = [round(0.50 + i * 0.05, 2) for i in range(10)]
        results    = [compute_metrics(scored, t) for t in thresholds]
        report_threshold_sweep(results)

        if args.plot:
            plot_results(results, scored)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
