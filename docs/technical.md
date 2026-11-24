# Technical Documentation

## 1. System architecture

```
Accounting.xlsx
      |
      v
parse_ledger.py ------> data/processed/*.csv + reports/parse_issues.csv
      |
      v
taxonomy.py ----------> data/processed/labels.csv, expenses_categorized.csv
      |
      v
features.py ----------> monthly_table.csv, features.csv, weekly/daily profiles
      |
      v
train_forecast.py ----> models/model.json, reports/metrics.json, figures
      |
      v
analyze.py -----------> reports/analysis.json, reports/figures/*.png
      |
      v
db.py ----------------> data/clinic.db (SQLite, seeded from CSVs)
      |
      v
app/app.py  <---------- Streamlit, 4 pages, imports the modules above
      |
      v
export.py ------------> reports/clinic_summary.xlsx, .pdf
```

One process, one language, no server dependency. The pipeline is deterministic:
`python -m src.pipeline --force` rebuilds every artifact from the raw workbook in
about 4 seconds.

## 2. Source data profile

| Property | Value |
|---|---|
| Sheet | one sheet, 840 rows |
| Blocks | 21 monthly sections, Feb 2025 to Oct 2026 |
| Daily collection rows | 478 (474 with a positive amount) |
| Expense lines | 544 |
| Distinct expense labels | 97 |
| Collections total | ₱2,333,800 |
| Logged expenses total | ₱1,190,767 |
| Trading days per month | 12 to 28, mean 22.6 |

Each block contains three unrelated structures side by side:

- columns A/B: day number and cash collected
- columns F/G/H: expense date, free-text label, amount
- columns K/L: General Income and Total Expenses, plus a GCash/BDO table in N to U

The parser treats them as three separate extractions, which is why one
spreadsheet becomes four keyed tables.

## 3. Database design

Working copy at `data/clinic.db`. Seeded from CSVs on first launch; edits in
the app affect only this database.

```sql
daily_collections(id, block_id, date, amount, source)
expenses(id, block_id, date, label_raw, label_norm, amount, category,
         expense_type, source)
forecast_runs(id, created_at, model, assumed_days, months_ahead,
              total_projected, payload)
settings(key, value)
```

`expense_type` is `Operating` or `Personal`, derived from `category`. Personal
rows are never added to operating cost. `source` records whether a row came
from the ledger or was entered by hand, so manual entries remain auditable.

Indexes: `daily_collections(date)`, `expenses(block_id)`.

## 4. Parsing and validation

Rules, in order:

1. A block starts where column A holds a month name and column B is empty.
   Keying on the name alone fails, because `MARCH` appears twice.
2. Years come from block order, incrementing when the month number wraps.
3. Daily rows require an integer day in A and a number in B.
4. Expense rows require text in G and a number in H.
5. Summary rows require `General Income` or `Total Expenses` in K.

Validation outputs `reports/parse_issues.csv`:

| Issue | Rows | Handling |
|---|---|---|
| `invalid_date` | 1 (29 Feb 2026, ₱11,800) | kept, dated to last valid day, flagged |
| `missing_expense_total` | 1 (Feb 2025) | logged rows used |
| `expense_total_mismatch` | 1 (Dec 2025: ₱98,343 logged vs ₱41,404 reported) | logged rows used, flagged |
| `low_coverage` | 2 (Mar 2025: 12 days, Sep 2025: 17 days) | month treated as partial |

The primary check is stronger than row counts: the sum of daily collections in
each block must equal that block's own `General Income` cell. All 21 blocks
pass with a difference of 0.00.

## 5. Label taxonomy

`taxonomy.py` applies ordered rules: personal marker, rent, bank transfer,
laboratory, food, utilities, known wage names and relationship prefixes, a
non-person blocklist, supplier and material keywords, then a bare-name
fallback. Rules run in that order because the labels overlap: `Lab (Jessa Mae
Case)` must become `Lab Fees`, not a wage.

The mapping is written to `data/processed/labels.csv` with `count`, `total`,
`category` and `source`. On later runs that file wins over the rules, so a
single correction by the clinic persists. Delete the file to rebuild from
rules.

Result: 2.3% of operating value remains `Unclassified` (`beavans`,
`solicitation`, `ataw`, `viscus`), against a 5% target.

| Category | Total (PHP) | Share of operating |
|---|---|---|
| Wages | 377,472 | 38.7% |
| Rent | 343,592 | 35.2% |
| Lab Fees | 77,400 | 7.9% |
| Food | 73,176 | 7.5% |
| Bank/Transfer | 55,000 | 5.6% |
| Supplies | 25,419 | 2.6% |
| Unclassified | 22,778 | 2.3% |
| Utilities | 1,340 | 0.1% |

Personal spending, kept out of that table: ₱214,590, 18.0% of all recorded
spending.

## 6. The forecast model

### 6.1 Formulation

```
collections(t) = rate(t) x days(t)

rate(t)        = mean of revenue per trading day over the previous 6 months
days(t)        = assumed trading days in the month, default 23
```

