"""Functional and algorithm tests for the pipeline.

These are the tests a panel can rerun: parser totals, validation behaviour,
category rules, database operations and the forecast's out-of-sample result.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db, parse_ledger, taxonomy  # noqa: E402
from src.features import build_features, load_daily, load_monthly, monthly_table  # noqa: E402
from src.forecast import backtest, candidates, summarise  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
MODELS = ROOT / "models"


@pytest.fixture(scope="module")
def parsed():
    daily, expenses, summary, issues = parse_ledger.parse()
    return daily, expenses, summary, issues


def test_parser_counts(parsed):
    daily, expenses, summary, issues = parsed
    assert summary["block_id"].nunique() == 21
    assert len(daily) == 478
    # 544 original lines + 474 inserted food lines (one per trading day)
    # + 11 backfilled rent lines
    assert len(expenses) == 1029


def test_daily_totals_tie_out_to_general_income(parsed):
    _, _, summary, _ = parsed
    tie_out = summary.dropna(subset=["general_income"])
    assert len(tie_out) == 21, "every block reports a General Income figure"
    assert (tie_out["tie_out_diff"].abs() < 0.005).all()


def test_known_data_issues_are_flagged(parsed):
    _, _, _, issues = parsed
    kinds = set(issues["kind"])
    # monthly totals now validate, so only the kept impossible date and the
    # two short months remain flagged
    assert kinds == {"invalid_date", "low_coverage"}
    assert (issues["kind"] == "invalid_date").sum() == 1


def test_expense_categories():
    assert taxonomy.rule_category("D") == "Personal"
    assert taxonomy.rule_category("d") == "Personal"
    assert taxonomy.rule_category("Food") == "Food"
    assert taxonomy.rule_category("Lab (Jessa Mae Case)") == "Lab Fees"
    assert taxonomy.rule_category("kimi") == "Wages"
    assert taxonomy.rule_category("rent") == "Rent"
    assert taxonomy.rule_category("solicitation") == "Unclassified"
    assert taxonomy.rule_category("Doctor 1") == "Personal"
    assert taxonomy.rule_category("Doctor 2") == "Wages"
    assert taxonomy.rule_category("Other Expenses") == "Unclassified"


def test_category_coverage():
    exp = pd.read_csv(PROCESSED / "expenses_categorized.csv")
    op = exp[exp["expense_type"] == "Operating"]
    share = op.loc[op["category"] == "Unclassified", "amount"].sum() / op["amount"].sum()
    assert share < 0.05, f"unclassified share {share:.1%} exceeds the 5% target"
    personal = exp[exp["expense_type"] == "Personal"]["amount"].sum()
    # former D (214,590) plus former Dianne (30,114.75), both now Doctor 1
    assert personal == pytest.approx(244_704.75, rel=1e-9)


def test_personal_spending_is_excluded_from_margin():
    exp = pd.read_csv(PROCESSED / "expenses_categorized.csv")
    assert set(exp["expense_type"].unique()) == {"Operating", "Personal"}
    assert (exp.loc[exp["category"] == "Personal", "expense_type"] == "Personal").all()


def test_forecast_beats_naive_baseline():
    model = json.loads((MODELS / "model.json").read_text())
    backtest_summary = model["backtest"]
    assert backtest_summary["chosen_mape"] < backtest_summary["baseline_mape"]
    assert backtest_summary["improvement_pct"] > 10


def test_backtest_is_walk_forward():
    months = monthly_table(load_daily(), load_monthly())
    feats = build_features(months)
    bt = backtest(feats)
    table = summarise(bt)
    assert table["mape"].min() < 20
    assert bt["origin"].nunique() == len(feats)
    assert (bt["predicted"] >= 0).all()


def test_database_crud_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        conn = db.init(rebuild=True, path=Path(tmp) / "test.db")
        before = db.frame(conn, "SELECT COUNT(*) n FROM expenses").iloc[0]["n"]
        db.add_expense(conn, "2026-11-01", "Supplies test", 100.0, "Supplies")
        after = db.frame(conn, "SELECT COUNT(*) n FROM expenses").iloc[0]["n"]
        assert after == before + 1

        row = db.frame(conn, "SELECT id, category FROM expenses ORDER BY id DESC LIMIT 1")
        rid = int(row.iloc[0]["id"])
        db.update_category(conn, rid, "Personal")
        got = db.frame(conn, f"SELECT category FROM expenses WHERE id = {rid}")
        assert got.iloc[0]["category"] == "Personal"

        db.delete_row(conn, "expenses", rid)
        assert db.frame(conn, "SELECT COUNT(*) n FROM expenses").iloc[0]["n"] == before
        conn.close()


def test_application_metrics_are_reproducible():
    analysis = json.loads((REPORTS / "analysis.json").read_text())
    assert analysis["kpis"]["months"] == 21
    assert analysis["kpis"]["trading_days"] == 474
    assert analysis["kpis"]["revenue_total"] == pytest.approx(2_333_800.0)
    assert analysis["kpis"]["personal_total"] == pytest.approx(244_704.75)
