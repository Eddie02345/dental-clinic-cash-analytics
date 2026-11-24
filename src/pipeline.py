"""Run the whole data pipeline end to end.

    python -m src.pipeline [--force]

Steps: parse the workbook, categorize expenses, backtest and select the
forecast model, compute the analytics and figures, then reseed the SQLite
working copy.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from src import analyze, db, parse_ledger, taxonomy, train_forecast
from src.features import (build_features, load_daily, load_monthly,
                          monthly_table)

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
MODELS = ROOT / "models"


def artifacts_exist() -> bool:
    required = [
        PROCESSED / "daily_collections.csv",
        PROCESSED / "expenses_categorized.csv",
        PROCESSED / "labels.csv",
        MODELS / "model.json",
        REPORTS / "analysis.json",
        REPORTS / "metrics.json",
    ]
    return all(p.exists() for p in required)


def run(force: bool = False, verbose: bool = True) -> dict:
    if artifacts_exist() and not force:
        return {"skipped": True}

    started = time.time()
    steps = []

    daily, expenses, summary, issues = parse_ledger.parse()
    steps.append(("parse", parse_ledger.write_outputs(daily, expenses, summary, issues)))

    categorized = taxonomy.categorize(pd.read_csv(PROCESSED / "expenses.csv"))
    categorized.to_csv(PROCESSED / "expenses_categorized.csv", index=False)
    exp_stats = taxonomy.summary(categorized)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "expense_summary.json").write_text(json.dumps(exp_stats, indent=2))
    steps.append(("taxonomy", exp_stats))

    months = monthly_table(load_daily(), load_monthly())
    months.to_csv(PROCESSED / "monthly_table.csv", index=False)
    build_features(months).to_csv(PROCESSED / "features.csv", index=False)
    steps.append(("features", {"months": int(len(months))}))

    if verbose:
        train_forecast.main()
        analyze.main()
    else:
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            train_forecast.main()
            analyze.main()
    steps.append(("forecast+analysis", {"ok": True}))

    db.init(rebuild=True).close()
    steps.append(("db", {"ok": True}))

    elapsed = time.time() - started
    if verbose:
        print(f"pipeline finished in {elapsed:.1f}s")
    return {"skipped": False, "seconds": elapsed, "steps": steps}


if __name__ == "__main__":
    import sys

    result = run(force="--force" in sys.argv)
    if result.get("skipped"):
        print("artifacts present, nothing to do (use --force to rebuild)")
