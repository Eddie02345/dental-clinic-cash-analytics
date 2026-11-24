# Dental Clinic Ledger (`Accounting.xlsx`): What We Can Mine

## What's actually in the file

It's a real clinic ledger, not a table. One sheet, 840 rows, 21 monthly blocks from **February 2025 to October 2026**, each block holding three separate things side by side:

- **Daily cash collections**: day number + amount, one row per calendar day (478 recorded days, 474 with money).
- **Expense log**: free-text label + amount, 544 entries, **97 distinct labels**.
- **Channel reconciliation**: GCash and BDO/BPI online payments with running balances and timestamps, plus per-month General Income and Total Expenses.

Measured totals: **₱2,333,800 collected** against **₱1,190,767 logged expenses**. Monthly revenue runs from ₱34,650 to ₱165,400. Daily collections: median ₱3,600, mean ₱4,924, max ₱29,800. Sundays are mostly absent (40 recorded vs ~73 for a weekday), so the clinic is closed or unlogged on Sundays.

## What you cannot do with it

There is no patient-level data, no treatment codes, no visit counts. Col A is a day number, so each amount is a day total, not a transaction. That rules out customer segmentation, RFM, and market basket analysis of treatments. If you propose "which services are availed together," you'll have nothing to feed it. Say so in the proposal before the panel asks.

## The project to build

**"Data Mining-Based Dental Clinic Revenue Forecasting and Expense Analytics System"**

| Rubric technique | What you implement | Why it fits |
|---|---|---|
| **Prediction** | Daily revenue forecast (regression with day-of-week, day-of-month, payday, lag features) | 478 observations is enough for a class-grade model, and it produces a real accuracy number for the evaluation deliverable |
| **Classification** | Auto-tag free-text expenses into Food, Wages, Lab, Rent, Supplies, Transfers | Directly fixes the ₱263,717 (22%) of spending that is currently unclassifiable |
| **Pattern discovery** (optional) | Anomaly flags on days where revenue collapses or expense outliers appear | Catches entry errors and unusual cash-outs; cheap to add |

Three findings the data already gives you, usable as the client-problem section:

1. **22% of spend is unmapped.** Labels like "D" (57 entries), "Ataw", "viscus", "winston" make ₱263,717 unreadable. The owner cannot see the cost mix from this file.
2. **Fixed costs eat a stable share.** Rent runs about ₱41,000/month on the entries that say "rent", wages and draws about ₱360,000 across 21 months. Average revenue is ₱111,133/month, so the margin is roughly 45 to 50%, and the clinic needs about ₱2,800 per open day just to cover rent and wages. Break-even per day is the single most useful number you can hand them.
3. **Demand has a mid-month pulse.** Avg revenue by day-of-month peaks at days 13, 17, 22, 23 and 31 (₱6,300 to ₱7,700) versus the ₱4,924 base. That is a testable payday effect and a nice chart.

## Data problems to fix before modeling

- 4 zero-value days and one impossible date: **Feb 29, 2026** recorded at ₱11,800.
- Missing days: 478 recorded out of roughly 640 calendar days, with Sundays almost all absent.
- Duplicate month headers (March 2025 and March 2026 both appear as "MARCH"), so never parse by month name; parse by block position.
- Summary column disagrees with the log in places: December 2025 shows Total Expenses ₱41,404 while logged entries sum to ₱98,343, and February 2025 has no total at all. Daily collections do tie out to General Income every month, so treat the day column as the source of truth.
- Typos in expense dates: "10/13/2006", "Augsut 26, 2026", "Feruary 27, 2026".
- **Patient names inside lab entries** ("Charmeon Case", "Jessa Mae Case", "PJ's case", "Edison Case", "Dacaimat"). Redact these before the file goes in a repo, a report, or a demo.
- Staff real first names on wage lines. Ask the owner whether to generalize them to "Wage 1, Wage 2" for the submission.

One question for the owner settles the biggest ambiguity: **what does "D" mean?** It appears 57 times for ₱1,000 to ₱45,000. If it is dentist draw, your margin math changes; if it is a supplier, your cost mix changes.

## Honest limits on the model

Daily clinic revenue is spiky (₱350 to ₱29,800), and 478 rows is small. Do not promise 90% accuracy. Build a naive baseline (trailing 7-day mean, and same-weekday-last-week), then report **MAE in pesos and MAPE against that baseline**. A model that beats the naive baseline by 15 to 20% MAPE is a credible result and a defensible evaluation section.

## Scope options

- **Full**: parser + tidy CSVs + expense auto-tagger + forecast + Streamlit dashboard with break-even line, monthly cost mix, and forecast. Two techniques, strong demo, real handover value.
- **Lean**: forecast only. Cleanest two-week build, but weaker "system" story and leaves the 22% unclassified problem untouched.
- **Max**: full plus anomaly flags and a GCash/BDO reconciliation check that compares running balances to recorded flows. Nice-to-have, adds a third technique.
