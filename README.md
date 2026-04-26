# ElectroPulse Unified Catalog — Technical Overview

This repository contains a data pipeline that unifies consumer electronics product catalogs from **four market feeds** (EU, US, Spain, Switzerland) by linking products that refer to the same underlying device, even when their model names differ across markets.

---

## Folder Structure

```
database-challenge/
├── data/
│   ├── component_list.json              # Canonical component vocabulary (608 entries)
│   ├── final_market_a_eu_catalog.csv    # Europe source feed
│   ├── final_market_b_us_catalog.csv    # United States source feed
│   ├── final_market_c_es_catalog.csv    # Spain source feed
│   ├── final_market_d_ch_catalog.csv    # Switzerland source feed
│   ├── validation_ui.html               # Browser UI for match review (generated)
│   └── evaluation/
│       ├── eval_pairs.csv               # Labeled pairs for threshold tuning
│       ├── manual_candidates.csv        # Unmatched products flagged for manual review
│       └── eval_results.png             # P/R/F1 plot across thresholds
│
├── scripts/
│   ├── main.py                          # Entry point — runs the full pipeline
│   ├── db.py                            # Database helpers (upsert, schema execution)
│   ├── ingest.py                        # Loads market CSVs into the database
│   ├── cleaning.py                      # Text normalization (spec stripping, manufacturer suffix removal, component splitting)
│   ├── bundles.py                       # Bundle detection and splitting
│   ├── aliases.py                       # Component alias resolution (multilingual → canonical)
│   ├── matching.py                      # Matching orchestrator — ties all steps together
│   ├── fuzzy_match.py                   # Tier-2 fuzzy matching pass
│   ├── evaluate.py                      # Threshold evaluation against labeled pairs
│   ├── generate_validation_ui.py        # Generates browser UI for visual match review
│   ├── exploration/
│   │   └── top_model_words.py           # Word frequency tool (used to identify noise tokens)
│   └── evaluation/
│       ├── generate_eval.py             # Generates eval_pairs.csv and manual_candidates.csv
│       └── generate_labeling_ui.py      # Browser UI for manually labeling unmatched products
│
├── sql/
│   └── schema_sqlite.sql                # Full relational schema (SQLite)
│
├── archive/                             # Superseded monolithic version (kept for reference)
├── images/                             # Screenshots of browser UIs
├── electropulse.db                      # Generated SQLite database (output)
└── README_ELECTROPULSE.md               # This file
```

---

## How to Run

### Prerequisites

```bash
pip install rapidfuzz pandas
```

Python 3.9+ required. No external database server needed — everything runs on SQLite.

### Step 1 — Run the main pipeline

```bash
python scripts/main.py
```

This will:
1. Create (or rebuild) `electropulse.db` from `sql/schema_sqlite.sql`
2. Load all four market CSVs into the `source_products` table
3. Run the full normalization and matching pipeline (cleaning, bundle splitting, alias resolution, exact linking)
4. Print a summary of row counts for each entity type

### Step 2 — Run the fuzzy matching pass

```bash
python scripts/fuzzy_match.py --algo name_comp_mfr --threshold 0.78
```

This adds a second tier of approximate links on top of exact matches. Use `--dry-run` to preview coverage without writing to the database:

```bash
python scripts/fuzzy_match.py --algo name_comp_mfr --threshold 0.78 --dry-run
```

### Step 3 — Generate the validation UI (optional)

```bash
python scripts/generate_validation_ui.py
```

Opens `data/validation_ui.html` in any browser. No server needed. Lets you review 100 random cross-market matches with keyboard shortcuts (→ correct, ← wrong, U = unsure) and export verdicts as CSV.

### Step 4 — Evaluate against labeled pairs (optional)

```bash
python scripts/evaluate.py --plot
```

Runs the scoring function over `data/evaluation/eval_pairs.csv` and prints a precision / recall / F1 table across thresholds 0.50–0.95. `--plot` saves `data/evaluation/eval_results.png`.

---

## Pipeline Overview

```
Market CSVs (4 feeds)
        │
        ▼
   [ingest.py]  ──── raw rows → source_products table
        │
        ▼
  [cleaning.py]  ─── strip spec tokens, resolve manufacturer suffix
        │
        ▼
  [bundles.py]  ──── detect & split bundle entries (e.g. "ModelA and ModelB")
        │
        ▼
  [aliases.py]  ──── resolve component language variants → canonical English
        │
        ▼
 [matching.py]  ──── exact-match linking into models / components tables
        │
        ▼
[fuzzy_match.py] ─── approximate matching for residual unmatched products
        │
        ▼
   electropulse.db   (linked catalog)
```

---

## Cleaning

**Script:** `scripts/cleaning.py`

Handles three distinct cleaning problems.

### 1. Stripping spec tokens and packaging noise

Model names in market feeds often include storage sizes, bundle labels, and regional flags that are not part of the true product name.

