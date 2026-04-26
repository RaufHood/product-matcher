"""
Count word frequencies across all market model_name columns.
Words that appear very often are spec/noise tokens — candidates for NOISE_PATTERN.

Usage:
    python scripts/top_model_words.py
    python scripts/top_model_words.py --top 50
"""

import argparse
import collections
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MARKET_FILES = [
    ROOT / "data" / "final_market_a_eu_catalog.csv",
    ROOT / "data" / "final_market_b_us_catalog.csv",
    ROOT / "data" / "final_market_c_es_catalog.csv",
    ROOT / "data" / "final_market_d_ch_catalog.csv",
]

# Already handled by NOISE_PATTERN in cleaning.py — skip these in output
ALREADY_KNOWN = {
    "gb", "tb", "dual", "sim", "starter", "kit",
    "refurbished", "bundle", "lite", "gen",
}


def detect_delimiter(path: Path) -> str:
    with path.open(encoding="utf-8-sig") as f:
        first = f.readline()
    return ";" if (";" in first and "," not in first) else ","


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args()

    counts: collections.Counter = collections.Counter()
    total_rows = 0

    for path in MARKET_FILES:
        delim = detect_delimiter(path)
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=delim):
                name = row.get("model_name", "")
                words = re.findall(r"[a-zA-Z]+", name.lower())
                counts.update(words)
                total_rows += 1

    print(f"Scanned {total_rows} rows across {len(MARKET_FILES)} markets.\n")
    print(f"{'Rank':>5}  {'Word':20s}  {'Count':>7}  {'Note'}")
    print("-" * 55)

    rank = 0
    for word, count in counts.most_common(args.top * 2):
        if rank >= args.top:
            break
        note = "already in NOISE_PATTERN" if word in ALREADY_KNOWN else "NEW — consider adding?"
        rank += 1
        print(f"{rank:>5}  {word:20s}  {count:>7}  {note}")


if __name__ == "__main__":
    main()