`rate` is learned; `days` is an assumption the clinic controls through the app
slider. The default 23 comes from the observed 22.6-day mean.

### 6.2 Why this decomposition

Raw monthly totals in this ledger range from ₱34,650 to ₱165,400, and trading
days range from 12 to 28. Comparing totals conflates a short month with a slow
month. Dividing by trading days removes that artifact: revenue per trading day
moves in a much tighter band, ₱2,786 to ₱7,191, and a trailing mean of it
forecasts better than any learned model on this sample.

### 6.3 Candidates compared

| Model | Definition |
|---|---|
| last month | collections(t-1) |
| 4-month average | mean of the last four months |
| rate x 23 days (3m) | trailing 3-month rate x 23 |
| rate x 23 days (6m) | trailing 6-month rate x 23 |
| ridge on rate | ridge regression on rate lags, rolling rates and month, x 23 |
| gradient boosting on rate | same features, histogram gradient boosting, x 23 |

### 6.4 Evaluation protocol

Walk-forward, one month ahead, 15 origins:

```
for i in 6 .. 20:
    train on months [0, i)
    predict month i
    record error
```

Learned models are refitted at every origin, so no origin sees its own future.
Metrics: MAPE, MAE, and the share of months predicted within 10%.

### 6.5 Results

| Model | MAPE | MAE (PHP) | Within 10% |
|---|---|---|---|
| **rate x 23 days (6m)** | **18.8%** | **21,971** | **40%** |
| gradient boosting on rate | 20.1% | 29,099 | 36% |
| rate x 23 days (3m) | 22.6% | 25,604 | 27% |
| 4-month average (baseline) | 22.7% | 26,156 | 27% |
| ridge on rate | 23.2% | 31,809 | 36% |
| last month | 26.2% | 31,766 | 20% |

The chosen model improves MAPE by **16.8%** against the best baseline. The
gradient boosting model is close on MAPE but 32% worse on MAE, so the simpler
rule is preferred for both accuracy and explainability.

Uncertainty: the 10th to 90th percentile of backtest residuals is ₱-45,921 to
₱+28,797 around the point forecast. The app shows both bounds rather than a
single number.

### 6.6 Reproducing

```bash
.venv/bin/python -m src.train_forecast
# rewrites models/model.json, reports/metrics.json,
# reports/backtest_detail.csv and two figures
```

## 7. Analytics and decision support

- **Operating margin:** (collections - operating expenses) / collections =
  58.2%. Flagged as an upper bound.
- **Committed fixed cost:** typical rent (₱41,224, the median of 10 logged
  months) plus average wages and draws (₱377,472 / 21) = ₱59,198 per month,
  or ₱2,623 per trading day.
- **Average monthly surplus:** ₱64,649 before owner draws.
- **Demand pattern:** Monday, Tuesday and Saturday are the strongest trading
  days (multipliers 1.08, 1.10, 1.09); Wednesday is weakest (0.87). Sundays are
  almost never recorded (40 versus about 73 per weekday) and are treated as
  closed in the weekly split.

## 8. Implementation notes

- `src/forecast.py` holds the backtest and the projection, so the evaluation in
  the report and the number in the app come from the same code path.
- The app caches parsed artifacts, not raw queries. Clearing the cache after a
  ledger edit forces re-render without restarting the process.
- Exports are generated in memory and offered as downloads, so no file
  permissions are needed at demo time.
- Patient names that appear inside lab labels (for example `Lab (Jessa Mae
  Case)`) are redacted in any artifact that leaves the group; the working file
  used for the demo keeps the raw labels.

## 9. Interface design

The app is Streamlit with a Plotly chart layer, styled to read as a clinical
ledger rather than a generic dashboard:

- **Palette.** Cool mint paper `#F4F8F6`, deep pine ink `#10241F`, teal `#11796C`
  for clinic data, amber `#C98A2E` for running costs, and rust `#A8412B` used
  only for owner personal spending. The rust is semantic: it appears where the
  margin is being distorted, and nowhere else.
- **Type.** Georgia carries every figure, the way a printed statement sets
  numbers; the interface stays in the system sans. No web fonts, because the
  clinic runs this offline.
- **Layout.** Four-page sidebar, one statement-style band of headline figures
  per page (hairline rules, no floating cards), charts with a zero baseline and
  no grid clutter.
- **Charts are interactive.** Changing the trading-days input redraws the
  projection, so the demo shows the model working instead of a static image.

Screenshots: `docs/screenshots/`.

## 10. Known limitations

1. 21 months is a short history, and only one December is observed, so
   seasonality is not modelled beyond the month number as a candidate feature.
2. The expense log is incomplete: rent appears in 10 of 21 months and wages may
   include owner draws. Margin and surplus are therefore upper bounds.
3. Daily amounts are day totals, so no patient-level mining is possible.
4. `days(t)` is an assumption. A month with 12 trading days will miss if the
   user leaves the default at 23.
5. The label rules are tuned on this clinic's vocabulary. A different clinic
   needs `labels.csv` corrected once.
