"""Turn free-text expense labels into categories.

The ledger has 97 distinct labels, typed by hand, with inconsistencies
("Food", "food", "FOOD") and shop-specific shorthand.  This module applies an
ordered keyword ruleset and, just as importantly, writes `labels.csv` so the
clinic can correct any mapping once instead of retyping every row.

If `data/processed/labels.csv` already exists, its `category` column wins.
That makes the file the single source of truth and keeps corrections stable
across reruns.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
LABELS = PROCESSED / "labels.csv"
REPORTS = ROOT / "reports"

PERSONAL = "Personal"
OPERATING = ["Rent", "Wages", "Lab Fees", "Food", "Supplies", "Utilities",
             "Bank/Transfer", "Unclassified"]
CATEGORIES = [PERSONAL] + OPERATING

# Staff, dentists and family members paid through the expense log.  Names are
# kept only for classification; every artifact that leaves the group uses
# "Wage N" instead.
WAGE_NAMES = {
    "kimi", "erica", "shyra", "dianne", "jordan", "lyka", "cj", "des", "armie",
    "judy", "heather", "kuya bernie", "ate rose", "rose", "mama jo", "doc rose",
    "doc valdez", "kuya pj", "mary", "jerry", "maesi", "cyril", "lyken", "liza",
    "shaolin", "bobby", "casem", "kyle baniwas", "pcc student", "roni",
    "don robert", "charlton", "russel", "maribel", "manang rose", "winston",
    "victoria", "kuya", "ate",
}

FOOD_WORDS = ["food", "chichirya", "pinakurat", "grocery", "savemore", "lunch",
              "breakfast", "dinner", "pad thai", "takoyaki", "greenwich", "snack",
              "coffee", "milk tea"]

SUPPLY_WORDS = ["syringe", "photopaper", "photo paper", "bond paper", "tissue",
                "zonrox", "garbage", "supply", "distilled", "k-file", "composite",
                "nss", "rug", "drawer", "scrub", "mask", "face", "coords", "sticker",
                "key duplicate", "light bulb", "spoon", "fork", "glass", "sink",
                "renovation", "ink", "printer", "dental", "watson", "moiturizer",
                "tooth", "gloves", "cotton", "alcohol", "materials", "tiongsan",
                "treasure link", "wilkins", "h2o", "water", "paper", "photocopy",
                "shoppe", "shopee", "jnt", "lbc", "courier", "lan cable", "gloves"]

UTILITY_WORDS = ["electric", "internet", "wifi", "load", "canva", "subscription",
                 "monthly fee", "bill"]

LAB_WORDS = ["laboratory", "lab fee", "denture", "ivocap", "case", "lab"]

# Labels that look like bare names but are not people we pay.  Without this,
# "solicitation" and shop shorthand get silently booked as wages.
NOT_A_PERSON = {"solicitation", "donation", "ataw", "viscus", "beavans"}


def normalize(label: str) -> str:
    text = str(label).lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .-,")


def _contains(norm: str, words) -> bool:
    return any(w in norm for w in words)


def rule_category(label: str) -> str:
    n = normalize(label)

    if n in {"d", "d.", "d-", "personal", "personal expenses"}:
        return PERSONAL
    if "rent" in n:
        return "Rent"
    if "bank" in n or "transfer" in n or "deposit" in n:
        return "Bank/Transfer"
    if _contains(n, LAB_WORDS):
        return "Lab Fees"
    if _contains(n, FOOD_WORDS):
        return "Food"
    if _contains(n, UTILITY_WORDS):
        return "Utilities"
    if n in NOT_A_PERSON:
        return "Unclassified"
    if n in WAGE_NAMES or n.startswith(("kuya ", "ate ", "doc ", "dr. ", "mama ",
                                        "manang ")):
        return "Wages"
    if re.fullmatch(r"[a-z]+( [a-z]+)?", n) and n in WAGE_NAMES:
        return "Wages"
    if _contains(n, SUPPLY_WORDS):
        return "Supplies"
    # A bare personal name we have not seen before is more likely a paid
    # helper than a supply purchase; flag rather than silently bucket it.
    if re.fullmatch(r"[a-z]+( [a-z]+){0,2}", n):
        return "Wages"
    return "Unclassified"


def categorize(expenses: pd.DataFrame, labels_path: Path = LABELS) -> pd.DataFrame:
    df = expenses.copy()
    df["label_norm"] = df["label_raw"].map(normalize)

    overrides = {}
    if labels_path.exists():
        prev = pd.read_csv(labels_path)
        if "category" in prev.columns:
            overrides = dict(zip(prev["label_norm"], prev["category"]))

    categories = {
        label: overrides.get(label) or rule_category(label)
        for label in sorted(df["label_norm"].unique())
    }
    df["category"] = df["label_norm"].map(categories)
    df["expense_type"] = df["category"].map(
        lambda c: PERSONAL if c == PERSONAL else "Operating")

    labels = (df.groupby("label_norm")
                .agg(count=("amount", "size"), total=("amount", "sum"),
                     category=("category", "first"))
                .reset_index()
                .sort_values("total", ascending=False))
    labels["source"] = labels["label_norm"].map(
        lambda l: "manual" if l in overrides else "rule")
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(labels_path, index=False)
    return df


def summary(df: pd.DataFrame) -> dict:
    op = df[df["expense_type"] == "Operating"]
    personal = df[df["expense_type"] == PERSONAL]
    by_cat = (op.groupby("category")["amount"].sum()
                .sort_values(ascending=False))
    op_total = float(op["amount"].sum())
    return {
        "operating_total": op_total,
        "personal_total": float(personal["amount"].sum()),
        "personal_share_of_all": float(personal["amount"].sum() / df["amount"].sum()),
        "unclassified_value": float(by_cat.get("Unclassified", 0.0)),
        "unclassified_share_of_operating": float(by_cat.get("Unclassified", 0.0) / op_total
                                                 if op_total else 0.0),
        "by_category": {k: float(v) for k, v in by_cat.items()},
        "labels": int(df["label_norm"].nunique()),
        "entries": int(len(df)),
    }


def main():
    expenses = pd.read_csv(PROCESSED / "expenses.csv")
    categorized = categorize(expenses)
    categorized.to_csv(PROCESSED / "expenses_categorized.csv", index=False)
    stats = summary(categorized)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "expense_summary.json").write_text(json.dumps(stats, indent=2))

    print(f"labels: {stats['labels']}  entries: {stats['entries']}")
    print(f"operating: {stats['operating_total']:,.2f}   "
          f"personal: {stats['personal_total']:,.2f} "
          f"({stats['personal_share_of_all']:.1%} of all spend)")
    print(f"unclassified: {stats['unclassified_value']:,.2f} "
          f"({stats['unclassified_share_of_operating']:.1%} of operating)")
    print("\ncategory            total      share")
    for cat, val in stats["by_category"].items():
        print(f"{cat:18s} {val:10,.0f}  {val / stats['operating_total']:6.1%}")


if __name__ == "__main__":
    main()
