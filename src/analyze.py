"""Descriptive analytics: cash position, cost mix, break-even, day profiles.

Everything here is aggregated from the parsed CSVs, so the numbers in the
dashboard, the report and the defence slides all come from one place.

Run:  python -m src.analyze
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

PALETTE = {"actual": "#1f3a93", "operating": "#16a085", "personal": "#c0392b",
           "personal_bar": "#e67e22", "muted": "#7f8c8d", "accent": "#d35400"}


def load():
    daily = pd.read_csv(PROCESSED / "daily_collections.csv", parse_dates=["date"])
    daily = daily[daily["amount"] > 0].copy()
    exp = pd.read_csv(PROCESSED / "expenses_categorized.csv")
    months = pd.read_csv(PROCESSED / "month_summary.csv")
    months["period"] = pd.to_datetime(
        months["year"].astype(int).astype(str) + "-" +
        months["month"].astype(int).astype(str).str.zfill(2) + "-01")
    return daily, exp, months.sort_values("period").reset_index(drop=True)


def monthly_frame(months: pd.DataFrame, exp: pd.DataFrame) -> pd.DataFrame:
    op = (exp[exp["expense_type"] == "Operating"]
          .groupby("block_id")["amount"].sum().rename("operating"))
    per = (exp[exp["expense_type"] == "Personal"]
           .groupby("block_id")["amount"].sum().rename("personal"))
    counts = (pd.read_csv(PROCESSED / "daily_collections.csv", parse_dates=["date"])
                .query("amount > 0")
                .groupby("block_id").size().rename("trading_days"))
    m = (months[["block_id", "period", "collected"]]
         .merge(op, on="block_id", how="left")
         .merge(per, on="block_id", how="left")
         .merge(counts, on="block_id", how="left"))
    m[["operating", "personal"]] = m[["operating", "personal"]].fillna(0.0)
    m["trading_days"] = m["trading_days"].fillna(0).astype(int)
    m["surplus"] = m["collected"] - m["operating"]
    m["total_spend"] = m["operating"] + m["personal"]
    return m


def category_frame(exp: pd.DataFrame) -> pd.DataFrame:
    op = exp[exp["expense_type"] == "Operating"]
    total = float(op["amount"].sum())
    g = (op.groupby("category")
           .agg(total=("amount", "sum"), entries=("amount", "size"))
           .reset_index())
    g["share"] = g["total"] / total
    return g.sort_values("total", ascending=False).reset_index(drop=True)


def fixed_cost(exp: pd.DataFrame, months: int, trading_days: float) -> dict:
    rent = exp[exp["category"] == "Rent"]["amount"]
    wages = exp[exp["category"] == "Wages"]["amount"]
    rent_rows = exp[exp["category"] == "Rent"]
    rent_typical = float(rent.median()) if len(rent) else 0.0
    rent_logged_months = int(rent_rows["block_id"].nunique())
    fixed_month = rent_typical + float(wages.sum()) / months
    return {
        "rent_typical_month": rent_typical,
        "rent_months_logged": rent_logged_months,
        "wages_total": float(wages.sum()),
        "wages_avg_month": float(wages.sum()) / months,
        "committed_fixed_month": fixed_month,
        "fixed_per_trading_day": fixed_month / trading_days if trading_days else 0.0,
    }


def figures(daily, monthly, cats, profile):
    FIGURES.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    x = np.arange(len(monthly))
    ax.bar(x, monthly["collected"], color=PALETTE["actual"], alpha=0.85,
           label="collections")
    ax.bar(x, monthly["operating"], color=PALETTE["operating"], alpha=0.85,
           label="operating expenses")
    ax.bar(x, monthly["personal"], bottom=monthly["operating"],
           color=PALETTE["personal"], alpha=0.75, label="owner personal")
    ax.set_xticks(x[::2])
    ax.set_xticklabels([p.strftime("%b %y") for p in monthly["period"]][::2],
                       rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("PHP")
    ax.set_title("Monthly collections against operating and personal spending")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "monthly_cash.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    top = cats.head(8)
    ax.barh(top["category"], top["total"], color=PALETTE["operating"])
    for i, row in top.iterrows():
        ax.text(row["total"], list(top.index).index(i),
                f'  {row["share"]:.0%}', va="center", fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("PHP (operating only, excludes owner personal)")
    ax.set_title("Cost mix, 21 months")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "cost_mix.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow = {int(k): float(v) for k, v in profile["dow_mean"].items()}
    vals = [dow.get(i, 0.0) for i in range(7)]
    ax.bar(names, vals, color=PALETTE["actual"])
    ax.axhline(profile["overall_mean"], color=PALETTE["accent"], linestyle="--",
               linewidth=1.2, label=f'avg trading day {profile["overall_mean"]:,.0f}')
    ax.set_ylabel("PHP per trading day")
    ax.set_title("Average takings by weekday")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIGURES / "weekday_profile.png", dpi=150)
    plt.close(fig)


def main():
    daily, exp, months = load()
    monthly = monthly_frame(months, exp)
    cats = category_frame(exp)
    profile = json.loads((REPORTS / "metrics.json").read_text())["profile"] \
        if (REPORTS / "metrics.json").exists() else None
    if profile is None:
        from src.features import daily_profile
        profile = daily_profile(daily)

    trading_days = float(monthly["trading_days"].mean())
    revenue = float(monthly["collected"].sum())
    operating = float(monthly["operating"].sum())
    personal = float(monthly["personal"].sum())
    fixed = fixed_cost(exp, len(monthly), trading_days)

    kpis = {
        "months": int(len(monthly)),
        "trading_days": int(len(daily)),
        "revenue_total": revenue,
        "revenue_avg_month": revenue / len(monthly),
        "revenue_per_trading_day": revenue / len(daily),
        "operating_total": operating,
        "operating_avg_month": operating / len(monthly),
        "personal_total": personal,
        "personal_share_of_spend": personal / (operating + personal),
        "operating_margin": (revenue - operating) / revenue,
        "surplus_avg_month": (revenue - operating) / len(monthly),
        "surplus_last_month": float(monthly["surplus"].iloc[-1]),
        "data_through": str(monthly["period"].iloc[-1].date()),
        "unclassified_share_of_operating": float(
            cats.loc[cats["category"] == "Unclassified", "share"].sum()),
        "fixed": fixed,
    }

    payload = {
        "kpis": kpis,
        "monthly": [
            {"period": p.strftime("%Y-%m"), "collected": float(c),
             "operating": float(o), "personal": float(pe),
             "surplus": float(s), "trading_days": int(td)}
            for p, c, o, pe, s, td in zip(
                monthly["period"], monthly["collected"], monthly["operating"],
                monthly["personal"], monthly["surplus"], monthly["trading_days"])
        ],
        "categories": cats.to_dict(orient="records"),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "analysis.json").write_text(json.dumps(payload, indent=2))
    monthly.to_csv(PROCESSED / "monthly_cash.csv", index=False)
    figures(daily, monthly, cats, profile)

    print(f"months {kpis['months']}  trading days {kpis['trading_days']}")
    print(f"revenue {revenue:,.0f}  operating {operating:,.0f}  personal {personal:,.0f}")
    print(f"operating margin {kpis['operating_margin']:.1%} (upper bound)")
    print(f"avg surplus {kpis['surplus_avg_month']:,.0f}/month")
    print(f"committed fixed {fixed['committed_fixed_month']:,.0f}/month "
          f"= {fixed['fixed_per_trading_day']:,.0f}/trading day")
    print(f"rent logged in {fixed['rent_months_logged']} of {kpis['months']} months")
    print(f"unclassified {kpis['unclassified_share_of_operating']:.1%} of operating")


if __name__ == "__main__":
    main()
