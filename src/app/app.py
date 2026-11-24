"""Streamlit application.

Run:  streamlit run src/app/app.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import theme  # noqa: E402
from src import db, export  # noqa: E402
from src.forecast import ModelSpec, load_all, project, week_split  # noqa: E402
from src.pipeline import run as run_pipeline  # noqa: E402
from src.taxonomy import CATEGORIES, rule_category  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
MODELS = ROOT / "models"

st.set_page_config(page_title="Clinic ledger", page_icon="🦷", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)
money = theme.money


# ---------------------------------------------------------------- bootstrap
@st.cache_resource(show_spinner="Preparing data and models…")
def bootstrap():
    run_pipeline(force=False, verbose=False)
    return db.init(rebuild=False)


@st.cache_data
def analysis() -> dict:
    return json.loads((REPORTS / "analysis.json").read_text())


@st.cache_data
def metrics() -> dict:
    return json.loads((REPORTS / "metrics.json").read_text())


@st.cache_data
def model_json() -> dict:
    return json.loads((MODELS / "model.json").read_text())


@st.cache_data
def monthly_cash() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "monthly_cash.csv", parse_dates=["period"])


@st.cache_data
def backtest_detail() -> pd.DataFrame:
    return pd.read_csv(REPORTS / "backtest_detail.csv", parse_dates=["period"])


@st.cache_data
def issues_frame() -> pd.DataFrame:
    path = REPORTS / "parse_issues.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


@st.cache_data
def projection(months_ahead: int, assumed_days: float) -> pd.DataFrame:
    spec = ModelSpec(**model_json()["model"])
    _, months, _, _ = load_all()
    return project(months, spec, n=months_ahead, days=assumed_days)


conn = bootstrap()


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown(
        '<div class="brand">Clinic ledger'
        '<span>Cash, cost and forecast for a dental practice</span></div>',
        unsafe_allow_html=True)
    st.write("")
    page = st.radio("View", ["Dashboard", "Forecast", "Ledger", "Reports"],
                    label_visibility="collapsed")
    st.divider()
    k = analysis()["kpis"]
    st.caption(f"Ledger through {pd.Timestamp(k['data_through']).strftime('%B %Y')}")
    st.caption(f"{k['trading_days']} trading days · {k['months']} months")
    st.caption(f"Forecast: {model_json()['model']['name']}")
    st.caption(f"Backtest error: {model_json()['backtest']['chosen_mape']:.1f}% MAPE")
    st.divider()
    with st.expander("Data quality"):
        st.caption("Problems carried from the workbook. Each one is flagged in "
                   "the pipeline rather than silently dropped.")
        issues = issues_frame()
        if issues.empty:
            st.write("No issues flagged.")
        else:
            st.dataframe(issues[["kind", "detail", "action"]],
                         hide_index=True, width="stretch")


# ---------------------------------------------------------------- dashboard
def dashboard():
    a = analysis()
    k = a["kpis"]
    fixed = k["fixed"]
    monthly = monthly_cash()

    st.title("Dashboard")
    st.markdown(theme.lede(
        "Twenty-one months of takings and spending. Owner personal spending is "
        "separated from clinic running costs, which is what makes a margin "
        "possible in the first place."), unsafe_allow_html=True)

    st.markdown(theme.band([
        ("Collections", money(k["revenue_total"]),
         f"{k['trading_days']} trading days"),
        ("Average trading day", money(k["revenue_per_trading_day"]),
         f"median {money(metrics()['profile']['median'])}"),
        ("Operating margin", f"{k['operating_margin']:.0%}",
         "upper bound, see note"),
        ("Owner personal", money(k["personal_total"]),
         f"{k['personal_share_of_spend']:.0%} of all spending"),
    ]), unsafe_allow_html=True)

    st.subheader("Monthly cash")
    st.plotly_chart(theme.monthly_cash(monthly), width="stretch",
                    config={"displayModeBar": False})
    st.caption("Spend bars are stacked: running costs in amber, the owner's "
               "personal lines in rust. The rust appears in bursts, not evenly, "
               "which is why repeating last month's total misleads.")

    st.divider()
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.subheader("Where the money goes")
        cats = pd.DataFrame(a["categories"])
        st.plotly_chart(theme.cost_mix(cats), width="stretch",
                        config={"displayModeBar": False})
        st.caption("Operating spend only. Owner personal is excluded from this "
                   "view and from the margin.")
    with right:
        st.subheader("What a month must clear")
        st.metric("Committed fixed cost", f"{money(fixed['committed_fixed_month'])}/month",
                  help="Typical rent plus average wages and draws")
        st.metric("Break-even per trading day",
                  money(fixed["fixed_per_trading_day"]))
        st.metric("Average monthly surplus", money(k["surplus_avg_month"]),
                  help="Collections minus operating expenses, before owner draws")
        st.caption(f"Rent is logged in only {fixed['rent_months_logged']} of "
                   f"{k['months']} months, so margin and surplus are upper bounds.")

    st.divider()
    st.subheader("Which days earn")
    c1, c2 = st.columns([1.25, 1], gap="large")
    with c1:
        st.plotly_chart(theme.weekday(metrics()["profile"]), width="stretch",
                        config={"displayModeBar": False})
    with c2:
        profile = metrics()["profile"]
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday"]
        tbl = pd.DataFrame({
            "day": names,
            "average": [round(profile["dow_mean"].get(str(i),
                            profile["dow_mean"].get(i, 0))) for i in range(7)],
            "against average": [f"{(profile['dow_multiplier'].get(str(i),
                                profile['dow_multiplier'].get(i, 1)) - 1) * 100:+.0f}%"
                                for i in range(7)],
        })
        tbl["average"] = tbl["average"].map(money)
        st.dataframe(tbl, hide_index=True, width="stretch")
        st.caption("Dotted rule marks the average trading day. Sunday is mostly "
                   "closed, 40 recorded against about 73 for a weekday, so the "
                   "weekly split treats it as zero.")


# ----------------------------------------------------------------- forecast
def forecast_page():
    m = model_json()
    k = analysis()["kpis"]
    bt_summary = m["backtest"]

    st.title("Forecast")
    st.markdown(theme.lede(
        "Monthly takings projected from revenue per trading day, multiplied by "
        "the number of days you expect to trade. Both inputs are visible, so you "
        "can argue with the answer."), unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1, 1.2], gap="large")
    months_ahead = c1.slider("Months ahead", 1, 6, 3)
    assumed_days = c2.number_input(
        "Trading days per month", min_value=10.0, max_value=31.0,
        value=round(k["trading_days"] / k["months"], 1), step=0.5, format="%.1f",
        help="The clinic traded 12 to 28 days a month, 22.6 on average.")
    proj = projection(months_ahead, assumed_days)
    lo, hi = m["interval_p10_p90"]["lo"], m["interval_p10_p90"]["hi"]

    with c3:
        st.metric(f"Projected collections, {months_ahead} month(s)",
                  money(float(proj["point"].sum())))
        st.caption("Shaded band is the 80% interval from backtest residuals. "
                   "A single month can land well away from the point, which is "
                   "why the table shows the bounds too.")

    st.plotly_chart(theme.projection(monthly_cash(), proj, lo, hi),
                    width="stretch", config={"displayModeBar": False})

    table = pd.DataFrame({
        "month": proj["period"].dt.strftime("%B %Y"),
        "trading days": proj["assumed_days"].round(0).astype(int),
        "per trading day": proj["rate"].round(0).map(money),
        "projected": proj["point"].round(0).map(money),
        "low": (proj["point"] + lo).round(0).map(money),
        "high": (proj["point"] + hi).round(0).map(money),
    })
    st.dataframe(table, hide_index=True, width="stretch")

    st.divider()
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        st.subheader("Cash pacing")
        first = proj.iloc[0]
        split = week_split(float(first["point"]), pd.Timestamp(first["period"]),
                           m["profile"])
        if not split.empty:
            st.plotly_chart(theme.pacing(split), width="stretch",
                            config={"displayModeBar": False})
        st.caption(f"First projected month, {pd.Timestamp(first['period']).strftime('%B %Y')}, "
                   "split by weekday weight with Sunday at zero. For staffing and "
                   "supplies, not a separate weekly model.")
    with right:
        st.subheader("How far to trust it")
        st.metric("Out-of-sample MAPE", f"{bt_summary['chosen_mape']:.1f}%",
                  delta=f"{bt_summary['improvement_pct']:.1f}% better than baseline",
                  delta_color="normal")
        st.write(f"Walk-forward test across {m['test_months']} months, refitting "
                 f"at every origin. The best naive baseline, "
                 f"{bt_summary['baseline_model']}, scored "
                 f"{bt_summary['baseline_mape']:.1f}%.")
        st.write(f"{bt_summary['chosen_within10']:.0f}% of months landed within "
                 f"10% of the actual total. Treat a single month as planning "
                 f"range, not a promise.")

    st.divider()
    st.subheader("Model comparison")
    st.plotly_chart(
        theme.backtest(backtest_detail(), m["model"]["name"],
                       bt_summary["baseline_model"]),
        width="stretch", config={"displayModeBar": False})
    table = pd.DataFrame(m["table"])[["model", "mape", "mae", "within10"]]
    table.columns = ["model", "MAPE %", "MAE", "within 10%"]
    table["MAPE %"] = table["MAPE %"].round(1).astype(str) + "%"
    table["MAE"] = table["MAE"].round(0).map(money)
    table["within 10%"] = table["within 10%"].round(0).astype(int).astype(str) + "%"
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("The chosen rule is the simplest model that won. Two learned "
               "models scored worse on absolute error, which is reported rather "
               "than hidden.")


# ------------------------------------------------------------------- ledger
def ledger_page():
    st.title("Ledger")
    st.markdown(theme.lede(
        "The clinic's working copy. The parsed spreadsheets stay untouched; "
        "edits here change the local database only."), unsafe_allow_html=True)

    tab_exp, tab_daily = st.tabs(["Expenses", "Collections"])

    with tab_exp:
        df = db.frame(conn, "SELECT id, date, label_raw, amount, category, "
                            "expense_type, source FROM expenses "
                            "ORDER BY date DESC, id DESC")
        total = float(df["amount"].sum())
        op = float(df.loc[df["expense_type"] == "Operating", "amount"].sum())
        st.markdown(theme.band([
            ("Expense lines", f"{len(df):,}", "from the ledger and manual entry"),
            ("Total recorded", money(total), "operating plus personal"),
            ("Operating", money(op), "excluded personal"),
            ("Personal", money(total - op), "label D and manual tags"),
        ]), unsafe_allow_html=True)

        edit = df.copy()
        edit["amount"] = edit["amount"].round(2)
        edited = st.data_editor(
            edit[["id", "date", "label_raw", "amount", "category"]],
            hide_index=True, width="stretch", height=360,
            column_config={
                "id": st.column_config.NumberColumn("id", disabled=True),
                "category": st.column_config.SelectboxColumn(
                    "category", options=CATEGORIES, required=True),
            },
            key="expense_editor")

        c1, c2 = st.columns([1, 2.4])
        if c1.button("Save category changes", type="primary"):
            changes = 0
            for _, row in edited.iterrows():
                original = df.loc[df["id"] == row["id"], "category"]
                if not original.empty and original.iloc[0] != row["category"]:
                    db.update_category(conn, int(row["id"]), row["category"])
                    changes += 1
            st.cache_data.clear()
            st.success(f"Updated {changes} line(s).")
            st.rerun()
        c2.caption("Pick a category in the table, then save. Personal keeps a "
                   "line out of every cost and margin figure. A blank date means "
                   "the ledger recorded the month but not the day.")

        with st.expander("Add or remove a line"):
            with st.form("add_expense", clear_on_submit=True):
                c1, c2 = st.columns(2)
                d = c1.date_input("Date", value=date.today())
                amount = c2.number_input("Amount (₱)", min_value=1.0, step=50.0)
                label = st.text_input("Label, as typed in the ledger")
                suggestion = rule_category(label) if label else "Unclassified"
                st.caption(f"Suggested category: {suggestion}")
                category = st.selectbox(
                    "Category", CATEGORIES,
                    index=CATEGORIES.index(suggestion)
                    if suggestion in CATEGORIES else 0)
                if st.form_submit_button("Add expense", type="primary"):
                    db.add_expense(conn, d.isoformat(), label, amount, category)
                    st.cache_data.clear()
                    st.success("Expense added.")
                    st.rerun()

            c1, c2 = st.columns([1, 2])
            del_id = c1.number_input("Line id", min_value=1, step=1,
                                     key="del_exp")
            if c2.button("Delete line", key="del_exp_btn"):
                db.delete_row(conn, "expenses", int(del_id))
                st.cache_data.clear()
                st.rerun()

    with tab_daily:
        d = db.frame(conn, "SELECT id, date, amount, source FROM daily_collections "
                           "ORDER BY date DESC")
        st.markdown(theme.band([
            ("Trading days", f"{len(d):,}", "recorded in the ledger"),
            ("Collections", money(float(d["amount"].sum())), "sum of the daily column"),
            ("Average day", money(float(d["amount"].mean())), "all trading days"),
            ("Largest day", money(float(d["amount"].max())), "single day record"),
        ]), unsafe_allow_html=True)
        st.dataframe(d.head(200), hide_index=True, width="stretch", height=320)

        with st.expander("Add a trading day"):
            with st.form("add_day", clear_on_submit=True):
                c1, c2 = st.columns(2)
                d0 = c1.date_input("Date", value=date.today(), key="day_date")
                amt = c2.number_input("Collections (₱)", min_value=0.0, step=100.0)
                if st.form_submit_button("Add day", type="primary"):
                    db.add_collection(conn, d0.isoformat(), amt)
                    st.cache_data.clear()
                    st.success("Trading day added.")
                    st.rerun()


# ------------------------------------------------------------------ reports
def reports_page():
    k = analysis()["kpis"]
    m = model_json()

    st.title("Reports")
    st.markdown(theme.lede(
        "Two files for the clinic's filing and one set of figures for the "
        "project write-up. Both are generated from the same pipeline as the "
        "screen you are looking at."), unsafe_allow_html=True)

    st.markdown(theme.band([
        ("Operating margin", f"{k['operating_margin']:.0%}", "upper bound"),
        ("Average surplus", money(k["surplus_avg_month"]), "before owner draws"),
        ("Personal share", f"{k['personal_share_of_spend']:.0%}", "of all spending"),
        ("Forecast error", f"{m['backtest']['chosen_mape']:.1f}%", "out of sample"),
    ]), unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.subheader("Excel workbook")
        st.write("Cleaned ledger, monthly cash, categorized expenses, forecast "
                 "and backtest detail in one file.")
        if st.button("Build workbook"):
            st.session_state["xlsx"] = export.excel_bytes()
        if "xlsx" in st.session_state:
            st.download_button("Download clinic_summary.xlsx",
                               data=st.session_state["xlsx"],
                               file_name="clinic_summary.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c2:
        st.subheader("Summary PDF")
        st.write("Two pages: cash position, forecast, monthly chart and cost "
                 "mix, ready to print or forward.")
        if st.button("Build PDF"):
            st.session_state["pdf"] = export.pdf_bytes()
        if "pdf" in st.session_state:
            st.download_button("Download clinic_summary.pdf",
                               data=st.session_state["pdf"],
                               file_name="clinic_summary.pdf",
                               mime="application/pdf")

    st.divider()
    st.subheader("Reading the numbers")
    st.markdown(f"""
- Collections of **{money(k['revenue_total'])}** over {k['months']} months and
  {k['trading_days']} trading days.
- Operating margin of **{k['operating_margin']:.1%}** on logged running costs.
  An upper bound: rent appears in {k['fixed']['rent_months_logged']} of {k['months']} months.
- Owner personal of **{money(k['personal_total'])}**, {k['personal_share_of_spend']:.1%}
  of all recorded spending, kept out of margin.
- **{money(k['fixed']['fixed_per_trading_day'])}** per trading day covers rent and
  wages alone.
- Forecast error **{m['backtest']['chosen_mape']:.1f}%** MAPE out of sample, against
  **{m['backtest']['baseline_mape']:.1f}%** for the best naive baseline.
""")

    with st.expander("Files behind this screen"):
        for p in sorted([*FIGURES.glob("*.png"), *REPORTS.glob("*.json"),
                         *REPORTS.glob("*.csv")]):
            st.caption(f"{p.relative_to(ROOT)}")


# --------------------------------------------------------------------- main
if page == "Dashboard":
    dashboard()
elif page == "Forecast":
    forecast_page()
elif page == "Ledger":
    ledger_page()
else:
    reports_page()
