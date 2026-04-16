# Current State Report — Rappi Competitive Intelligence

_Generated: 2026-04-15_

This report describes what exists in the repository today, how the pieces are
wired together, and — most importantly — **where the dashboard and PDF report
diverge from the real scraped data**. Nothing was modified; this is a
read-only audit.

---

## 1. Project Structure

### Root-level scripts
| File | Lines | Purpose |
|------|-------|---------|
| `run_scraper.py` | 280 | Legacy orchestration entry point. Can generate sample data OR run a live scraper, then calls consolidation. |
| `run_rappi_full.py` | 600 | Production Rappi scrape → **writes `data/processed/rappi_data.csv` (WIDE format)** and raw JSON per row. |
| `run_ubereats_full.py` | 620 | Production UberEats scrape → **writes `data/processed/ubereats_data.csv` (WIDE format)** and raw JSON per row. |
| `run_didifood_full.py` | 476 | Production DiDi Food scrape → **writes `data/processed/didifood_data.csv` (WIDE format, overwrite)** and raw JSON per row. |
| `run_didifood_recovery.py` | 487 | Re-runs the 4 DiDi locations that failed → **appends to `didifood_data.csv`**. |
| `generate_report.py` | 748 | Reads `competitive_data.csv` (LONG) → writes PDF + analysis CSVs + charts. |
| `test_didifood_quick.py` / `test_ubereats_quick.py` / `test_ubereats_scale.py` | — | Smoke tests. |

