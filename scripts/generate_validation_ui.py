"""
Reads electropulse.db, pulls 100 cross-market matched pairs, writes
a standalone data/validation_ui.html for browser-based validation.

Usage:
    python scripts/generate_validation_ui.py
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT     = Path(__file__).resolve().parent.parent
DB_PATH  = ROOT / "electropulse.db"
OUT_PATH = ROOT / "data" / "validation_ui.html"

QUERY = """
SELECT
    sp1.id AS anchor_id,
    m1.market_code AS anchor_market,
    sp1.raw_model_name AS anchor_raw,
    sp1.normalized_model_name AS anchor_norm,
    sp1.raw_manufacturer_of_record AS anchor_mfr,
    sp1.normalized_core_components AS anchor_comp,
    spm1.match_type,
    sp2.id AS match_id,
    m2.market_code AS match_market,
    sp2.raw_model_name AS match_raw,
    sp2.normalized_model_name AS match_norm,
    sp2.raw_manufacturer_of_record AS match_mfr,
    sp2.normalized_core_components AS match_comp,
    mo.canonical_model_name
FROM source_product_models spm1
JOIN source_product_models spm2 ON spm1.model_id = spm2.model_id
JOIN source_products sp1 ON spm1.source_product_id = sp1.id
JOIN source_products sp2 ON spm2.source_product_id = sp2.id
JOIN markets m1 ON sp1.market_id = m1.id
JOIN markets m2 ON sp2.market_id = m2.id
JOIN models mo ON spm1.model_id = mo.id
WHERE sp1.id < sp2.id
  AND m1.market_code != m2.market_code
  AND spm1.match_type != 'bundle_part'
  AND spm2.match_type != 'bundle_part'
