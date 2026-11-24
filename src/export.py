"""Excel and PDF exports for the clinic's monthly filing.

The Excel workbook is the handover artifact: it holds the cleaned ledger, the
monthly cash summary, the cost mix, the forecast and the backtest detail.  The
PDF is the one-page summary the owner can print or forward.
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"


def _monthly() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "monthly_cash.csv")


def _categories() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "expenses_categorized.csv")


def _forecast_frame() -> pd.DataFrame | None:
    from src.forecast import ModelSpec, load_all, project

    path = ROOT / "models" / "model.json"
    if not path.exists():
        return None
    model = json.loads(path.read_text())
    spec = ModelSpec(**model["model"])
    _, months, _, _ = load_all()
    proj = project(months, spec, n=3)
    proj["period"] = proj["period"].dt.strftime("%B %Y")
    proj["point"] = proj["point"].round(0)
    proj["rate"] = proj["rate"].round(0)
    return proj.rename(columns={"period": "month", "point": "projected_collections",
                                "rate": "revenue_per_trading_day",
                                "assumed_days": "assumed_trading_days"})


def excel_bytes() -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _monthly().to_excel(writer, sheet_name="Monthly cash", index=False)
        _categories().to_excel(writer, sheet_name="Categorized expenses", index=False)
        pd.read_csv(PROCESSED / "daily_collections.csv").to_excel(
            writer, sheet_name="Daily collections", index=False)
        fc = _forecast_frame()
        if fc is not None:
            fc.to_excel(writer, sheet_name="Forecast", index=False)
        bt = REPORTS / "backtest_detail.csv"
        if bt.exists():
            pd.read_csv(bt).to_excel(writer, sheet_name="Backtest", index=False)
        info = pd.DataFrame({
            "field": ["generated", "source", "note"],
            "value": [date.today().isoformat(),
                      "data/raw/Accounting.xlsx",
                      "Personal expenses (label 'D') are kept separate from operating costs"],
        })
        info.to_excel(writer, sheet_name="About", index=False)
    return buffer.getvalue()


class SummaryPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "Dental Clinic Cash and Cost Summary", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(110, 110, 110)
        self.cell(0, 5, f"Generated {date.today().isoformat()}", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)


def _jpg_png(path: Path) -> io.BytesIO:
    buf = io.BytesIO()
    buf.write(path.read_bytes())
    buf.seek(0)
    return buf


def pdf_bytes() -> bytes:
    analysis = json.loads((REPORTS / "analysis.json").read_text())
    kpis = analysis["kpis"]
    metrics = json.loads((REPORTS / "metrics.json").read_text())

    pdf = SummaryPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "1. Cash position", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    fixed = kpis["fixed"]
    rows = [
        ("Months on file", f'{kpis["months"]}'),
        ("Trading days recorded", f'{kpis["trading_days"]}'),
        ("Collections total", f'PHP {kpis["revenue_total"]:,.0f}'),
        ("Average per trading day", f'PHP {kpis["revenue_per_trading_day"]:,.0f}'),
        ("Operating expenses", f'PHP {kpis["operating_total"]:,.0f}'),
        ("Owner personal (label D)", f'PHP {kpis["personal_total"]:,.0f}'),
        ("Operating margin (upper bound)", f'{kpis["operating_margin"]:.1%}'),
        ("Average monthly surplus", f'PHP {kpis["surplus_avg_month"]:,.0f}'),
        ("Committed fixed cost / month", f'PHP {fixed["committed_fixed_month"]:,.0f}'),
        ("Break-even per trading day", f'PHP {fixed["fixed_per_trading_day"]:,.0f}'),
        ("Unclassified share of operating", f'{kpis["unclassified_share_of_operating"]:.1%}'),
    ]
    for label, value in rows:
        pdf.cell(95, 5.5, label)
        pdf.cell(0, 5.5, value, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "2. Forecast", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    headline = metrics["backtest"]
    pdf.multi_cell(0, 5,
                   f'Model: {metrics["model"]["name"]} (revenue per trading day x '
                   f'assumed trading days). Out-of-sample error on 4-week planning '
                   f'blocks: MAPE {headline["chosen_mape"]:.1f}%, against '
                   f'{headline["baseline_mape"]:.1f}% for {headline["baseline_model"]}. '
                   f'Improvement {headline["improvement_pct"]:.1f}%.')
    pdf.ln(1)
    fc = _forecast_frame()
    if fc is not None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(60, 5.5, "Month", border=0)
        pdf.cell(45, 5.5, "Trading days", border=0)
        pdf.cell(0, 5.5, "Projected collections", border=0, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for _, r in fc.iterrows():
            pdf.cell(60, 5.5, str(r["month"]))
            pdf.cell(45, 5.5, f'{r["assumed_trading_days"]:.0f}')
            pdf.cell(0, 5.5, f'PHP {r["projected_collections"]:,.0f}', new_x="LMARGIN", new_y="NEXT")

    for fig, caption in [("monthly_cash.png", "3. Monthly collections"),
                         ("cost_mix.png", "4. Cost mix")]:
        path = FIGURES / fig
        if path.exists():
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, caption, new_x="LMARGIN", new_y="NEXT")
            pdf.image(_jpg_png(path), w=185)
    return bytes(pdf.output())


if __name__ == "__main__":
    (REPORTS / "clinic_summary.xlsx").write_bytes(excel_bytes())
    (REPORTS / "clinic_summary.pdf").write_bytes(pdf_bytes())
    print("wrote reports/clinic_summary.xlsx and .pdf")
