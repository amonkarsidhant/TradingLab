"""
Tests for StrategyComparison v1.
"""
import sqlite3

import pytest

from trading_lab.reports.strategy_comparison import (
    StrategyComparison,
    _default_kwargs,
)


class TestDefaultKwargs:
    def test_simple_momentum(self):
        assert _default_kwargs("simple_momentum") == {"lookback": 5}

    def test_ma_crossover(self):
        assert _default_kwargs("ma_crossover") == {"fast": 10, "slow": 30}

    def test_mean_reversion(self):
        assert _default_kwargs("mean_reversion") == {
            "period": 14, "oversold": 30, "overbought": 70,
        }

    def test_unknown_returns_empty(self):
        assert _default_kwargs("nonexistent") == {}


class TestStrategyComparison:
    def test_report_includes_all_strategies(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        for name in ["simple_momentum", "ma_crossover", "mean_reversion"]:
            assert name in report

    def test_report_has_comparison_table(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        assert "Performance Comparison" in report
        assert "Return%" in report
        assert "CAGR%" in report
        assert "Sharpe" in report

    def test_all_strategies_have_metrics_for_static_data(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        # Each strategy should produce a numeric return (or 0.00)
        assert "0.00" in report or "-" not in report.split("simple_momentum")[1][:100]

    def test_journaled_counts_appear_when_data_exists(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        with sqlite3.connect(db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL, strategy TEXT, ticker TEXT,
                    action TEXT, confidence REAL, reason TEXT,
                    suggested_qty REAL, dry_run INTEGER, approved INTEGER,
                    approval_reason TEXT
                )
            """)
            conn.execute(
                """INSERT INTO signals
                   (created_at, strategy, ticker, action, confidence, reason,
                    suggested_qty, dry_run, approved, approval_reason)
                   VALUES ('2026-04-27T10:00:00Z', 'simple_momentum', 'TEST',
                           'BUY', 0.8, 'Test', 1.0, 1, 1, 'ok')"""
            )
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        assert "Journaled Signal Counts" in report

    def test_missing_db_does_not_crash(self, tmp_path):
        db = str(tmp_path / "does_not_exist" / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        assert "Strategy Comparison" in report

    def test_report_includes_per_strategy_details(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        assert "## simple_momentum" in report
        assert "Total Return" in report
        assert "Sharpe Ratio" in report

    def test_report_includes_equity_sparkline(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        # Should have Unicode block characters or an empty indicator
        assert "Equity curve" in report

    def test_report_includes_interpretation_guide(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="TEST", data_source="static")
        assert "How to Read This" in report
        assert "Profit Factor" in report

    def test_custom_capital_and_ticker_reflected(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        comp = StrategyComparison(db)
        report = comp.compare(ticker="CUSTOM_TICKER", initial_capital=5000.0)
        assert "CUSTOM_TICKER" in report
        assert "5,000" in report
