# Project Proposal

**Title:** Data Mining-Based Dental Clinic Revenue Forecasting and Expense Analytics System
**Client:** Dental clinic, a micro enterprise (name withheld from the public copy; supplied the ledger `Accounting.xlsx`)
**Technique:** Prediction (regression-based forecasting with a walk-forward evaluation)
**Dataset:** 21 monthly ledger blocks, February 2025 to October 2026

## 1. Client background

The clinic is a small dental practice that records its daily takings and its
spending in one spreadsheet. There are 474 recorded trading days across 21
months, averaging 22.6 trading days per month, and 1029 expense lines typed as
free text. Collections total ₱2,333,800 over the period, peaking at ₱165,400 in
December 2025 and February 2026.

## 2. Existing problem

Three problems come from the same file:

1. **Profit cannot be computed.** Owner personal spending was entered in the same
   expense column as clinic costs (redacted to the label `Doctor 1` in the
   working copy). It totals ₱244,705, or 13.0% of all recorded spending, and it
   ranges from ₱0 in six months to ₱46,500 in March 2026, where it was 82.4%
   of that month's recorded costs. Any profit figure from this sheet mixes the
   business with the household.
2. **Spending was unreadable.** Expense labels were free text across 97 variants:
   `Food`, `food`, `FOOD`, personal names for wages, shop shorthand such as
   `shoppe (a3 3m)`, single letters, and patient surnames inside lab-case
   labels. Payee and patient names are now redacted (`Doctor 1`..`Doctor 16`,
   `Other Expenses`, `Patient`), one food line per trading day was added for
   modelling, and rent was normalized to every month, leaving 77 distinct
   labels with 3.3% of operating value unclassified.
3. **No forward view.** The clinic has no way to estimate next month's cash, and
   its own month totals swing with the number of trading days, which ranged from
   12 to 28, so month-to-month comparison misleads.

## 3. Objectives

- Separate operating costs from owner personal spending and report a true
  operating margin.
- Categorize every expense line to within 5% of operating value left unknown.
- Produce a one to three month cash forecast with an out-of-sample accuracy
  figure, not an anecdotal one.
- Deliver a usable system the clinic can run offline, with Excel and PDF
  exports for its monthly filing.

## 4. Proposed solution

A local web application (Streamlit and SQLite) with four views: a dashboard of
cash position and cost mix, a forecast page, an editable ledger, and a reports
page. The data-mining component is a monthly collections forecast built on a
two-component model:

```
collections(t) = revenue per trading day(t) x trading days(t)
```

The first component is estimated from history with a trailing six-month mean,
and the second is a planning assumption the clinic sets. This decomposition is
the key design choice: raw month totals confound a short month with a slow
month, and separating rate from volume is what makes the forecast beat the
naive baselines.

## 5. Methodology

1. **Parse.** Split the workbook's monthly blocks into four keyed tables
   (daily collections, expenses, month summary, validation issues), keyed on
   block position rather than month name, because two March blocks exist.
2. **Validate.** Every block's daily sum must equal the workbook's own
   `General Income` cell. This passes for all 21 blocks with zero difference.
3. **Clean.** Normalize and categorize labels with an ordered ruleset; write
   the mapping to a file the clinic can correct.
4. **Model.** Compare six candidates on a walk-forward backtest with 15
   one-month-ahead origins: last month, four-month average, two rate rules,
   ridge regression on rate features, and gradient boosting on rate features.
5. **Evaluate.** Report MAPE and MAE per model, choose the best, and publish
   the interval implied by its residuals.
6. **Deliver.** App, exports, manual and demo script.

## 6. Selected data mining technique

**Prediction**, per the guidelines' category "estimates future outcomes based
on historical data". The model is evaluated out of sample and compared against
naive baselines, which is what makes the accuracy claim meaningful.

Classification and association rule mining were considered and rejected with
reasons: there is no patient-level data for segmentation or basket analysis,
and daily expense events are too sparse (1029 lines over 21 months, dominated
by one-food-line-per-day entries) for association rules to produce defensible
support levels.

## 7. Expected output

- Operating margin of 29.8% (upper bound, computed on normalized rent and
  modelled food lines) against a headline 13.0% of spending that is personal.
- Break-even of ₱2,529 per trading day for rent and wages alone.
- A three-month projection: ₱113,982 for November 2026, ₱115,093 for December,
  ₱114,614 for January 2027.
- Accuracy: 18.8% MAPE out of sample against 22.7% for the best naive baseline.

## 8. Scope limits

Out of scope: patient records, treatment mix, POS integration, tax reporting,
multi-branch and multi-user support, and a trained expense classifier (rules
are used instead and described as preprocessing, not as a technique).
