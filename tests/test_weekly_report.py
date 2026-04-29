"""
Tests for WeeklyReport v1.
"""
import sqlite3
from datetime import datetime, timezone

import pytest

from trading_lab.reports.weekly_report import WeeklyReport, _week_bounds


def _journal_signals(db_path: str, created_ats: list[str],
                     strategy: str = "simple_momentum", ticker: str = "TEST",
                     action: str = "BUY", confidence: float = 0.8) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL, strategy TEXT, ticker TEXT,
                action TEXT, confidence REAL, reason TEXT,
                suggested_qty REAL, dry_run INTEGER, approved INTEGER,
                approval_reason TEXT
            )
        """)
        for ts in created_ats:
            conn.execute(
                """INSERT INTO signals
                   (created_at, strategy, ticker, action, confidence, reason,
                    suggested_qty, dry_run, approved, approval_reason)
                   VALUES (?, ?, ?, ?, ?, 'Test', 1.0, 1, 1, 'ok')""",
                (ts, strategy, ticker, action, confidence),
            )


def _journal_snapshots(db_path, created_ats, snapshot_type="account_summary"):
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL, snapshot_type TEXT, data_json TEXT
            )
        """)
        for ts in created_ats:
            conn.execute(
                "INSERT INTO snapshots (created_at, snapshot_type, data_json) VALUES (?, ?, '{}')",
                (ts, snapshot_type),
            )


class TestWeekBounds:
    def test_monday_returns_same_monday(self):
        m, f = _week_bounds("2026-04-27")  # Monday
        assert m.strftime("%Y-%m-%d") == "2026-04-27"
        assert f.strftime("%Y-%m-%d") == "2026-05-01"

    def test_wednesday_returns_preceding_monday(self):
        m, f = _week_bounds("2026-04-29")  # Wednesday
        assert m.strftime("%Y-%m-%d") == "2026-04-27"
        assert f.strftime("%Y-%m-%d") == "2026-05-01"

    def test_sunday_returns_preceding_monday(self):
        m, f = _week_bounds("2026-05-03")  # Sunday
        assert m.strftime("%Y-%m-%d") == "2026-04-27"
        assert f.strftime("%Y-%m-%d") == "2026-05-01"


class TestWeeklyReport:
    def test_empty_week_produces_report(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Weekly Report" in report
        assert "2026-04-27" in report
        assert "2026-05-01" in report
        assert "No signals recorded this week" in report

    def test_signals_in_week_are_counted(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        _journal_signals(db, [
            "2026-04-27T10:00:00Z",
            "2026-04-28T10:00:00Z",
            "2026-04-29T10:00:00Z",
        ])
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Total signals: 3" in report

    def test_signals_outside_week_are_excluded(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        _journal_signals(db, [
            "2026-04-27T10:00:00Z",  # Monday — in range
            "2026-04-26T10:00:00Z",  # Sunday — before
            "2026-05-02T10:00:00Z",  # Saturday — after
        ])
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Total signals: 1" in report

    def test_monday_and_friday_boundaries(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        _journal_signals(db, [
            "2026-04-27T10:00:00Z",  # Monday
            "2026-05-01T10:00:00Z",  # Friday
        ])
        report = WeeklyReport(db).generate("2026-04-29")
        assert "Total signals: 2" in report

    def test_daily_breakdown_shows_counts(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        _journal_signals(db, [
            "2026-04-27T10:00:00Z",
            "2026-04-28T10:00:00Z",
        ])
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Daily Breakdown" in report
        assert "simple_momentum" in report

    def test_multiple_strategies_in_daily_breakdown(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        _journal_signals(db, ["2026-04-27T10:00:00Z"], strategy="simple_momentum")
        _journal_signals(db, ["2026-04-28T10:00:00Z"], strategy="ma_crossover")
        report = WeeklyReport(db).generate("2026-04-27")
        assert "simple_momentum" in report
        assert "ma_crossover" in report

    def test_snapshots_counted(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        _journal_snapshots(db, ["2026-04-27T10:00:00Z", "2026-04-28T10:00:00Z"])
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Total snapshots: 2" in report

    def test_missing_db_does_not_crash(self, tmp_path):
        db = str(tmp_path / "does_not_exist" / "test.sqlite3")
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Weekly Report" in report
        assert "0" in report

    def test_review_questions_present(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        report = WeeklyReport(db).generate("2026-04-27")
        assert "Review Questions" in report

    def test_generate_defaults_to_today_when_no_date(self, tmp_path):
        db = str(tmp_path / "test.sqlite3")
        report = WeeklyReport(db).generate()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert "Weekly Report" in report
        # Should not crash