ORDER BY RANDOM()
LIMIT 100
"""

HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Match Validation</title>
<style>
*{box-sizing:border-box}
body{font-family:sans-serif;max-width:920px;margin:28px auto;padding:0 16px;color:#222}
h2{margin:0 0 12px}
#pbar-wrap{height:6px;background:#eee;border-radius:3px;margin-bottom:14px}
#pbar{height:6px;background:#43a047;border-radius:3px;transition:width .3s}
#nav{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap}
#nav button{padding:6px 16px;border:1px solid #bbb;border-radius:5px;cursor:pointer;background:#fff}
#nav button:hover{background:#f5f5f5}
#ctr{color:#666;font-size:.9em}
#results-btn{margin-left:auto;background:#1565c0;color:#fff;border:none!important;font-weight:600}
#results-btn:hover{background:#0d47a1!important}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
.box{border:1px solid #e0e0e0;border-radius:7px;padding:14px}
.mkt-badge{display:inline-block;background:#eeeeee;border-radius:3px;padding:1px 8px;font-size:.75em;font-weight:700;margin-right:6px}
.name{font-size:1.05em;font-weight:600;margin-bottom:6px}
.row{font-size:.85em;color:#555;margin:2px 0}
.badge{display:inline-block;border-radius:3px;padding:1px 8px;font-size:.75em;font-weight:700;color:#fff}
.badge.direct{background:#1565c0}
.badge.fuzzy{background:#e65100}
.badge.bundle_part{background:#6a1b9a}
.canonical{font-size:.82em;color:#888;margin-top:6px}
.verdicts{display:flex;gap:10px;justify-content:center;margin-bottom:10px}
.v-btn{flex:1;max-width:160px;padding:9px;border-radius:6px;border:2px solid transparent;cursor:pointer;font-size:.95em;font-weight:600;transition:all .15s}
.v-btn.correct{background:#e8f5e9;border-color:#a5d6a7;color:#2e7d32}
.v-btn.wrong{background:#ffebee;border-color:#ef9a9a;color:#c62828}
.v-btn.unsure{background:#f5f5f5;border-color:#bdbdbd;color:#555}
.v-btn.sel.correct{background:#43a047;color:#fff;border-color:#2e7d32}
.v-btn.sel.wrong{background:#e53935;color:#fff;border-color:#c62828}
.v-btn.sel.unsure{background:#757575;color:#fff;border-color:#555}
.hint{text-align:center;font-size:.78em;color:#aaa;margin-bottom:6px}
/* results */
#results{display:none}
#results h3{margin-bottom:10px}
table{border-collapse:collapse;width:100%;font-size:.9em}
th,td{padding:7px 10px;border:1px solid #e0e0e0;text-align:left}
th{background:#f5f5f5;font-weight:600}
#exp-btn{margin-top:14px;padding:8px 20px;background:#1565c0;color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:600}
#exp-btn:hover{background:#0d47a1}
#back-btn{margin-top:10px;margin-left:10px;padding:8px 20px;background:#fff;border:1px solid #bbb;border-radius:5px;cursor:pointer}
</style>
</head>
<body>
<h2>Match Validation</h2>
<div id="pbar-wrap"><div id="pbar" style="width:0%"></div></div>
<div id="nav">
  <button onclick="go(-1)">&#8592; Prev</button>
  <button onclick="go(1)">Next &#8594;</button>
  <span id="ctr"></span>
  <button id="results-btn" onclick="showResults()">See Results</button>
</div>
<div id="card"></div>
<div id="results">
  <h3>Results</h3>
  <div id="summary"></div>
  <button id="exp-btn" onclick="exportCSV()">&#8595; Export CSV</button>
  <button id="back-btn" onclick="hideResults()">&#8592; Back</button>
</div>
<script>
const D=__DATA__;
const V={};  // index -> 'correct'|'wrong'|'unsure'
let i=0;

function reviewed(){return Object.keys(V).length;}

function render(){
  const p=D[i];
  const v=V[i]||null;
  const done=reviewed();
  document.getElementById("pbar").style.width=(done/D.length*100)+"%";
  document.getElementById("ctr").textContent=(i+1)+"/"+D.length+"  ("+done+" reviewed)";

  const mt=p.match_type||"";
  const html=`
<div class="pair">
  <div class="box">
    <div class="name"><span class="mkt-badge">${e(p.anchor_market)}</span>${e(p.anchor_raw)}</div>
    <div class="row">norm: ${e(p.anchor_norm)||"—"}</div>
    <div class="row">mfr: ${e(p.anchor_mfr)||"—"}</div>
    <div class="row">comp: ${e(p.anchor_comp)||"—"}</div>
  </div>
  <div class="box">
    <div class="name"><span class="mkt-badge">${e(p.match_market)}</span>${e(p.match_raw)}</div>
    <div class="row">norm: ${e(p.match_norm)||"—"}</div>
    <div class="row">mfr: ${e(p.match_mfr)||"—"}</div>
    <div class="row">comp: ${e(p.match_comp)||"—"}</div>
    <div class="canonical">canonical: ${e(p.canonical_model_name)}&nbsp;&nbsp;<span class="badge ${e(mt)}">${e(mt)}</span></div>
  </div>
</div>
<div class="verdicts">
  <button class="v-btn correct${v==='correct'?' sel':''}" onclick="verdict('correct')">&#10003; Correct</button>
  <button class="v-btn wrong${v==='wrong'?' sel':''}" onclick="verdict('wrong')">&#10007; Wrong</button>
  <button class="v-btn unsure${v==='unsure'?' sel':''}" onclick="verdict('unsure')">? Unsure</button>
</div>
<div class="hint">&#8592;/N = wrong &nbsp;|&nbsp; &#8594;/Y = correct &nbsp;|&nbsp; U = unsure</div>`;
  document.getElementById("card").innerHTML=html;
}

function verdict(v){
  V[i]=v;
  render();
  if(i<D.length-1)setTimeout(()=>go(1),180);
}

function go(d){
  i=Math.max(0,Math.min(D.length-1,i+d));
  render();
}

function e(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

document.addEventListener("keydown",ev=>{
  if(ev.key==="ArrowRight"||ev.key.toLowerCase()==="y")verdict("correct");
  else if(ev.key==="ArrowLeft"||ev.key.toLowerCase()==="n")verdict("wrong");
  else if(ev.key.toLowerCase()==="u")verdict("unsure");
});

function counts(){
  const c={correct:0,wrong:0,unsure:0};
  for(const v of Object.values(V))c[v]=(c[v]||0)+1;
  return c;
}

function showResults(){
  document.getElementById("card").style.display="none";
  document.getElementById("nav").style.display="none";
  document.getElementById("results").style.display="block";

  const total=reviewed(), c=counts();
  const pct=n=>total?Math.round(n/total*100):0;

  // by match_type
  const byType={};
  for(const[idx,v] of Object.entries(V)){
    const mt=D[idx].match_type||"other";
    if(!byType[mt])byType[mt]={correct:0,wrong:0,unsure:0,total:0};
    byType[mt][v]++;byType[mt].total++;
  }
  // by market pair
  const byMkt={};
  for(const[idx,v] of Object.entries(V)){
    const p=D[idx];
    const key=[p.anchor_market,p.match_market].sort().join("-");
    if(!byMkt[key])byMkt[key]={correct:0,wrong:0,unsure:0,total:0};
    byMkt[key][v]++;byMkt[key].total++;
  }

  let h=`<table><tr><th>Metric</th><th>Count</th><th>%</th></tr>
<tr><td>Total reviewed</td><td>${total}</td><td>${pct(total)} of ${D.length}</td></tr>
<tr><td>&#10003; Correct</td><td>${c.correct}</td><td>${pct(c.correct)}%</td></tr>
<tr><td>&#10007; Wrong</td><td>${c.wrong}</td><td>${pct(c.wrong)}%</td></tr>
<tr><td>? Unsure</td><td>${c.unsure}</td><td>${pct(c.unsure)}%</td></tr>
</table><br>
<table><tr><th>Match type</th><th>Reviewed</th><th>Correct</th><th>Wrong</th><th>Unsure</th></tr>`;
  for(const[mt,r] of Object.entries(byType))
    h+=`<tr><td>${e(mt)}</td><td>${r.total}</td><td>${r.correct}</td><td>${r.wrong}</td><td>${r.unsure}</td></tr>`;
  h+=`</table><br><table><tr><th>Market pair</th><th>Reviewed</th><th>Correct</th><th>Wrong</th><th>Unsure</th></tr>`;
  for(const[mp,r] of Object.entries(byMkt))
    h+=`<tr><td>${e(mp)}</td><td>${r.total}</td><td>${r.correct}</td><td>${r.wrong}</td><td>${r.unsure}</td></tr>`;
  h+=`</table>`;
  document.getElementById("summary").innerHTML=h;
}

function hideResults(){
  document.getElementById("results").style.display="none";
  document.getElementById("card").style.display="block";
  document.getElementById("nav").style.display="flex";
  render();
}

function exportCSV(){
  const hdr=["anchor_id","match_id","anchor_market","match_market","anchor_raw","match_raw","anchor_norm","match_norm","match_type","canonical_model_name","verdict"];
  const rows=[hdr.join(",")];
  for(const[idx,v] of Object.entries(V)){
    const p=D[idx];
    rows.push([p.anchor_id,p.match_id,p.anchor_market,p.match_market,
      q(p.anchor_raw),q(p.match_raw),q(p.anchor_norm),q(p.match_norm),
      p.match_type,q(p.canonical_model_name),v].join(","));
  }
  const blob=new Blob([rows.join("\\n")],{type:"text/csv"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download="validation_results.csv";a.click();
}

function q(s){return '"'+String(s||"").replace(/"/g,'""')+'"';}

render();
</script>
</body>
</html>
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(QUERY).fetchall()
    finally:
        conn.close()

    data = [dict(r) for r in rows]
    print(f"[gen] {len(data)} pairs fetched")

    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"[gen] written -> {OUT_PATH}")
    print(f"[gen] open: file://{OUT_PATH}")


if __name__ == "__main__":
    main()