| Raw model name | Cleaned |
|---|---|
| `AzureRouter SE Ultra 64GB Starter Kit` | `AzureRouter SE Ultra` |
| `AstraCam 512GB Dual-SIM` | `AstraCam` |
| `AuroraCam 1TB Starter Kit` | `AuroraCam` |
| `Silver Kernel Beam 256GB Starter Kit Copperline` | `Silver Kernel Beam` |

**Removed tokens (regex):** storage sizes (`256GB`, `1TB`), `Dual-SIM`, `Starter Kit`, `Refurbished`, `Bundle`, `Lite`, `Gen N`. The list was built empirically using `scripts/exploration/top_model_words.py`, which ranks word frequencies across all four feeds to surface high-frequency noise candidates.

### 2. Stripping manufacturer suffixes from model names

Some products use a generic descriptor pattern where the manufacturer brand is appended directly to the model name. The brand must be removed to get the clean model name.

| Raw model name | Manufacturer | Cleaned |
|---|---|---|
| `Atlas Fabric Kernel BlueRiver` | BlueRiver Holdings | `Atlas Fabric Kernel` |
| `Delta Matrix Grid Copperline` | Copperline Inc. | `Delta Matrix Grid` |
| `Vega Beam GoldenGate` | GoldenGate Ltd. | `Vega Beam` |

`extract_brand_from_manufacturer()` extracts the first meaningful token from the full legal entity string. `strip_manufacturer_suffix()` then removes that token if it appears at the end of the model name.

### 3. Parsing multi-component strings

The `core_components` field uses inconsistent delimiters across feeds. All are normalized to `" | "` after splitting.

| Raw | Parsed |
|---|---|
| `Slate Hub + Aero Flex` | `Slate Hub \| Aero Flex` |
| `Indigo Core; Lyra Kernel` | `Indigo Core \| Lyra Kernel` |
| `Ruby Node Edge and Topaz Rayo` | `Ruby Node Edge \| Topaz Rayo` |
| `Magenta Lien Gewebe & Sonic Bouclier Kernel` | `Magenta Lien Gewebe \| Sonic Bouclier Kernel` |

Split on: `/`, `,`, `;`, `+`, `&`, ` and ` (case-insensitive).

---

## Bundle Splitting

**Script:** `scripts/bundles.py`

Some entries in non-EU feeds represent product bundles where two model names are combined in a single `model_name` field.

| Raw entry | Split into |
|---|---|
| `SolPhone Mini Ultra and CoreBook Pro Max` | `SolPhone Mini Ultra`, `CoreBook Pro Max` |
| `RubyHub / VectorWatch Max Ultra 1TB Bundle` | `RubyHub`, `VectorWatch Max Ultra` |
| `HelioCam 1TB Dual-SIM/SonicBuds Mini` | `HelioCam`, `SonicBuds Mini` |

Splits on `" and "` and `" / "`. Each bundle part is treated as an independent product and linked with `match_type = 'bundle_part'` so it remains traceable back to the original combined entry.

> The EU feed is intentionally clean and does not contain bundle entries.

---

## Component Alias Resolution

**Script:** `scripts/aliases.py`

The Switzerland feed contains component names in German and French that must be mapped to the canonical English vocabulary defined in `data/component_list.json`.

| Market name (raw) | Language | Canonical (English) |
|---|---|---|
| `Sierra Kern` | German | `Sierra Core` |
| `Magenta Bouclier Mesh` | French | `Magenta Shield Mesh` |
| `Slate Matriz` | Spanish | `Slate Matrix` |
| `Teal Lien` | French | `Teal Link` |

Resolution order: exact match against `components` table → lookup in `component_aliases` table → unresolved if neither matches.

---

## Matching

### Tier 1 — Exact matching (`scripts/matching.py`)

After cleaning, products whose normalized model names are identical are linked to the same canonical `model` record. This is the primary linking mechanism and handles the majority of clear-cut cross-market matches.

**What counts as a match:** two source products share the same normalized model name after spec stripping, bundle splitting, and manufacturer suffix removal.

### Tier 2 — Fuzzy matching (`scripts/fuzzy_match.py`)

Products that survive Tier 1 without a cross-market link go through a fuzzy pass. Candidates are first filtered by a **first-token block** (only products whose model name starts with the same word are compared), then scored with a weighted composite:

```
score = 0.55 × name_sim + 0.30 × component_sim + 0.15 × manufacturer_sim
```

- **name_sim:** `token_sort_ratio` from rapidfuzz — sorts tokens before comparing, which handles minor word-order variation without being overly permissive.
- **component_sim:** `token_set_ratio` on the normalized component string — appropriate here because component order does not carry meaning.
- **manufacturer_sim:** `1.0` if manufacturer IDs match, `0.5` if manufacturer name similarity ≥ 0.6, else `0.0`.

Pairs above the threshold are written as `match_type = 'fuzzy'` rows into `source_product_models`.

### Algorithm variants