### `config/`
| File | Purpose |
|------|---------|
| `settings.py` | Paths (`RAW_DIR`, `PROCESSED_DIR`), platform URLs, timeouts, zone labels, platform colors. |
| `locations.py` | 25 CDMX locations with zone type / label / lat / lng. `get_locations_by_priority()`, `get_location_by_id()`. |
| `products.py` | 2 target restaurants (McDonald's, Burger King) with 5 product references (`big_mac`, `combo_big_mac`, `mcnuggets_10`, `whopper`, `combo_whopper`). |

### `scrapers/`
| File | Purpose |
|------|---------|
| `base.py` | Dataclasses: `ProductResult`, `DeliveryInfo`, `PromotionInfo`, `RestaurantResult`, `ScrapeResult` (with `.save(RAW_DIR)`). Abstract `BaseScraper` with `scrape_restaurant_at_location()`. |
| `rappi_scraper.py` (855) | Full Playwright scraper for Rappi. |
| `ubereats_scraper.py` (1192) | Full Playwright scraper for UberEats. |
| `didifood_scraper.py` (1676) | Full Playwright scraper for DiDi Food (direct-URL search + card delivery-info parsing). |
| `utils/anti_detection.py`, `parsers.py`, `retry.py`, `screenshot.py` | Stealth helpers, price/time parsing, retry, screenshots. |

### `scripts/`
| File | Purpose |
|------|---------|
| `consolidate_data.py` (296) | Reads `data/raw/*.json` → writes LONG-format `data/processed/competitive_data.csv`. **Only source that produces `competitive_data.csv`.** |
| `generate_sample_data.py` (440) | Synthetic `ScrapeResult` JSON generator (3 platforms × up to 25 locations × 2 restaurants, ~150 files). Used for dev / fallback only. |

### `analysis/`
| File | Lines | Purpose |
|------|-------|---------|
| `comparative.py` | 395 | 5 analysis functions (price positioning, delivery times, fee structure, promotions, geographic variability). CLI `__main__` writes 5 `reports/analysis_*.csv`. |
| `insights.py` | 512 | Converts comparative output → top-5 insights. Writes `reports/top5_insights.json` + `.txt`. |
| `visualizations.py` | 523 | 8 matplotlib charts → `reports/charts/*.png`. |

### `dashboard/`
| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | 875 | Streamlit app, 6 tabs. |
| `ai_summary.py` | 66 | Groq LLM wrapper for executive summary (optional — requires `GROQ_API_KEY`). |
| `components/` | (empty `__init__.py` only) | Placeholder, no components implemented. |

### `data/`
```
data/processed/
  competitive_data.csv           190 data rows (long format)
  rappi_data.csv                 46 data rows (wide format)
  ubereats_data.csv              46 data rows (wide format)
  didifood_data.csv              46 data rows (wide format)
  consolidated_20260410_180142.json   legacy consolidated dump
data/raw/           per-scrape ScrapeResult JSONs (native format)
data/screenshots/   optional screenshots from scraper runs
```

### `reports/`
```
analysis_fees.csv
analysis_geographic.csv
analysis_prices.csv
analysis_promotions.csv
analysis_times.csv
charts/                 PNGs from visualizations.py
competitive_report.pdf  output of generate_report.py
top5_insights.json
top5_insights.txt
```

### `tests/`
`test_analysis.py`, `test_integration.py`, `test_scrapers.py`.

---

## 2. Dashboard (`dashboard/app.py`)

### Data source
A single `@st.cache_data`-wrapped loader at `dashboard/app.py:70` reads
**`data/processed/competitive_data.csv`** (LONG format) and derives
`delivery_time_mid = (estimated_time_min + estimated_time_max) / 2`. The
per-platform CSVs (`rappi_data.csv` etc.) are **not read anywhere by the
dashboard**.

If the CSV is missing, the dashboard errors out and suggests running the
sample data generator (`app.py:74-76`) — it does **not** auto-fall back to
synthetic data.

### Tabs
All six tabs consume the same long-format DataFrame; aggregations happen in
the tab body.

| # | Tab | Function | Key columns consumed |
|---|-----|----------|----------------------|
| 1 | Executive Overview | `tab_overview()` (166–241) | `platform`, `product_price_mxn`, `delivery_fee_mxn`, `delivery_time_mid`, `restaurant_rating`, `data_completeness`, `timestamp`. Also loads `reports/top5_insights.json` via `load_insights()` (97). |
| 2 | Pricing | `tab_prices()` (312–398) | `product_name`, `product_price_mxn`, `platform`, `zone_type`, `zone_label`. Plotly bars + deltas vs Rappi. |
| 3 | Delivery & Fees | `tab_delivery()` (404–537) | `delivery_fee_mxn`, `service_fee_mxn`, `delivery_time_mid`, `zone_type`, `platform`. |
| 4 | Geographic | `tab_geographic()` (538–631) | `location_id`, `zone_type`, `zone_label`, `lat`, `lng`, `total_price_mxn`. Scatter maps. |
| 5 | Promotions | `tab_promotions()` (632–749) | `promotions_count`, `promotions_description`, `platform`. Inline `_classify_promo()` (708) categorises text. |
| 6 | AI Insights | `tab_ai_insights()` (750–805) | Reads `top5_insights.json`; optionally calls `ai_summary.generate_ai_summary()` if `GROQ_API_KEY` is set. |

### Real vs synthetic
Everything the dashboard renders is real **iff** `competitive_data.csv` is
fresh. There is **no synthetic fallback at runtime**; the error message is
advisory only.

### `ai_summary.py`
Real — calls Groq `llama3-8b-8192`. If no API key it returns a canned
markdown string so the tab never breaks.

---

## 3. Analysis modules (`analysis/`)

All three modules are **fully implemented** — no `TODO`s, no stubs, no
hardcoded test data. They all read the same long CSV.

### `comparative.py` — 5 public functions
Input: `analysis/comparative.py:41` `load_data()` reads
`PROCESSED_DIR/competitive_data.csv`.

| Function | Lines | Input columns | Output shape |
|----------|-------|---------------|--------------|
| `analyze_price_positioning(df)` | 73–114 | `product_name`, `product_price_mxn`, `platform` | 1 row per product with `rappi_avg`, `ubereats_avg`, `didifood_avg`, `ue_vs_rappi_pct`, `didi_vs_rappi_pct`, `cheapest_platform`. |
| `analyze_delivery_times(df)` | 121–166 | `delivery_time_mid`, `zone_type`, `platform` | 1 row per zone with platform-specific avg/std and `fastest_platform`. |
| `analyze_fee_structure(df)` | 173–204 | `delivery_fee_mxn`, `service_fee_mxn`, `product_price_mxn`, `platform` | 1 row per platform with avg fees + `fee_as_pct_of_product`. |
| `analyze_promotions(df)` | 211–263 | `scrape_id`, `platform`, `promotions_count`, `promotions_description` | 1 row per platform with promo rate + `most_common_promo_type` (keyword-based). |
| `analyze_geographic_variability(df)` | 270–303 | `product_price_mxn`, `zone_type`, `zone_label`, `platform`, `delivery_fee_mxn`, `delivery_time_mid`, `total_price_mxn` | ranked per-zone per-platform table. |

The CLI (`python -m analysis.comparative`) writes each result to
`reports/analysis_*.csv`.

### `insights.py`
Five generators (`_insight_pricing`, `_insight_fees`, `_insight_delivery`,
`_insight_promotions`, `_insight_geographic`) that consume the outputs of
`comparative.py` and emit dicts with `number`, `category`, `finding`,
`impact`, `recommendation`, `data_support`. CLI writes top-5 to
`reports/top5_insights.json` + `.txt`.

### `visualizations.py`
Eight matplotlib charts, each saved via an internal `_save()` helper:
`plot_price_comparison`, `plot_total_cost_breakdown`, `plot_geographic_heatmap`,
`plot_delivery_times`, `plot_fee_comparison`, `plot_promotion_rates`,
`plot_competitive_radar`, `plot_price_delta_by_zone`. All expect the long
format.

---

## 4. Report generator (`generate_report.py`)

- **Input:** `data/processed/competitive_data.csv` (`generate_report.py:25`).
- **Loader:** `load_data()` (~l. 186) casts numerics, derives
  `delivery_time_mid`, drops `data_completeness == "failed"`.
- **Pipeline:** calls the same `analyze_*` functions from
  `analysis.comparative`, then builds PDF pages with ReportLab / matplotlib.
- **Pages:** cover → executive summary → methodology → price analysis →
  geographic + delivery times → fees + promotions → top-5 insights →
  scorecard → next steps.
- **Outputs:**
  - `reports/competitive_report.pdf`
  - `reports/analysis_*.csv` (re-written by comparative pipeline)
  - `reports/charts/*.png`
  - `reports/top5_insights.json`

**Format expected: LONG.** It cannot consume the per-platform wide CSVs
directly.

---

## 5. Scripts (`scripts/`)

### `consolidate_data.py`
- Reads **only** `data/raw/*.json` (line 4 docstring, confirmed in source).
- `CSV_COLUMNS` (38–67) defines the canonical LONG schema.
- `flatten_result()` emits **one row per product** from the `products[]`
  array of each `ScrapeResult` JSON.
- Writes `data/processed/competitive_data.csv`.
- **This is the only producer of `competitive_data.csv` in the codebase.**

### `generate_sample_data.py`
- Generates synthetic `ScrapeResult` JSONs into `data/raw/` with realistic
  platform/zone multipliers (prices, fees, ETAs, ratings, promotions).
- Referenced by `run_scraper.py` (`--generate-sample`) and by the advisory
  error messages in `app.py`/`comparative.py`; **not imported or invoked at
  runtime by the dashboard or report generator**.

---

## 6. Available data

### Row counts (`wc -l` incl. header)
| File | Total lines | Data rows |
|------|-------------|-----------|
| `data/processed/competitive_data.csv` | 191 | 190 |
| `data/processed/rappi_data.csv` | 47 | 46 |
| `data/processed/ubereats_data.csv` | 47 | 46 |
| `data/processed/didifood_data.csv` | 47 | 46 |

### Freshness (newest `timestamp` in each)
| File | Newest timestamp |
|------|------------------|
| `competitive_data.csv` | 2026-04-10 (stale — ~5 days old) |
| `rappi_data.csv` | 2026-04-14 21:22 UTC |
| `ubereats_data.csv` | 2026-04-14 03:30 UTC |
| `didifood_data.csv` | 2026-04-15 03:34 UTC |

The **per-platform CSVs are fresh**; `competitive_data.csv` is **stale** and
predates all three production runs.

### Schema — LONG vs WIDE

**LONG — `competitive_data.csv` (28 cols, one row per product per observation):**
```
scrape_id, timestamp, platform, location_id, location_address,
lat, lng, zone_type, zone_label, city,
restaurant_name, restaurant_available, restaurant_rating, restaurant_review_count,
product_name, product_reference_id, product_price_mxn, product_available,
delivery_fee_mxn, service_fee_mxn, estimated_time_min, estimated_time_max,
total_price_mxn, promotions_count, promotions_description,
data_completeness, errors_count, scrape_duration_seconds
```

**WIDE — `{rappi,ubereats,didifood}_data.csv` (34 cols, one row per observation):**
```
run_id, timestamp, platform, location_id, location_address, zone_type, zone_label, city,
lat, lng,
restaurant_name, restaurant_available, restaurant_rating, restaurant_review_count,
delivery_fee_mxn, service_fee_mxn, eta_min_min, eta_max_min,
price_big_mac, price_combo_big_mac, price_mcnuggets_10, price_whopper, price_combo_whopper,
match_big_mac, match_combo_big_mac, match_mcnuggets_10, match_whopper, match_combo_whopper,
promotions_count, promotions_values,
data_completeness, retry_attempt, errors_count, errors, scrape_duration_seconds
```

**Key field differences:**

| Concept | LONG | WIDE |
|---------|------|------|
| Primary id | `scrape_id` (UUID) | `run_id` (timestamp string) |
| Product identity | `product_name`, `product_reference_id` as rows | `price_<id>` / `match_<id>` as columns |
| Price | `product_price_mxn` (one value per row) | five `price_*` columns |
| ETA columns | `estimated_time_min`, `estimated_time_max` | `eta_min_min`, `eta_max_min` |
| Promotions text | `promotions_description` | `promotions_values` |
| Errors | `errors_count` | `errors_count` + `errors` (list) + `retry_attempt` |
| Total price | `total_price_mxn` (derived) | not stored |

### Sample rows

`rappi_data.csv` (first data row):
```
20260414_162204, 2026-04-14T21:22:11, rappi, polanco, …, McDonald's - Juárez,
True, 3.7, 270, 0.0, , 12, 12, 145.0, 199.0, 149.0, , ,
Big Mac Tocino…, McTrío Big Mac Tocino…, Paquete Botanero…, , ,
0, , full, 1, 0, , 123.48
```

`didifood_data.csv` (first data row):
```
20260414_201121, 2026-04-15T01:11:33, didifood, polanco, …, McDonald's (Antara),
True, 4.1, 4000, 15.0, , 15, 30, 87.0, 199.0, 159.0, , ,
Big Mac, McTrío Big Mac, McNuggets 10, , ,
2, 55%; 55%, full, 1, 0, , 41.45
```

`ubereats_data.csv` (first data row):
```
20260413_214009, 2026-04-14T02:40:13, ubereats, polanco, …, McDonald's Antara,
True, 4.5, 15000, 0.0, , 14, 34, 125.0, 169.0, 159.0, , ,
Big Mac, McTrío Big Mac …, McTrio … McNuggets 10 …, , ,
4, 43%; 27%; 41%; 22%, full, 1, 0, , 64.33
```

---

## 7. Who reads what — format usage map

| Consumer | Expects | File it reads |
|----------|---------|---------------|
| `dashboard/app.py:71` | LONG | `data/processed/competitive_data.csv` |
| `generate_report.py:25` | LONG | `data/processed/competitive_data.csv` |
| `analysis/comparative.py:26` | LONG | `data/processed/competitive_data.csv` |
| `scripts/consolidate_data.py` | JSON | `data/raw/*.json` (produces LONG CSV) |
| `run_rappi_full.py:49` | — (writer) | writes `rappi_data.csv` (WIDE) + raw JSONs |
| `run_ubereats_full.py:51` | — (writer) | writes `ubereats_data.csv` (WIDE) + raw JSONs |
| `run_didifood_full.py:53` | — (writer) | writes `didifood_data.csv` (WIDE) + raw JSONs |
| `run_didifood_recovery.py:54` | — (writer) | appends to `didifood_data.csv` (WIDE) + raw JSONs |

**No code path reads the per-platform WIDE CSVs.** The production scrape
scripts happen to write them (convenient per-platform audit trail), but the
analysis/reporting stack only consumes the LONG CSV produced by
`consolidate_data.py` out of raw JSON.

---

## 8. Gap analysis — synthetic vs real data

Contrary to what you might fear, **the dashboard, report, and analysis code
are all "real" and all point at real-data paths**. Nothing hardcodes
synthetic values. The only reason output may look stale or synthetic is that
`competitive_data.csv` has not been refreshed since 2026-04-10.

**Two possible states of the raw JSON:**
1. If `data/raw/` contains fresh `ScrapeResult` JSONs from the recent full
   runs (the run scripts call `result.save(RAW_DIR)` on every scrape),
   simply re-running consolidation will rebuild the long CSV with real data.
2. If `data/raw/` only has old JSONs, the run scripts need to be re-run
   (they save JSON alongside the CSV), then consolidation.

---

## 9. What needs to change

The gap is **operational, not structural**. The pipeline is intact; one
step (consolidation) is stale.

### Minimal path (no code changes) — if `data/raw/` has the fresh JSONs
```
python -m scripts.consolidate_data          # rebuild competitive_data.csv
python -m analysis.comparative              # rebuild analysis_*.csv
python -m analysis.insights                 # rebuild top5_insights.json
python -m analysis.visualizations           # rebuild charts/*.png
python generate_report.py                   # rebuild PDF
# restart Streamlit to clear @st.cache_data
```

### If the per-platform WIDE CSVs are the canonical source (raw JSON gone or lagging)
You need a WIDE → LONG bridge. Two options:

**Option A (recommended) — teach `consolidate_data.py` to also read the WIDE CSVs.**

File: `scripts/consolidate_data.py`
- Add a `flatten_wide_row(row)` function that, for each of the 5
  `price_<id>` columns in a WIDE row, emits one LONG dict using the mapping:
  - `run_id` → `scrape_id`
  - `eta_min_min`/`eta_max_min` → `estimated_time_min`/`estimated_time_max`
  - `promotions_values` → `promotions_description`
  - skip products whose `price_<id>` is empty
  - compute `total_price_mxn = price_<id> + (delivery_fee_mxn or 0) + (service_fee_mxn or 0)`
  - set `product_name = match_<id>` (fallback to humanised `<id>`) and
    `product_reference_id = <id>`
- In `consolidate()` (~l. 197), discover and iterate the three WIDE CSVs
  alongside (or instead of) `data/raw/*.json`; route each row through the
  appropriate flattener.

**Option B — separate bridge script.**
Create `scripts/wide_to_long.py` that reads the three per-platform CSVs,
emits the same long-format rows, and appends/overwrites
`competitive_data.csv`. Leaves `consolidate_data.py` untouched.

### Files that would need modification under Option A
| File | Line(s) | Change |
|------|---------|--------|
| `scripts/consolidate_data.py` | add `flatten_wide_row()` helper near `flatten_result()` (after l. 180); extend `consolidate()` input discovery around l. 197; keep `CSV_COLUMNS` unchanged | bridge WIDE → LONG |

**No changes required** in `dashboard/app.py`, `generate_report.py`,
`analysis/comparative.py`, `analysis/insights.py`, or
`analysis/visualizations.py` — they already read the correct file. They
just need that file to be rebuilt.

### Sanity checks after rebuild
- `wc -l data/processed/competitive_data.csv` should grow from 191 to at
  least ~370 (46 WIDE rows × ~2–3 non-empty products each across the 3
  platforms, excluding failed scrapes).
- `head -1` should still match the 28-column LONG schema above.
- Dashboard tabs should show `timestamp` values from 2026-04-14 / 2026-04-15.

---

## 10. Open questions

1. Are the raw JSONs in `data/raw/` from the most recent production runs still
   present, or have they been pruned? (Drives whether Option A bridge is
   required or whether consolidation alone is enough.)
2. The legacy `data/processed/consolidated_20260410_180142.json` — is it
   still a valid fallback or should it be deleted?
3. The per-platform WIDE CSVs lack a `total_price_mxn` column; confirm the
   computation rule `price + delivery + service` matches how the LONG CSV
   was previously derived.
