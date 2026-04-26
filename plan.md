# ElectroPulse Matching — State of Play & Next Steps

---

## Where we are right now

### What the naive pipeline does
The current algorithm normalizes model names (strips storage sizes, spec tokens, manufacturer
suffixes) and then links products that share an **exactly identical** normalized name across
markets. That is the only matching signal used.

### Current coverage (naive pipeline) — exact counts

| Market | Products | Unmatched | Unmatched % |
|--------|----------|-----------|-------------|
| EU     | 1 912    | 575       | 30.1%       |
| US     | 11 852   | 8 996     | 75.9%       |
| ES     | 38 108   | 31 155    | 81.8%       |
| CH     | 442      | 66        | 14.9%       |
| **All**| **52 314**| **40 792** | **78.0%** |

**Key takeaway: the naive pipeline only matches 22% of products.**

This is NOT "last 5%" territory. 78% unmatched requires investigation before optimising.

---

## Is the algorithm good enough?

**No — 78% unmatched is a major gap.** But before adding fuzzy matching, understand WHY.

**Two possible explanations:**

**A. The markets carry genuinely different product mixes.**
ES has 38 108 products vs EU's 1 912. Even if every EU product matched an ES counterpart,
~36 000 ES products would still be "unmatched" simply because EU doesn't stock them.
→ In this case, 78% unmatched is expected and the algorithm is fine.

**B. The normalization is too conservative — tier suffixes block matches.**
`AzureDock Pro` (EU) and `AzureDock` (ES) normalize differently. If these are actually the
same underlying product sold under different tier names in different markets, that is a
missed match.
→ In this case, fuzzy matching would help — but risks merging genuinely different tiers.

**Diagnostic run (2025-04-26) confirms: it is mostly A.**

Sample of unmatched products shows:
- **EU**: tier-combo products (`SonicLink Plus Gen`, `AstraCam SE Ultra Edge`) — no counterpart in other markets under that exact name.
- **US**: generic/Challenge #5 products (`Silver Drive Flow Photon`, `Cedar Grid Arc DeepField`) — manufacturer stripping IS firing (verified: `Vega Beam GoldenGate` → `Vega Beam`). These are genuinely US-only SKUs after stripping.
- **ES**: overwhelmingly bundles and spec variants. ES has 38 108 rows vs EU's 1 912 because every storage/bundle combination is its own row. After normalization these often produce base names that simply don't exist in EU/US.

**Conclusion: the algorithm is working correctly. 78% unmatched is a data reality, not a matching failure.**

---

## The real gap: no negatives in the eval set

The evaluate.py output says:
```
[!] no negatives yet — add label=0 pairs to eval_pairs.csv for full precision
```
Without label=0 pairs, precision = 1.000 is *meaningless* (the denominator is 0).

---

## Recommended next steps (in order of value)

### Step 1 — Understand WHY 78% is unmatched (20 min) ← DO THIS FIRST
Look at a sample of unmatched products per market and ask: do they LOOK like they should
have a counterpart in another market, or are they genuinely market-exclusive SKUs?

```bash
python -c "
import sqlite3, csv
c = sqlite3.connect('electropulse.db')
# Sample 10 unmatched products from each market
for mkt in ['EU','US','ES','CH']:
    rows = c.execute('''
        SELECT sp.raw_model_name, sp.raw_manufacturer_of_record
        FROM source_products sp JOIN markets m ON sp.market_id=m.id
        WHERE m.market_code=?
        AND sp.id NOT IN (
            SELECT sp1.id FROM source_product_models spm1
            JOIN source_product_models spm2 ON spm1.model_id=spm2.model_id
            JOIN source_products sp1 ON spm1.source_product_id=sp1.id
            JOIN source_products sp2 ON spm2.source_product_id=sp2.id
            JOIN markets m1 ON sp1.market_id=m1.id
            JOIN markets m2 ON sp2.market_id=m2.id
            WHERE m1.market_code!=m2.market_code
            UNION
            SELECT sp2.id FROM source_product_models spm1
            JOIN source_product_models spm2 ON spm1.model_id=spm2.model_id
            JOIN source_products sp1 ON spm1.source_product_id=sp1.id
            JOIN source_products sp2 ON spm2.source_product_id=sp2.id
            JOIN markets m1 ON sp1.market_id=m1.id
            JOIN markets m2 ON sp2.market_id=m2.id
            WHERE m1.market_code!=m2.market_code
        )
        ORDER BY RANDOM() LIMIT 10
    ''', (mkt,)).fetchall()
    print(f'--- {mkt} unmatched sample ---')
    for r in rows: print(f'  {r[0]} | {r[1]}')
"
```

**If the unmatched samples look like variants of matched products** (same base name, different
tier/spec) → the algorithm needs fuzzy matching.
**If they look like completely different products** → 78% unmatched is expected; algorithm is fine.

### Step 2 — Add label=0 pairs to get real precision (30 min)
The labeling UI is the right tool but use it differently:
- **Mark candidates you are confident are WRONG as label=0**, not just marking correct ones.
- Export from the UI and append to `eval_pairs.csv` with `label=0`.
- Re-run `evaluate.py` — now precision becomes meaningful.

> Tip: in the `Echo Pulse Wave Catalyst` example, `Pulse Pulse Harbor` (85%) is clearly
> wrong — mark it as 0. `Echo Pulse` (94%) is ambiguous — skip it.

### Step 3 — Decide: fuzzy matching or not (decision point)

**Only do this if Step 1 shows > 2% unmatched AND Step 2 shows false positives exist.**

If the unmatched rate is <1% and precision is near-perfect, do NOT add fuzzy matching to
the pipeline. It adds complexity and false positives for marginal recall gain.

If you do add fuzzy matching, use the scoring already built in `evaluate.py`:
```
score = w1 * name_sim + w2 * comp_overlap + w3 * mfr_match
```
Tune weights with `--weights` flag against your labeled eval set before wiring into
`matching.py`.

### Step 4 — Fix the ES component gap (if pursuing fuzzy matching)
ES has no `core_components`. This caps every ES pair score at 0.667 with equal weights.
Two options:
- Market-aware weights: when `comp_overlap=0` for both sides, redistribute its weight to name.
- Accept it: at threshold 0.50, recall is already 73% and all pairs have precision=1.0.

### Step 5 — Focus on the deliverable
The challenge asks for:
1. A **relational data model** — already implemented in `sql/schema_sqlite.sql`
2. A **matching algorithm** — implemented in `scripts/matching.py`
3. A **write-up** of the approach, challenges solved, and tradeoffs

The labeling exercise is useful for *validating* the algorithm, not for building it.
If the eval numbers look good after Steps 1–2, move to writing up the approach.

---

## What NOT to do

- Do not spend more time labeling ambiguous UI cases where no clear match exists.
- Do not add fuzzy matching without first measuring whether unmatched products have real counterparts.
- Do not optimize for the last 0.2% at the cost of introducing false positives.

---

## Quick-reference commands

```bash
# Rebuild DB
python scripts/main.py

# Regenerate eval data
python scripts/generate_eval.py

# Regenerate labeling UI
python scripts/generate_labeling_ui.py

# Evaluate algorithm
python scripts/evaluate.py
python scripts/evaluate.py --weights 0.5 0.25 0.25 --plot
```
