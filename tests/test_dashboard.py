"""
Tests for DashboardGenerator v1.
"""
import json
import re

import pytest

from trading_lab.reports.dashboard import DashboardGenerator


def _extract_json_from_html(html: str) -> dict:
    match = re.search(r"const DATA = ({.*?});", html, re.DOTALL)
    assert match is not None, "DATA payload not found in HTML"
    return json.loads(match.group(1))


class TestDashboardGenerator:
    def test_produces_valid_html(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_embedded_json(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert "const DATA =" in html
        data = _extract_json_from_html(html)
        assert isinstance(data, dict)

    def test_json_has_expected_top_level_keys(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        data = _extract_json_from_html(html)
        for key in ["strategies", "calendar", "recent_signals", "account_snapshot", "generated_at"]:
            assert key in data

    def test_strategies_in_json(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        data = _extract_json_from_html(html)
        names = [s["name"] for s in data["strategies"]]
        assert "simple_momentum" in names
        assert "ma_crossover" in names
        assert "mean_reversion" in names

    def test_equity_curves_in_json(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        data = _extract_json_from_html(html)
        for s in data["strategies"]:
            if not s.get("error"):
                assert "equity_curve" in s
                assert isinstance(s["equity_curve"], list)

    def test_has_all_html_sections(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert "Strategy Performance" in html
        assert "Equity Curves" in html
        assert "Signal Heatmap" in html
        assert "Recent Signals" in html
        assert "Account Snapshot" in html

    def test_canvas_element_present(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert "equity-canvas" in html
        assert "<canvas" in html

    def test_missing_db_does_not_crash(self, tmp_path):
        db = str(tmp_path / "does_not_exist" / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert "<!DOCTYPE html>" in html

    def test_dark_theme_styles_present(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert "#0d1117" in html
        assert "system-ui" in html

    def test_safety_footer(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="TEST", data_source="static")
        assert "no live trades" in html.lower()

    def test_custom_ticker_reflected_in_json(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        gen = DashboardGenerator(db)
        html = gen.generate(ticker="CUSTOM", data_source="static")
        data = _extract_json_from_html(html)
        assert data["ticker"] == "CUSTOM"
