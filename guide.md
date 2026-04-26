Files are clean — the console error is just Windows terminal encoding for the special hyphen in the raw data, the
  CSV itself is correct. The first pair confirms it's working: SparkSpeaker Ultra Ultra [EU] ↔ SparkSpeaker Ultra 
  Ultra [CH], label=1.                                                                                                  
  ---                                                                                                                   Manual labeling guide — the 100 pairs in manual_candidates.csv                                                      
                                                                                                                      
  These are products the naive algorithm could not link across markets. Your job: determine if any of them refer to 
  the same product as something in another market's CSV.                                                                                                                                                                                      Setup (5 min)                                                                                                       

  Open three things side by side:
  1. data/manual_candidates.csv — your 100 candidates
  2. All four CSVs open in Excel/Sheets (one tab each)
  3. data/eval_pairs.csv open — you'll append rows here

  The labeling loop

  For each row in manual_candidates.csv:

  1. Take the normalized_model_name and search it in the other markets' CSVs (Ctrl+F). Start with EU — it's the       
  cleanest feed.

  2. If you find a plausible match, check secondary signals:
  - Same manufacturer family? (Harbor Holdings Inc. ≈ Harbor Systems Inc.)
  - Overlapping components? (even partially — Kern = Core in CH)
  - If both signals agree → it's a match (label=1)
  - If name matches but manufacturer is totally different → probably not (label=0)

  3. Append a row to eval_pairs.csv:

  id_a      = id from manual_candidates.csv
  id_b      = the ID of the product you found (look it up in the DB, or search by row number in CSV)
  market_a  = market from manual_candidates
  market_b  = market of the match you found
  name_a    = raw_model_name from candidates
  name_b    = raw_model_name you found
  norm_name_a / norm_name_b = cleaned versions (strip spec tokens manually)
  label     = 1 (match) or 0 (confirmed non-match)
  match_type = manual
  notes     = WHY — e.g. "Kern=Core CH translation" or "same components diff mfr, no match"

  4. If no match found in 60 seconds → skip. Don't force it. Unresolved candidates are still useful — they become hard
   negatives when paired with similar-looking products from another market.

  What to focus on per market

  ┌────────┬──────────────────────────────────────────────────────────────────┬───────────────────────────────────┐   
  │ Market │                        What makes it hard                        │         What to look for          │   
  ├────────┼──────────────────────────────────────────────────────────────────┼───────────────────────────────────┤   
  │        │ German/French component names (Kern=Core, Netz=Net,              │ Match normalized model name to    │   
  │ CH     │ Gewebe=Fabric, Lien=Link, Bouclier=Shield, Matriz=Matrix,        │ EU, ignore component names        │   
  │        │ Rayo=Ray)                                                        │                                   │   
  ├────────┼──────────────────────────────────────────────────────────────────┼───────────────────────────────────┤   
  │ ES     │ No core_components column at all                                 │ Only name + manufacturer to go on │   
  ├────────┼──────────────────────────────────────────────────────────────────┼───────────────────────────────────┤   
  │ US     │ Bundle names (SolPhone Mini and CoreBook Pro)                    │ Search each bundle part           │   
  │        │                                                                  │ separately in EU                  │   
  ├────────┼──────────────────────────────────────────────────────────────────┼───────────────────────────────────┤   
  │ EU     │ Cleanest feed, use as the anchor                                 │ If a CH/US/ES candidate looks     │   
  │        │                                                                  │ right, EU will confirm it         │   
  └────────┴──────────────────────────────────────────────────────────────────┴───────────────────────────────────┘   

  Getting IDs for products you find in the CSVs

  Run this in the terminal to look up an ID by name:
  ! python -c "import sqlite3; conn = sqlite3.connect('electropulse.db'); print(conn.execute(\"SELECT id, market_id, raw_model_name FROM source_products WHERE raw_model_name LIKE '%SparkWatch%' LIMIT 10\").fetchall())"

  Target

  Aim for ~60–70 successful manual pairs (label=1) + ~30–40 confirmed non-matches (label=0). The non-matches are just 
  as important — they teach the algorithm what NOT to match.

  When done you'll have ~160–170 labeled pairs total. That's enough to run a meaningful precision/recall sweep.    