"""SQLite store for the app: seeded from the parsed CSVs, then editable.

The CSVs remain the reproducible artifact; the database is the working copy the
clinic edits.  `rebuild()` throws the working copy away and reseeds from CSVs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "clinic.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'ledger'
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id INTEGER NOT NULL,
    date TEXT,
    label_raw TEXT NOT NULL,
    label_norm TEXT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    expense_type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'ledger'
);
CREATE TABLE IF NOT EXISTS forecast_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    assumed_days REAL NOT NULL,
    months_ahead INTEGER NOT NULL,
    total_projected REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_collections(date);
CREATE INDEX IF NOT EXISTS idx_exp_block ON expenses(block_id);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init(rebuild: bool = False, path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) AS n FROM daily_collections").fetchone()["n"]
    if rebuild or n == 0:
        seed(conn)
    return conn


def seed(conn: sqlite3.Connection) -> None:
    conn.executescript("DELETE FROM daily_collections; DELETE FROM expenses;"
                       "DELETE FROM sqlite_sequence WHERE name IN "
                       "('daily_collections', 'expenses');")
    daily = pd.read_csv(PROCESSED / "daily_collections.csv",
                        parse_dates=["date"])
    daily["date"] = daily["date"].dt.date.astype(str)
    daily[["block_id", "date", "amount"]].to_sql(
        "daily_collections", conn, if_exists="append", index=False)

    exp = pd.read_csv(PROCESSED / "expenses_categorized.csv")
    dates = pd.to_datetime(exp["date"], errors="coerce")
    exp["date"] = dates.dt.strftime("%Y-%m-%d").where(dates.notna(), None)
    exp[["block_id", "date", "label_raw", "label_norm", "amount",
         "category", "expense_type"]].to_sql(
        "expenses", conn, if_exists="append", index=False)
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                 ("assumed_days", "23"))
    conn.commit()


def frame(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def add_collection(conn, date: str, amount: float, block_id: int = 99) -> None:
    conn.execute(
        "INSERT INTO daily_collections(block_id, date, amount, source) "
        "VALUES (?, ?, ?, 'manual')", (block_id, date, float(amount)))
    conn.commit()


def add_expense(conn, date: str | None, label: str, amount: float,
                category: str, block_id: int = 99) -> None:
    from src.taxonomy import normalize

    expense_type = "Personal" if category == "Personal" else "Operating"
    conn.execute(
        "INSERT INTO expenses(block_id, date, label_raw, label_norm, amount, "
        "category, expense_type, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'manual')",
        (block_id, date, label, normalize(label), float(amount), category,
         expense_type))
    conn.commit()


def update_category(conn, expense_id: int, category: str) -> None:
    expense_type = "Personal" if category == "Personal" else "Operating"
    conn.execute("UPDATE expenses SET category = ?, expense_type = ? WHERE id = ?",
                 (category, expense_type, int(expense_id)))
    conn.commit()


def delete_row(conn, table: str, row_id: int) -> None:
    if table not in ("daily_collections", "expenses"):
        raise ValueError("unknown table")
    conn.execute(f"DELETE FROM {table} WHERE id = ?", (int(row_id),))
    conn.commit()


def get_setting(conn, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                 (key, str(value)))
    conn.commit()


if __name__ == "__main__":
    c = init(rebuild=True)
    print("collections:", c.execute(
        "SELECT COUNT(*) n FROM daily_collections").fetchone()["n"])
    print("expenses:", c.execute("SELECT COUNT(*) n FROM expenses").fetchone()["n"])
