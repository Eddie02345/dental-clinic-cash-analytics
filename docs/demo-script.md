# Demo Script

Total time: about 8 minutes. Run order matters: show the mess, then the cleaning,
then the algorithm, then the product. The guidelines explicitly accept a
demonstration only if it shows the processing, not screenshots of results.

## Before the panel arrives

```bash
cd datsci
.venv/bin/python -m src.pipeline --force   # pre-warm, ~5s
.venv/bin/streamlit run src/app/app.py
```

Have open: the workbook in a spreadsheet app, a terminal at the repo root, and
the browser on the Dashboard.

## 1. The raw problem (1 minute)

Open `Accounting.xlsx` and scroll to any monthly block. Point at:

- three unrelated structures side by side (collections in A/B, expenses in F/G/H,
  GCash balances in N to U),
- the free-text expense column with `Food`, `Doctor 1`, and redacted `Doctor N`
  payee lines (raw personal names are gone from the working copy),
- the `Doctor 1` lines. State the number: ₱244,705, 13.0% of all recorded spending,
  and 82% of March 2026's recorded costs.

Say the sentence the whole project rests on: because personal spending sits in
the same column as clinic costs, this clinic cannot compute its own margin.

## 2. Parsing and validation (1 minute)

```bash
.venv/bin/python -m src.parse_ledger
```

Point at the printed table: 21 blocks, and a `tie` column of zeros. Explain that
each block's daily sum is checked against the workbook's own General Income cell,
so the extraction is verified rather than assumed. Mention the three flagged
rows and the invalid date.

## 3. Cleaning and categorization (1 minute)

```bash
.venv/bin/python -m src.taxonomy
```

Show: 3.3% of operating spend left unclassified, personal spending split out,
cost mix with rent and wages at 53.6% and 19.3%. Open `labels.csv` and explain
that a correction by the clinic is stored once and wins on every later run.

## 4. The algorithm (2 minutes)

```bash
.venv/bin/python -m src.train_forecast
```

Show the comparison table and say the important part out loud:

- six candidates, 15 walk-forward origins, refit at every origin,
- the chosen rule is revenue per trading day times assumed trading days,
- 18.8% MAPE against 22.7% for the best baseline, a 16.8% improvement,
- the learned models lost, and the report says so.

This is where you answer "where is the data mining": the model is fitted on
history, selected on out-of-sample error, and its uncertainty interval comes
from its own residuals.

## 5. The product (2 minutes)

Browser, in this order:

1. **Dashboard**: margin, break-even per trading day, cost mix, weekday pattern.
2. **Forecast**: change the trading-days input from 23 to 20 and let the
   projection move. That demonstrates the model rather than a static image.
3. **Ledger**: type `Doctor 2` into the expense form, show the category suggestion
   flip to Wages, save, and show it in the table.
4. **Reports**: build and download the PDF. Open it.

## 6. Limits and close (1 minute)

State unprompted:

- 21 months is short, and only one December is observed.
- Rent is normalized to all 21 months, so margin is an upper bound.
- Amounts are day totals, so no patient-level analysis is possible.
- The forecast is a planning aid; two months in five land within 10%.

Close on the value: the clinic can now see its own margin, knows it needs
₱2,529 per trading day to cover rent and wages, and has a three-month cash
projection with a published error rate.

## If something fails

| Failure | Recovery |
|---|---|
| App will not start | Run the pipeline first, then `streamlit run`; the app rebuilds missing artifacts |
| Numbers look stale | `python -m src.pipeline --force` regenerates everything in about 5 seconds |
| A live edit breaks the table | Revert with the delete-by-id control, or restore `data/clinic.db` from the CSV seed by running the pipeline again |
| Panel asks for a different month | The forecast slider goes to 6 months; any figure can be reproduced from `reports/metrics.json` |
