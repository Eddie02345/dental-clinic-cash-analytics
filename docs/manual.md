# User Manual

## Starting the system

```bash
cd datsci
.venv/bin/streamlit run src/app/app.py
```

The browser opens at `http://localhost:8501`. No internet connection is needed
after the first run, and no login is required.

On first launch the system rebuilds its data from `Accounting.xlsx` if the
prepared files are missing. That takes about five seconds and only happens once.

## The four pages

### Dashboard

Shows the cash position for the whole period.

- **Collections**: total takings, average per trading day, operating margin, and
  the share of spending still uncategorized.
- **Monthly cash chart**: collections against operating expenses, with owner
  personal spending stacked separately.
- **Break-even**: what a month of rent and wages costs, and what that means per
  trading day.
- **Cost mix and demand pattern**: where the money goes, and which weekdays earn
  the most.

Read the margin as an upper bound. The note under it explains why.

### Forecast

1. Choose how many months ahead, from 1 to 6.
2. Set the number of trading days you expect in a month. The default is 22.6,
   the clinic's own average. Lower it for a month with holidays.
3. Read the projected collections per month, plus the low and high values. The
   high and low are the range the model hit 8 times out of 10 in backtesting.
4. The right-hand panel shows how accurate the model was on past months, so you
   can judge the projection rather than trust it blindly.
5. **Cash pacing** splits the first projected month into weeks. Use it for
   staffing and supply timing; it is a distribution of the monthly total, not a
   separate weekly forecast.

### Ledger

Two tabs, Expenses and Collections.

**Expenses**
- The table lists every expense line with its category.
- Click any category cell and pick a different one, then press **Save category
  changes**. Use this when the automatic categorization is wrong.
- **Add an expense**: type the label exactly as it appears in the ledger. The
  system suggests a category (for example, a staff name suggests Wages); confirm
  or change it before saving.
- To remove a line, enter its id and press delete.

**Collections**
- Lists the recorded trading days.
- **Add a trading day** for a day that was missed.

Personal spending stays in the ledger with the category `Personal`. It is
excluded from every cost and margin figure.

### Reports

- **Excel workbook**: the cleaned ledger, monthly cash, categorized expenses,
  the forecast and the backtest detail. Use this for filing.
- **Summary PDF**: two pages with the cash position, forecast, monthly chart and
  cost mix. Print it or forward it.
- **What the numbers mean**: a plain-language recap of the headline figures.

## Monthly routine

1. Add the month's daily collections in the Ledger, or re-import a workbook
   using the pipeline command below.
2. Add expense lines as they occur.
3. Correct any category the suggestion got wrong.
4. Open Forecast, set the trading days you expect next month, and note the
   projection.
5. Export the PDF for your records.

## Rebuilding from a new workbook

If the clinic supplies an updated spreadsheet with the same monthly block
layout:

```bash
cp new_workbook.xlsx data/raw/Accounting.xlsx
.venv/bin/python -m src.pipeline --force
```

This re-parses, re-categorizes, re-trains the model and reseeds the database.
Your edits in the app are replaced by the workbook contents, so export first if
you need them.

## If something looks wrong

| Symptom | Check |
|---|---|
| A month shows no expenses | `reports/parse_issues.csv`, it may be a month the clinic left blank |
| Forecast looks too high | The trading-days setting; 23 is the default, a holiday month needs fewer |
| A category is wrong | Edit it in the Ledger; the correction is saved to `labels.csv` on the next pipeline run |
| Numbers differ from the spreadsheet | The system uses the daily column and the logged expense rows, not the workbook's summary cells; differences are listed in the parse issues file |
