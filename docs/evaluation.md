# Testing and Evaluation Results

## 1. Functional testing

Run: `.venv/bin/python -m pytest tests -q` → **16 passed**

| Test | What it proves |
|---|---|
| `test_parser_counts` | 21 blocks, 478 day rows, 1029 expense lines |
| `test_daily_totals_tie_out_to_general_income` | every block's daily sum equals the workbook's own monthly total, zero difference |
| `test_known_data_issues_are_flagged` | the impossible date and the two short months are reported; every month's totals validate, nothing else is flagged |
| `test_expense_categories` | `Doctor 1` maps to Personal, `Doctor 2` to Wages, `Lab (Patient case)` to Lab Fees, `solicitation` stays Unclassified |
| `test_category_coverage` | unclassified spend is under 5% of operating value; personal spend equals ₱244,705 |
| `test_personal_spending_is_excluded_from_margin` | no personal row is ever typed as operating |
| `test_forecast_beats_naive_baseline` | the chosen model beats the best naive baseline by at least 10% |
| `test_backtest_is_walk_forward` | one prediction per origin, no origin sees its own future, no negative forecasts |
| `test_database_crud_roundtrip` | add, update category, delete on a temporary database |
| `test_application_metrics_are_reproducible` | dashboard figures match the source data |
| `test_page_renders` (x4) | Dashboard, Forecast, Ledger and Reports each render without an exception |
| `test_forecast_page_shows_backtest` | the forecast page surfaces the out-of-sample error, not just a number |
| `test_ledger_pages_have_tables` | both ledger tabs load |

The app tests use Streamlit's `AppTest` harness, so they exercise the real
script, not a mock.

## 2. Algorithm evaluation

Protocol: walk-forward, one month ahead, 15 origins, learned models refitted at
every origin. Metrics computed on out-of-sample predictions only.

| Model | MAPE | MAE (PHP) | Within 10% |
|---|---|---|---|
| **rate x 23 days (6m)** | **18.8%** | **21,971** | **40%** |
| gradient boosting on rate | 20.1% | 29,099 | 36% |
| rate x 23 days (3m) | 22.6% | 25,604 | 27% |
| 4-month average (best baseline) | 22.7% | 26,156 | 27% |
| ridge on rate | 23.2% | 31,809 | 36% |
| last month | 26.2% | 31,766 | 20% |

- Relative improvement of the chosen model over the best baseline: **16.8%**.
- 80% prediction interval from residuals: **₱-45,921 to ₱+28,797** per month.
- Interpretation: about two months in five land within 10% of the actual total.
  This is a planning aid, not a promise.

### Why the learned models did not win

Gradient boosting and ridge had the same information as the rate rule but
produced worse MAE (₱29,099 and ₱31,809 against ₱21,971). With 15 training
windows and a level that shifts, they fit noise. This is reported rather than
hidden: on a 21-month sample, a transparent two-number model is the better
engineering choice, and the comparison is the evidence for that claim.

## 3. Dataset validation results

| Check | Result |
|---|---|
| Blocks parsed | 21 of 21 |
| Daily sums matching General Income | 21 of 21, difference 0.00 |
| Expense lines recovered | 1029 |
| Expense total recovered | ₱1,883,075 |
| Personal spending isolated | ₱244,705 (13.0% of spend) |
| Unclassified operating spend | 3.3% (target under 5%) |
| Impossible dates | 1, flagged |
| Months with incomplete expense logs | none: rent in 21 of 21 months, every Total Expenses cell matches the logged rows |

## 4. Client feedback

Pending. The plan is to send the exported PDF and a five-question form to the
clinic owner and record the reply verbatim here.

Questions being asked:

1. Is the 22.6 trading days per month figure about right for a normal month?
2. Does the break-even figure of ₱2,529 per trading day match your experience?
3. Are the wage and rent figures in the right order of magnitude?
4. Is there anything in the cost mix that looks miscategorized?
5. Would you use the monthly PDF, the Excel file, or both?

## 5. Demonstration checklist

- Raw workbook opened, one block visible.
- Parser run live, tie-out table shown passing.
- Category mapping and the Personal split shown.
- Model comparison table and the backtest figure shown.
- App: dashboard, forecast with the accuracy panel, ledger edit, exports.
- Limitations stated before they are asked: 21 months, incomplete expense log,
  day totals only.
