"""Forecast engine: rolling-origin backtest, model selection, projection.

Two ideas keep this honest:

1. Every candidate predicts a month using only information available before
   that month.  The backtest walks forward one month at a time, refitting where
   needed, so the reported accuracy is out-of-sample.
2. The deployed model is a decomposable rule (revenue per trading day x
   assumed trading days), not an opaque fit.  The clinic can see the two
   numbers that produced the forecast, which matters more than a tenth of a
   percentage point of accuracy on 15 test months.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

DEFAULT_DAYS = 23.0
RIDGE_FEATURES = ["rate_lag1", "rate_lag2", "rate_lag3",
                  "rate_roll3", "rate_roll6", "month_num"]


@dataclass
class ModelSpec:
    name: str
    kind: str          # roll_rate | naive | ridge | gb
    window: int = 6
    days: float = DEFAULT_DAYS

    def to_dict(self) -> dict:
        return asdict(self)


def mape(actual, predicted) -> float:
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    mask = a != 0
    return float(np.mean(np.abs((p[mask] - a[mask]) / a[mask])) * 100)


def _fit_rate_model(kind: str, train: pd.DataFrame):
    X, y = train[RIDGE_FEATURES], train["rate"]
    if kind == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=3.0)).fit(X, y)
    return HistGradientBoostingRegressor(
        max_depth=2, learning_rate=0.08, max_iter=150, min_samples_leaf=4,
        l2_regularization=2.0, random_state=0).fit(X, y)


def predict_one(spec: ModelSpec, row: pd.Series, model=None) -> float:
    """Collections for a single month from its feature row."""
    if spec.kind == "naive_last":
        return float(row["collected_lag1"])
    if spec.kind == "naive_mean4":
        return float(row["collected_roll4"])
    if spec.kind == "roll_rate":
        col = "rate_roll3" if spec.window == 3 else "rate_roll6"
        return float(row[col] * spec.days)
    rate = float(model.predict(pd.DataFrame([row[RIDGE_FEATURES]]))[0])
    return rate * spec.days


def candidates() -> list[ModelSpec]:
    return [
        ModelSpec("last month", "naive_last"),
        ModelSpec("4-month average", "naive_mean4"),
        ModelSpec("rate x 23 days (3m)", "roll_rate", window=3),
        ModelSpec("rate x 23 days (6m)", "roll_rate", window=6),
        ModelSpec("ridge on rate", "ridge", days=DEFAULT_DAYS),
        ModelSpec("gradient boosting on rate", "gb", days=DEFAULT_DAYS),
    ]


def backtest(feats: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward evaluation, one month at a time, refitting learned models."""
    rows = []
    for i in range(len(feats)):
        test = feats.iloc[i]
        train = feats.iloc[:i]
        for spec in candidates():
            model = None
            if spec.kind in ("ridge", "gb") and len(train) >= 4:
                model = _fit_rate_model(spec.kind, train)
            elif spec.kind in ("ridge", "gb"):
                continue
            pred = predict_one(spec, test, model)
            rows.append({
                "model": spec.name, "origin": i,
                "period": test["period"], "actual": float(test["collected"]),
                "predicted": pred, "error": pred - float(test["collected"]),
                "ape": abs(pred - float(test["collected"])) / float(test["collected"]) * 100,
            })
    return pd.DataFrame(rows)


def summarise(bt: pd.DataFrame) -> pd.DataFrame:
    g = (bt.groupby("model")
           .agg(mape=("ape", "mean"), mae=("error", lambda e: float(np.mean(np.abs(e)))),
                rmse=("error", lambda e: float(np.sqrt(np.mean(e ** 2)))),
                n=("ape", "size"),
                within10=("ape", lambda s: float(np.mean(s <= 10) * 100)))
           .reset_index()
           .sort_values("mape"))
    return g


def choose(specs: list[ModelSpec], table: pd.DataFrame) -> ModelSpec:
    """Best backtest score, with a tie-break toward the explainable rule."""
    best = table.iloc[0]
    simple = table[table["model"].str.startswith(("rate", "last", "4-month"))]
    if not simple.empty:
        simple_best = simple.iloc[0]
        if simple_best["mape"] <= best["mape"] * 1.05:
            best = simple_best
    for spec in specs:
        if spec.name == best["model"]:
            return spec
    raise SystemExit("chosen model not found in candidate list")


