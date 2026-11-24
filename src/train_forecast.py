"""Run the backtest, pick the model, write metrics and the backtest figure.

Run:  python -m src.train_forecast
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.forecast import (backtest, candidates, choose, load_all,
                          residual_interval, summarise)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MODELS = ROOT / "models"


def main():
    daily, months, feats, profile = load_all()
    bt = backtest(feats)
    table = summarise(bt)
    specs = candidates()
    best = choose(specs, table)
    baseline = table[table["model"].isin(["last month", "4-month average"])].iloc[0]
    improvement = (baseline["mape"] - table.iloc[0]["mape"]) / baseline["mape"] * 100
    lo, hi = residual_interval(bt, best.name)

    MODELS.mkdir(parents=True, exist_ok=True)
    payload = {
        "target": "monthly collections (PHP)",
        "evaluation": "rolling origin, one month ahead, refit at each origin",
        "test_months": int(bt["origin"].nunique()),
        "train_months_first_origin": 6,
        "model": best.to_dict(),
        "backtest": {
            "chosen_mape": float(table.iloc[0]["mape"]),
            "chosen_mae": float(table.iloc[0]["mae"]),
            "chosen_within10": float(table.iloc[0]["within10"]),
            "baseline_model": baseline["model"],
            "baseline_mape": float(baseline["mape"]),
            "improvement_pct": float(improvement),
        },
        "interval_p10_p90": {"lo": lo, "hi": hi},
        "table": table.to_dict(orient="records"),
        "profile": profile,
        "data_through": str(pd.Timestamp(months["period"].iloc[-1]).date()),
        "observed_months": int(len(months)),
        "trading_days_mean": float(months["ndays"].mean()),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (MODELS / "model.json").write_text(json.dumps(payload, indent=2))
    (REPORTS / "metrics.json").write_text(json.dumps(payload, indent=2))
    bt.to_csv(REPORTS / "backtest_detail.csv", index=False)

    # --- figure
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(months["period"], months["collected"], label="actual",
            color="#1f3a93", linewidth=1.8, marker="o", markersize=3)
    chosen = bt[bt["model"] == best.name]
    ax.plot(chosen["period"], chosen["predicted"], label=f"forecast ({best.name})",
            color="#d35400", linewidth=1.6, marker="o", markersize=3)
    base_rows = bt[bt["model"] == baseline["model"]]
    ax.plot(base_rows["period"], base_rows["predicted"],
            label=f"baseline ({baseline['model']})", color="#7f8c8d",
            linestyle="--", linewidth=1.0)
    ax.set_title("Walk-forward backtest: monthly collections")
    ax.set_ylabel("PHP per month")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGURES / "forecast_backtest.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.barh(table["model"], table["mape"], color="#1f3a93")
    ax.set_xlabel("MAPE % (lower is better)")
    ax.set_title("Model comparison, out-of-sample")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "model_comparison.png", dpi=150)
    plt.close(fig)

    print(f"{'model':30s} {'MAPE':>7s} {'MAE':>9s} {'within10':>9s}")
    for r in table.itertuples():
        print(f"{r.model:30s} {r.mape:6.1f}% {r.mae:9,.0f} {r.within10:8.0f}%")
    print(f"\nchosen: {best.name}")
    print(f"improvement over {baseline['model']}: {improvement:.1f}%")
    print(f"80% interval per month: {lo:,.0f} to +{hi:,.0f}")


if __name__ == "__main__":
    main()
