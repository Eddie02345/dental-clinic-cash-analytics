# Dental Clinic Cash Analytics

A working prototype that turns a dental clinic's free-text ledger into a
forecast and a margin view. Built for the Data Mining final project.

The clinic did not have a system. It had one spreadsheet with three things
mixed together: daily cash collections, an expense log typed by hand, and
GCash/BDO balances. Owner personal spending was recorded inside the expense log
as `D`, so the clinic could not compute its own operating margin.

## What it does

| Output | Method |
|---|---|
| Clean ledger (21 months, 478 trading days, 544 expense lines) | Parser with validation against the workbook's own monthly totals |
| Operating vs personal spending split | Label taxonomy, editable in `data/processed/labels.csv` |
| Cost mix, break-even, weekday demand pattern | Descriptive analytics |
| Three-month cash forecast | Prediction: revenue per trading day x assumed trading days, backtested walk-forward |
| Excel and PDF handover reports | `src/export.py` |

Headline result: the forecast model cuts out-of-sample error to **18.8% MAPE**
against **22.7%** for the best naive baseline (a 16.8% relative improvement),
measured on 15 walk-forward months.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# rebuild every artifact from the raw workbook (~5 seconds)
.venv/bin/python -m src.pipeline --force

# run the app
.venv/bin/streamlit run src/app/app.py

# tests
.venv/bin/python -m pytest tests -q
```

The app rebuilds missing artifacts on first launch, so `streamlit run` alone
works from a clean checkout.

## Layout

```
Accounting.xlsx                     original workbook (untouched)
data/raw/Accounting.xlsx            working copy
data/processed/                     parsed CSVs, labels.csv, monthly tables
data/clinic.db                      SQLite working copy used by the app
src/parse_ledger.py                 workbook -> tidy CSVs + validation
src/taxonomy.py                     free-text label -> category rules
src/features.py                     monthly table, features, daily profile
src/forecast.py                     backtest, model selection, projection
src/train_forecast.py               evaluation run + figures
src/analyze.py                      KPIs, cost mix, break-even
src/db.py                           SQLite schema and CRUD helpers
src/export.py                       XLSX and PDF reports
src/app/app.py                      Streamlit app (4 pages)
tests/                              16 functional and algorithm tests
docs/                               proposal, technical docs, manual, demo script
reports/                            metrics, analysis, figures, exports
```

## Screens

| | |
|---|---|
| Dashboard | `docs/screenshots/dashboard.png` |
| Forecast | `docs/screenshots/forecast.png` |
| Ledger | `docs/screenshots/ledger.png` |
| Reports | `docs/screenshots/reports.png` |

## Numbers

| Figure | Value |
|---|---|
| Collections, 21 months | ₱2,333,800 |
| Operating expenses | ₱976,177 |
| Owner personal (label `D`) | ₱214,590 (18.0% of spend) |
| Operating margin | 58.2% (upper bound) |
| Average monthly surplus | ₱64,649 |
| Break-even per trading day | ₱2,623 |
| Unclassified operating spend | 2.3% |
| Forecast MAPE, out of sample | 18.8% |

## Data caveats

- The expense log is not a complete business ledger. Rent appears in 10 of 21
  months, so margin and surplus are upper bounds, not audited figures.
- Amounts are day totals, not individual transactions, so patient-level
  analysis (segmentation, treatment baskets) is not possible from this file.
- One impossible date (29 Feb 2026, ₱11,800) is kept and flagged, dated to the
  last valid day of the month.
- Missing days are treated as non-trading days, not zeros.

See `reports/parse_issues.csv` for the full list.
