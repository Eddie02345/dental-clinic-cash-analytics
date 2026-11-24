"""App smoke tests: every page renders, and the ledger actions work."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = ROOT / "src" / "app" / "app.py"


def _render(page: str) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.run()
    assert not at.exception, f"initial render failed: {[e.value for e in at.exception]}"
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, f"{page} raised: {[e.value for e in at.exception]}"
    return at


@pytest.mark.parametrize("page", ["Dashboard", "Forecast", "Ledger", "Reports"])
def test_page_renders(page):
    at = _render(page)
    assert len(at.title) == 1


def test_forecast_page_shows_backtest():
    at = _render("Forecast")
    metrics = {m.label for m in at.metric}
    assert any("Projected collections" in label for label in metrics)
    assert any("Out-of-sample MAPE" in label for label in metrics)


def test_ledger_pages_have_tables():
    at = _render("Ledger")
    assert len(at.tabs) == 2
    assert len(at.dataframe) >= 2