def residual_interval(bt: pd.DataFrame, model_name: str) -> tuple[float, float]:
    err = bt.loc[bt["model"] == model_name, "error"].to_numpy()
    lo, hi = np.quantile(err, [0.1, 0.9])
    return float(lo), float(hi)


def project(months: pd.DataFrame, spec: ModelSpec, n: int = 3,
            days: float | None = None) -> pd.DataFrame:
    """Project the next n months from the last observed month."""
    m = months.copy()
    days = float(days if days is not None else spec.days)
    out = []
    for step in range(1, n + 1):
        last = m.iloc[-1]
        nxt = (pd.Timestamp(last["period"]) + pd.offsets.MonthBegin(1))
        rate_hist = m["rate"].to_numpy()
        collected_hist = m["collected"].to_numpy()
        ndays_hist = m["ndays"].to_numpy()
        row = {
            "period": nxt,
            "rate_lag1": rate_hist[-1],
            "rate_lag2": rate_hist[-2] if len(rate_hist) > 1 else rate_hist[-1],
            "rate_lag3": rate_hist[-3] if len(rate_hist) > 2 else rate_hist[-1],
            "rate_roll3": float(np.mean(rate_hist[-3:])),
            "rate_roll6": float(np.mean(rate_hist[-6:])),
            "month_num": nxt.month,
            "collected_lag1": collected_hist[-1],
            "collected_roll4": float(np.mean(collected_hist[-4:])),
            "ndays_avg3": float(np.mean(ndays_hist[-3:])),
        }
        if spec.kind == "roll_rate":
            rate = row["rate_roll6"] if spec.window == 6 else row["rate_roll3"]
            point = rate * days
        elif spec.kind == "naive_last":
            point = row["collected_lag1"]
            rate = point / days
        elif spec.kind == "naive_mean4":
            point = row["collected_roll4"]
            rate = point / days
        else:
            train = months.copy()
            train["rate_lag1"] = train["rate"].shift(1)
            train["rate_lag2"] = train["rate"].shift(2)
            train["rate_lag3"] = train["rate"].shift(3)
            train["rate_roll3"] = train["rate"].shift(1).rolling(3).mean()
            train["rate_roll6"] = train["rate"].shift(1).rolling(6).mean()
            train["month_num"] = pd.to_datetime(train["period"]).dt.month
            train = train.dropna(subset=RIDGE_FEATURES)
            model = _fit_rate_model(spec.kind, train)
            rate = float(model.predict(pd.DataFrame([row[RIDGE_FEATURES]]))[0])
            point = rate * days

        out.append({"period": nxt, "point": max(point, 0.0), "rate": max(rate, 0.0),
                    "assumed_days": days})
        m = pd.concat([m, pd.DataFrame([{
            "period": nxt, "collected": point, "ndays": days,
            "rate": point / days if days else 0.0}])], ignore_index=True)
    return pd.DataFrame(out)


def week_split(month_point: float, month_start: pd.Timestamp,
               profile: dict) -> pd.DataFrame:
    """Distribute a monthly projection across the weeks the clinic trades."""
    # JSON round-trips integer keys to strings; normalise before use.
    mult = {int(k): float(v) for k, v in profile["dow_multiplier"].items()}
    days = pd.date_range(month_start, month_start + pd.offsets.MonthEnd(0),
                         freq="D")
    weights = []
    for d in days:
        if d.weekday() == 6:      # Sundays are mostly closed
            w = 0.0
        else:
            w = mult.get(d.weekday(), 1.0)
        weights.append((d, w))
    wdf = pd.DataFrame(weights, columns=["date", "weight"])
    wdf["week_end"] = wdf["date"] + pd.to_timedelta(
        (6 - wdf["date"].dt.day_of_week), unit="D")
    grouped = wdf.groupby("week_end")["weight"].sum()
    grouped = grouped[grouped > 0]        # a week with no trading day earns nothing
    total = grouped.sum()
    if total <= 0:
        return pd.DataFrame(columns=["week_end", "point"])
    return pd.DataFrame({
        "week_end": grouped.index,
        "point": (grouped / total * month_point).to_numpy(),
    })


def load_all():
    from src.features import (build_features, daily_profile, load_daily,
                              load_monthly, monthly_table)
    daily = load_daily()
    summary = load_monthly()
    months = monthly_table(daily, summary)
    feats = build_features(months)
    return daily, months, feats, daily_profile(daily)
