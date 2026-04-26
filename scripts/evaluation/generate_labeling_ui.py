"""
For each product in data/manual_candidates.csv, find the top-5 best-matching
products from other markets using fuzzy name similarity (rapidfuzz).
Writes a standalone data/labeling_ui.html — open in any browser, no server needed.

Usage:
    python scripts/generate_labeling_ui.py
    python scripts/generate_labeling_ui.py --threshold 45 --top 5
"""

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

import sys

from rapidfuzz import fuzz, process as rfprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT              = Path(__file__).resolve().parent.parent
DB_PATH           = ROOT / "electropulse.db"
CANDIDATES_PATH   = ROOT / "data" / "manual_candidates.csv"
OUTPUT_HTML_PATH  = ROOT / "data" / "labeling_ui.html"


# ── data loading ──────────────────────────────────────────────────────────────

def load_all_products(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Load source products grouped by market, with their component strings."""
    rows = conn.execute(
        """
        SELECT sp.id, m.market_code, sp.raw_model_name, sp.normalized_model_name,
               sp.raw_manufacturer_of_record, sp.normalized_core_components
        FROM source_products sp
        JOIN markets m ON sp.market_id = m.id
        ORDER BY sp.id
        """
    ).fetchall()

    by_market: dict[str, list[dict]] = {}
    for id_, mkt, raw_name, norm_name, mfr, components in rows:
        by_market.setdefault(mkt, []).append({
            "id":         id_,
            "market":     mkt,
            "raw_name":   raw_name or "",
            "norm_name":  norm_name or "",
            "mfr":        mfr or "",
            "components": components or "",
        })
    return by_market


def load_manual_candidates() -> list[dict]:
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(f"{CANDIDATES_PATH} not found — run generate_eval.py first.")
    with CANDIDATES_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── candidate search ──────────────────────────────────────────────────────────

_BUNDLE_SEP = re.compile(r"\s+and\s+|\s*/\s*", flags=re.IGNORECASE)

def _is_bundle(raw_name: str) -> bool:
    """Exclude bundle rows — they score 100% via token subset matching, polluting results."""
    return len(_BUNDLE_SEP.split(raw_name)) > 1


def _score(anchor_name: str, anchor_components: str,
           cand_name: str, cand_components: str) -> float:
    """
    Blended score: 65% name similarity + 35% component similarity.
    - Both have components  → full blend.
    - Only anchor has them  → 15% penalty on name score (missing component data is a red flag).
    - Neither has them      → name score only.
    Name similarity itself is the average of token_set_ratio and token_sort_ratio so that
    subset matches (AzureDock vs AzureDock Pro) don't score 100%.
    """
    name = (fuzz.token_set_ratio(anchor_name, cand_name) +
            fuzz.token_sort_ratio(anchor_name, cand_name)) / 2

    if anchor_components and cand_components:
        comp = fuzz.token_set_ratio(anchor_components, cand_components)
        return name * 0.65 + comp * 0.35
    if anchor_components and not cand_components:
        return name * 0.85
    return name


def find_top_candidates(
    anchor_norm_name: str,
    anchor_components: str,
    anchor_market: str,
    by_market: dict[str, list[dict]],
    threshold: int,
    top_k: int,
) -> list[dict]:
    """
    Search all other markets for the best matches to the anchor.
    Score = blended name + component similarity (see _score).
    Excludes bundle entries from the candidate pool.
    """
    all_hits: list[dict] = []

    for market, products in by_market.items():
        if market == anchor_market:
            continue

        for p in products:
            if _is_bundle(p["raw_name"]):
                continue
            score = _score(anchor_norm_name, anchor_components,
                           p["norm_name"], p["components"])
            if score >= threshold:
                cand = dict(p)
                cand["score"] = round(score / 100, 4)
                all_hits.append(cand)

    all_hits.sort(key=lambda x: -x["score"])
    return all_hits[:top_k]


# ── HTML generation ───────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Match Labeling</title>
<style>
*{box-sizing:border-box}
body{font-family:sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#222}
h2{margin-bottom:4px}
#bar{display:flex;align-items:center;gap:8px;margin-bottom:18px;flex-wrap:wrap}
#bar button{padding:7px 18px;border:1px solid #bbb;border-radius:5px;cursor:pointer;background:#fff}
#bar button:hover{background:#f5f5f5}
#prog{margin-left:auto;color:#666;font-size:.9em}
#export{background:#1565c0;color:#fff;border:none!important;font-weight:600}
#export:hover{background:#0d47a1!important}
.anchor{background:#f0f4ff;border:1px solid #c5cae9;border-radius:6px;padding:14px;margin-bottom:14px}
.anchor .label{font-size:.75em;background:#3f51b5;color:#fff;border-radius:3px;padding:1px 7px;margin-right:6px}
.anchor .name{font-size:1.05em;font-weight:600}
.anchor .meta{font-size:.85em;color:#555;margin-top:4px}
.cands-header{font-size:.85em;font-weight:600;color:#888;margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em}
.cand{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border:1px solid #e0e0e0;border-radius:5px;margin-bottom:7px;transition:background .15s}
.cand.on{background:#e8f5e9;border-color:#a5d6a7}
.sc{min-width:38px;font-size:.82em;color:#888;padding-top:2px}
.inf{flex:1;font-size:.9em;line-height:1.5}
.mkt{display:inline-block;background:#eeeeee;border-radius:3px;padding:0 6px;font-size:.78em;margin-right:5px;font-weight:600}
.cand.on .mkt{background:#c8e6c9}
.tick{border:none;border-radius:4px;cursor:pointer;padding:6px 13px;font-size:.95em;font-weight:600}
.cand:not(.on) .tick{background:#e0e0e0;color:#333}
.cand.on .tick{background:#43a047;color:#fff}
.empty{color:#aaa;font-style:italic;font-size:.9em;padding:8px 0}
</style>
</head>
<body>
<h2>Match Labeling</h2>
<div id="bar">
  <button onclick="go(-1)">&#8592; Prev</button>
  <button onclick="go(1)">Next &#8594;</button>
  <span id="prog"></span>
  <button id="export" onclick="exportCSV()">&#8595; Export CSV</button>
</div>
<div id="card"></div>
<script>
const D=__DATA__;
let i=0;
const M={};  // anchorId -> Set of candidate indices

function saved(){return Object.values(M).reduce((s,v)=>s+v.size,0)}

function render(){
  const it=D[i], a=it.anchor;
  const ms=M[a.id]||new Set();
  document.getElementById("prog").textContent=
    (i+1)+"/"+D.length+" — "+saved()+" match"+(saved()===1?"":"es")+" saved";
  let h=`<div class="anchor">
    <span class="label">${a.market}</span><span class="name">${esc(a.raw_name)}</span>
    <div class="meta">norm: ${esc(a.norm_name)}</div>
    <div class="meta">mfr: ${esc(a.mfr)}</div>
    <div class="meta">comp: ${esc(a.components)||"—"}</div>
  </div><div class="cands-header">Candidates (click ✓ to mark as match)</div>`;
  if(!it.candidates.length){h+='<div class="empty">No candidates found above threshold.</div>';}
  it.candidates.forEach((c,ci)=>{
    const on=ms.has(ci);
    h+=`<div class="cand${on?" on":""}" id="cd${ci}">
      <span class="sc">${Math.round(c.score*100)}%</span>
      <div class="inf">
        <span class="mkt">${c.market}</span><b>${esc(c.raw_name)}</b><br>
        <small style="color:#888">norm: ${esc(c.norm_name)}</small><br>
        mfr: ${esc(c.mfr)}<br>comp: ${esc(c.components)||"—"}
      </div>
      <button class="tick" onclick="tog(${ci})">${on?"✓ matched":"✓"}</button>
    </div>`;
  });
  document.getElementById("card").innerHTML=h;
}

function tog(ci){
  const id=D[i].anchor.id;
  if(!M[id])M[id]=new Set();
  M[id].has(ci)?M[id].delete(ci):M[id].add(ci);
  render();
}

function go(d){i=Math.max(0,Math.min(D.length-1,i+d));render();}

function esc(s){
  return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function exportCSV(){
  const hdr=["id_a","id_b","market_a","market_b","name_a","name_b","norm_name_a","norm_name_b","label","match_type","notes"];
  const rows=[hdr.join(",")];
  for(const[aid,idxSet]of Object.entries(M)){
    const it=D.find(d=>String(d.anchor.id)===String(aid));
    if(!it)continue;
    const a=it.anchor;
    for(const ci of idxSet){
      const c=it.candidates[ci];
      const r=[a.id,c.id,a.market,c.market,
        q(a.raw_name),q(c.raw_name),q(a.norm_name),q(c.norm_name),
        1,"manual",""].join(",");
      rows.push(r);
    }
  }
  const blob=new Blob([rows.join("\\n")],{type:"text/csv"});
  const el=document.createElement("a");
  el.href=URL.createObjectURL(blob);
  el.download="manual_eval_pairs.csv";
  el.click();
}

function q(s){return '"'+String(s||"").replace(/"/g,'""')+'"';}

document.addEventListener("keydown",e=>{
  if(e.key==="ArrowRight")go(1);
  if(e.key==="ArrowLeft")go(-1);
});

render();
</script>
</body>
</html>
"""


def build_data(
    anchors: list[dict],
    by_market: dict[str, list[dict]],
    threshold: int,
    top_k: int,
) -> list[dict]:
    data = []
    total = len(anchors)
    for idx, row in enumerate(anchors):
        print(f"  [{idx+1}/{total}] {row['market']} — {row['raw_model_name'][:50]}", end="\r")
        candidates = find_top_candidates(
            anchor_norm_name=row["normalized_model_name"],
            anchor_components=row["raw_core_components"],
            anchor_market=row["market"],
            by_market=by_market,
            threshold=threshold,
            top_k=top_k,
        )
        data.append({
            "anchor": {
                "id":         int(row["id"]),
                "market":     row["market"],
                "raw_name":   row["raw_model_name"],
                "norm_name":  row["normalized_model_name"],
                "mfr":        row["manufacturer"],
                "components": row["raw_core_components"],
            },
            "candidates": candidates,
        })
    print()
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=50,
                        help="Min fuzzy score (0-100) for a candidate to appear")
    parser.add_argument("--top", type=int, default=5,
                        help="Max candidates to show per anchor product")
    args = parser.parse_args()

    anchors = load_manual_candidates()
    print(f"[gen] {len(anchors)} anchor products loaded from {CANDIDATES_PATH.name}")

    conn = sqlite3.connect(DB_PATH)
    try:
        by_market = load_all_products(conn)
        total = sum(len(v) for v in by_market.values())
        print(f"[gen] {total} products loaded across {len(by_market)} markets")
        print(f"[gen] searching for candidates (threshold={args.threshold}, top={args.top})...")

        data = build_data(anchors, by_market, args.threshold, args.top)
    finally:
        conn.close()

    with_candidates = sum(1 for d in data if d["candidates"])
    print(f"[gen] {with_candidates}/{len(data)} anchors have at least one candidate")

    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))

    OUTPUT_HTML_PATH.write_text(html, encoding="utf-8")
    print(f"[gen] written -> {OUTPUT_HTML_PATH}")
    print(f"[gen] open in browser: file://{OUTPUT_HTML_PATH}")


if __name__ == "__main__":
    main()
