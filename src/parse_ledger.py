"""Parse the clinic's monthly ledger workbook into tidy CSVs.

The workbook is not a table: each month is a block that contains daily cash
collections (columns A/B), a free-text expense log (columns F/G/H) and a small
summary (columns K/L).  This module splits those into separate, keyed tables.

Usage:
    python -m src.parse_ledger
    python -m src.parse_ledger --input data/raw/Accounting.xlsx --outdir data/processed
"""
from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import date
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "Accounting.xlsx"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"

MONTHS = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}


def _is_month_header(value) -> bool:
    return isinstance(value, str) and value.strip().upper() in MONTH_NUM


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def load_rows(path: Path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    return ws, [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
                for r in range(1, ws.max_row + 1)]


def find_blocks(rows):
    """Return [(row_index, MONTH_NAME)] for each monthly section header.

    Keyed on a month word in column A with column B empty.  Never keyed on the
    month name alone: MARCH appears twice (2025 and 2026).
    """
    blocks = []
    for i, row in enumerate(rows, start=1):
        if _is_month_header(row[0]) and row[1] in (None, ""):
            blocks.append((i, row[0].strip().upper()))
    if not blocks:
        raise SystemExit("No monthly blocks found; check the input workbook.")
    blocks.append((len(rows) + 1, "END"))
    return blocks


def assign_years(blocks) -> list[int]:
    """Walk blocks in order, bumping the year when the month wraps backwards."""
    years, year, prev = [], 2025, None
    for _, name in blocks[:-1]:
        num = MONTH_NUM[name]
        if prev is not None and num < prev:
            year += 1
        years.append(year)
        prev = num
    return years


def _parse_date(value, month: int, year: int):
    """Best-effort date for an expense row.  Returns (date or None, quality)."""
    if isinstance(value, date):
        d = value
        # Excel serial mistakes show up as wildly out-of-range years.
        if 2000 <= d.year <= 2100:
            return d, "ok"
        return None, "bad_year"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, "empty"
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%B %d,%Y", "%m/%d/%y"):
            try:
                from datetime import datetime
                d = datetime.strptime(text, fmt).date()
                if 2000 <= d.year <= 2100:
                    return d, "ok"
                return None, "bad_year"
            except ValueError:
                continue
        return None, "unparsed"
    return None, "empty"


def parse(path: Path = RAW):
    _, rows = load_rows(path)
    blocks = find_blocks(rows)
    years = assign_years(blocks)

    daily, expenses, summary, issues = [], [], [], []

    for idx, ((start, month_name), (end, _)) in enumerate(zip(blocks, blocks[1:])):
        month, year = MONTH_NUM[month_name], years[idx]
        block_collected = 0.0
        for r in range(start + 1, end):
            row = rows[r - 1]
            a, b = row[0], row[1]
            g, h = row[6], row[7]
            f = row[5]

            # --- daily cash collection: day number + amount
            if _num(a) and 1 <= int(a) <= 31 and _num(b) is not None:
                day = int(a)
                amount = float(b)
                try:
                    d = date(year, month, day)
                except ValueError:
                    last_day = calendar.monthrange(year, month)[1]
                    issues.append({
                        "block_id": idx, "row": r, "kind": "invalid_date",
                        "detail": f"{year}-{month:02d}-{day:02d} does not exist",
                        "value": amount,
                        "action": f"kept, dated {year}-{month:02d}-{last_day:02d}",
                    })
                    d = date(year, month, last_day)
                daily.append({
                    "block_id": idx, "month": month, "year": year, "date": d,
                    "dow": d.weekday(), "amount": amount,
                })
                block_collected += amount

            # --- expense log: label text + amount
            if isinstance(g, str) and g.strip() and _num(h) is not None:
                d, quality = _parse_date(f, month, year)
                if d is None and quality == "bad_year":
                    issues.append({
                        "block_id": idx, "row": r, "kind": "bad_expense_date",
                        "detail": str(f), "value": float(h),
                        "action": "date dropped, month kept",
                    })
                expenses.append({
                    "block_id": idx, "row": r, "month": month, "year": year,
                    "date": d.isoformat() if d else None,
                    "date_quality": quality,
                    "label_raw": g.strip(), "amount": float(h),
                })

            # --- summary block: General Income / Total Expenses
            if row[10] in ("General Income", "Total Expenses") and _num(row[11]) is not None:
                summary.append({
                    "block_id": idx, "month": month, "year": year,
                    "field": row[10].strip(), "value": float(row[11]),
                })

    daily_df = pd.DataFrame(daily).sort_values("date").reset_index(drop=True)
    exp_df = pd.DataFrame(expenses)
    sum_df = pd.DataFrame(summary).pivot_table(
        index=["block_id", "month", "year"], columns="field",
        values="value", aggfunc="first").reset_index()
    sum_df = sum_df.rename(columns={
        "General Income": "general_income",
        "Total Expenses": "total_expenses_reported",
    })
    if "general_income" not in sum_df:
        sum_df["general_income"] = float("nan")
    if "total_expenses_reported" not in sum_df:
        sum_df["total_expenses_reported"] = float("nan")

    per_block = daily_df.groupby("block_id")["amount"].sum().rename("collected")
    logged = exp_df.groupby("block_id")["amount"].sum().rename("logged_expenses")
    sum_df = sum_df.merge(per_block, on="block_id", how="left")
    sum_df = sum_df.merge(logged, on="block_id", how="left")
    sum_df["collected"] = sum_df["collected"].fillna(0.0)
    sum_df["logged_expenses"] = sum_df["logged_expenses"].fillna(0.0)

    # --- validation: daily totals must equal the workbook's own General Income
    ties = []
    for _, row in sum_df.iterrows():
        gi = row["general_income"]
        diff = None if pd.isna(gi) else round(float(row["collected"]) - float(gi), 2)
        ties.append(diff)
        if pd.isna(gi):
            issues.append({
                "block_id": int(row["block_id"]), "row": None, "kind": "missing_total",
                "detail": "General Income not reported for this month",
                "value": float(row["collected"]), "action": "daily total used",
            })
        elif abs(diff) > 0.005:
            issues.append({
                "block_id": int(row["block_id"]), "row": None, "kind": "tie_out_mismatch",
                "detail": "daily sum != General Income", "value": diff,
                "action": "investigate parser",
            })
    sum_df["tie_out_diff"] = ties

    # --- second validation: the workbook's own expense total vs the logged rows
    diffs = []
    for _, row in sum_df.iterrows():
        rep, logged_amt = row["total_expenses_reported"], row["logged_expenses"]
        if pd.isna(rep):
            diffs.append(None)
            issues.append({
                "block_id": int(row["block_id"]), "row": None, "kind": "missing_expense_total",
                "detail": "Total Expenses not reported for this month",
                "value": float(logged_amt), "action": "logged rows used",
            })
            continue
        diff = round(float(logged_amt) - float(rep), 2)
        diffs.append(diff)
        if abs(diff) > 1.0:
            issues.append({
                "block_id": int(row["block_id"]), "row": None, "kind": "expense_total_mismatch",
                "detail": f"logged rows {logged_amt:,.0f} vs reported {rep:,.0f}",
                "value": diff, "action": "logged rows used, flagged in docs",
            })
    sum_df["reported_vs_logged_diff"] = diffs

    # --- month-level coverage facts used by the report
    for _, row in sum_df.iterrows():
        n_days = int((daily_df["block_id"] == row["block_id"]).sum())
        if n_days < 20:
            issues.append({
                "block_id": int(row["block_id"]), "row": None, "kind": "low_coverage",
                "detail": f"{n_days} trading days recorded", "value": float(row["collected"]),
                "action": "treat month as partial",
            })

    return daily_df, exp_df, sum_df, pd.DataFrame(issues)


def write_outputs(daily_df, exp_df, sum_df, issues_df, outdir: Path = PROCESSED):
    outdir.mkdir(parents=True, exist_ok=True)
    daily_df.to_csv(outdir / "daily_collections.csv", index=False)
    exp_df.to_csv(outdir / "expenses.csv", index=False)
    sum_df.to_csv(outdir / "month_summary.csv", index=False)
    (REPORTS).mkdir(parents=True, exist_ok=True)
    issues_df.to_csv(REPORTS / "parse_issues.csv", index=False)

    stats = {
        "blocks": int(sum_df["block_id"].nunique()),
        "daily_rows": int(len(daily_df)),
        "positive_days": int((daily_df["amount"] > 0).sum()),
        "expense_rows": int(len(exp_df)),
        "collected_total": float(daily_df["amount"].sum()),
        "logged_expenses_total": float(exp_df["amount"].sum()),
        "tie_out_failures": int(sum(1 for v in sum_df["tie_out_diff"]
                                    if pd.notna(v) and abs(v) > 0.005)),
        "issues": int(len(issues_df)),
    }
    (REPORTS / "parse_stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(RAW))
    ap.add_argument("--outdir", default=str(PROCESSED))
    args = ap.parse_args()

    daily_df, exp_df, sum_df, issues_df = parse(Path(args.input))
    stats = write_outputs(daily_df, exp_df, sum_df, issues_df, Path(args.outdir))

    print(f"{'blk':>3} {'month':<9} {'collected':>10} {'days':>5} "
          f"{'logged':>11} {'GI':>10} {'tie':>8}")
    for _, row in sum_df.iterrows():
        gi = row["general_income"]
        gi_txt = "n/a" if pd.isna(gi) else format(gi, "10,.0f")
        tie = row["tie_out_diff"]
        tie_txt = "n/a" if pd.isna(tie) else format(tie, "8,.2f")
        days = int((daily_df["block_id"] == row["block_id"]).sum())
        print(f"{int(row['block_id']):3d} {int(row['month']):02d}/{int(row['year'])}   "
              f"{row['collected']:10,.0f} {days:5d} {row['logged_expenses']:11,.0f} "
              f"{gi_txt} {tie_txt}")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
