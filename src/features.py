"""Monthly modelling table, forecast features and daily profiles.

Daily takings are spiky and weekly totals still move 40% on average, so the
modelled target is the **monthly collections total**, driven by two components:

    collections = revenue per trading day  x  trading days in the month

The first component is estimated from history; the second is a planning
assumption the clinic controls (it knows its own schedule).  Splitting the two
is what makes the forecast beat "repeat last month", because trading days range
from 12 to 28 in this ledger and a raw month-total comparison confuses a short
month with a slow month.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

DEFAULT_TRADING_DAYS = 23.0
MONTH_FEATURES = ["rate_lag1", "rate_lag2", "rate_lag3",
                  "rate_roll3", "rate_roll6", "month_num",
                  "collected_lag1", "collected_roll4", "ndays_avg3"]


def load_daily(path: Path = PROCESSED / "daily_collections.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    return df[df["amount"] > 0].sort_values("date").reset_index(drop=True)


def load_monthly(path: Path = PROCESSED / "month_summary.csv") -> pd.DataFrame:
    df = pd.read_csv(path).sort_values(["year", "month"]).reset_index(drop=True)
    df["period"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" +
        df["month"].astype(int).astype(str).str.zfill(2) + "-01")
    return df


def monthly_table(daily: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    """Observed months with collections, trading days and revenue per day."""
    m = summary.copy()
    counts = (daily.assign(period=daily["date"].dt.to_period("M"))
                   .groupby("period").size().rename("ndays"))
    m["period_key"] = m["period"].dt.to_period("M")
    m = m.merge(counts, left_on="period_key", right_index=True, how="left")
    m["ndays"] = m["ndays"].fillna(0).astype(int)
    m = m[m["collected"] > 0].copy()
    m["rate"] = m["collected"] / m["ndays"]
    return m.sort_values("period").reset_index(drop=True)


def build_features(m: pd.DataFrame) -> pd.DataFrame:
    d = m.copy().reset_index(drop=True)
    d["month_num"] = d["period"].dt.month
    for lag in (1, 2, 3):
        d[f"rate_lag{lag}"] = d["rate"].shift(lag)
    d["rate_roll3"] = d["rate"].shift(1).rolling(3).mean()
    d["rate_roll6"] = d["rate"].shift(1).rolling(6).mean()
    d["collected_lag1"] = d["collected"].shift(1)
    d["collected_roll4"] = d["collected"].shift(1).rolling(4).mean()
    d["ndays_avg3"] = d["ndays"].shift(1).rolling(3).mean()
    return d.dropna(subset=MONTH_FEATURES).reset_index(drop=True)


def daily_profile(daily: pd.DataFrame) -> dict:
    """Weekday and day-of-month multipliers used to shape a monthly total."""
    overall = float(daily["amount"].mean())
    dow_mean = daily.groupby("dow")["amount"].mean()
    shown = daily["date"].dt.day
    bucket = pd.cut(shown, bins=[0, 7, 14, 21, 31],
                    labels=["1-7", "8-14", "15-21", "22-31"])
    bucket_mean = daily.groupby(bucket, observed=False)["amount"].mean()
    return {
        "overall_mean": overall,
        "median": float(daily["amount"].median()),
        "dow_mean": {int(k): float(v) for k, v in dow_mean.items()},
        "dow_multiplier": {int(k): float(v / overall) for k, v in dow_mean.items()},
        "dom_bucket_multiplier": {str(k): float(v / overall)
                                  for k, v in bucket_mean.items()},
        "trading_days": int(len(daily)),
        "p25": float(daily["amount"].quantile(0.25)),
        "p75": float(daily["amount"].quantile(0.75)),
        "p95": float(daily["amount"].quantile(0.95)),
    }


if __name__ == "__main__":
    daily = load_daily()
    summary = load_monthly()
    m = monthly_table(daily, summary)
    f = build_features(m)
    m.to_csv(PROCESSED / "monthly_table.csv", index=False)
    print(f"months {len(m)}  modelling rows {len(f)}")
    print(f"trading days per month: min {m.ndays.min()} max {m.ndays.max()} "
          f"mean {m.ndays.mean():.1f}")
    print(f"revenue per trading day: {m.rate.min():,.0f} to {m.rate.max():,.0f}")