Three named configurations are available via `--algo`:

| Alias | Weights (name / comp / mfr) | Use case |
|---|---|---|
| `name_only` | 1.0 / 0.0 / 0.0 | Debug — name signal only |
| `name_comp` | 0.65 / 0.35 / 0.0 | When manufacturer data is unreliable |
| `name_comp_mfr` *(default)* | 0.55 / 0.30 / 0.15 | Full signal; recommended |

---

## Decisions & Techniques

### Why `token_sort_ratio` for name similarity (not `token_set_ratio`)

`token_set_ratio` was evaluated first as the name scorer. It is more permissive — it handles the case where one string is a subset of another — but this caused false positives between products that share a common prefix but are distinct models (e.g., `AzureRouter SE` matching `AzureRouter SE Ultra`). Switching to `token_sort_ratio` for the name dimension, while keeping `token_set_ratio` for components, gave better precision at the same threshold with a manageable recall cost.

### Threshold selection

The default threshold is **0.78**, selected by a dry-run sweep across the range 0.60–0.80:

| Threshold | Estimated fuzzy links | Coverage |
|---|---|---|
| 0.65 | ~18,000 | ~43 % |
| 0.70 | ~16,500 | ~39 % |
| 0.75 | ~15,200 | ~36 % |
| **0.78** | **~14,677** | **~35 %** |
| 0.80 | ~13,100 | ~31 % |

0.78 was chosen as the conservative end of the range: coverage still meaningfully extends exact-match results without visually introducing many obviously wrong links (verified via the validation UI). A proper labeled dataset would sharpen this decision — see [To-Do](#to-do).

### Blocking

Without blocking, all-pairs comparison across 52,000 products is prohibitively slow. The first-token block reduces the comparison space by ~95 % while retaining recall for the vast majority of real matches (products with the same first word in their model name). Products with no component data have the component weight redistributed to the name weight to avoid penalizing them unfairly.

---

## Data Model

The schema (`sql/schema_sqlite.sql`) is designed around full traceability: every original record is preserved and linked, not overwritten.

```
markets ──────────────── source_products ──────── source_product_models ──── models
                              │                                                  │
                              └── source_product_components ─── components ──────┘
                                                                    │
                                                             component_aliases
manufacturers ──── source_products
```

Key tables:

| Table | Purpose |
|---|---|
| `source_products` | One row per raw market entry. Stores both `raw_*` and `normalized_*` columns. |
| `models` | Deduplicated canonical model names. |
| `source_product_models` | Links each source product to a canonical model. `match_type` records how the link was made (`direct`, `bundle_part`, `fuzzy`). |
| `components` | 608 canonical English component names. |
| `component_aliases` | Maps localized component names to canonical IDs. |
| `manufacturers` | Normalized manufacturer legal entity names. |

---

## Results

| Metric | Value |
|---|---|
| Total products ingested | ~52,314 |
| — EU | 1,912 |
| — US | 11,852 |
| — Spain | 38,108 |
| — Switzerland | 442 |
| Canonical model entities created | — |
| Exact-match cross-market links | ~22 % coverage |
| Fuzzy-match additional links (threshold 0.78) | ~14,677 estimated (~35 % total coverage) |
| Canonical components | 608 |

---

## Evaluation

**Script:** `scripts/evaluate.py`  
**Data:** `data/evaluation/eval_pairs.csv`

The current eval set (`eval_pairs.csv`) was auto-generated by `scripts/evaluation/generate_eval.py` — it pulls 100 pairs that the naive exact-match pipeline already linked (all labeled `1`). This means it only validates that the scoring function agrees with existing exact matches; it **does not measure how many true cross-market matches the fuzzy pass is missing or incorrectly adding**.

To evaluate against this dataset:

```bash
python scripts/evaluate.py --plot
```

---

## To-Do

### Create a representative labeled dataset

The current evaluation set is not suitable for threshold tuning because it contains only positive examples drawn from already-matched pairs. A proper evaluation requires:

1. **Positive examples** — cross-market pairs that are known to be the same product (including cases the pipeline does not yet link).
2. **Negative examples** — cross-market pairs that look similar but are distinct products.

**How to generate candidates for labeling:**

```bash
# Generate unmatched candidates for manual review
python scripts/evaluation/generate_eval.py

# Open the labeling UI in your browser
python scripts/evaluation/generate_labeling_ui.py
# → opens data/labeling_ui.html
```

The labeling UI presents each unmatched product alongside its top-5 fuzzy candidates, scored and ranked. You select which candidates are true matches and export the results as a CSV. That CSV, combined with confirmed negatives, becomes the ground-truth dataset needed to run a meaningful threshold sweep and identify the precision/recall trade-off for each algorithm variant.

### Other improvements

- Populate `component_aliases` more systematically (currently seeded by hand from known CH variants).
- Handle the case where the same product appears in a feed under both its standalone name and as part of a bundle entry (currently treated as two separate source products).
