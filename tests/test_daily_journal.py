"""
Tests for DailyJournal report generator.

All tests use tmp_path SQLite databases.
No network calls. No API credentials. No Trading 212 API usage.
Data is inserted directly with controlled UTC timestamps.
"""
import sqlite3

import pytest

from trading_lab.logger import SnapshotLogger
from trading_lab.reports.daily_journal import DailyJournal

TARGET_DATE = "2026-04-29"
OTHER_DATE = "2026-04-28"


# ── Test database helpers ─────────────────────────────────────────────────────

def make_db(tmp_path) -> str:
    """Initialise tables via SnapshotLogger and return the db_path."""
    db_path = str(tmp_path / "test.sqlite3")
    SnapshotLogger(db_path)  # creates both tables
    return db_path


def insert_snapshot(db_path: str, date: str, snapshot_type: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO snapshots (created_at, snapshot_type, data_json) VALUES (?, ?, ?)",
            (f"{date}T10:00:00+00:00", snapshot_type, '{"test": true}'),
        )


def insert_signal(
    db_path: str,
    date: str,
    action: str = "BUY",
    approved: bool = True,
    dry_run: bool = True,
    reason: str = "Price moved up 5.66%.",
    ticker: str = "AAPL_US_EQ",
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO signals
               (created_at, strategy, ticker, action, confidence, reason,
                suggested_qty, dry_run, approved, approval_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"{date}T10:00:00+00:00",
                "simple_momentum",
                ticker,
                action,
                0.95,
                reason,
                1.0,
                int(dry_run),
                int(approved),
                "Approved by basic demo risk policy.",
            ),
        )


# ── Empty / missing data ──────────────────────────────────────────────────────

def test_empty_report_when_no_snapshots_or_signals(tmp_path):
    """Empty DB must produce a report with helpful placeholder messages."""
    db_path = make_db(tmp_path)
    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert TARGET_DATE in report
    assert "No snapshots recorded" in report
    assert "No signals recorded" in report


def test_empty_report_includes_review_questions(tmp_path):
    """Review questions must always appear, even with no data."""
    db_path = make_db(tmp_path)
    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Review questions" in report


def test_empty_report_includes_safety_disclaimer(tmp_path):
    """The demo-only disclaimer must always be present."""
    db_path = make_db(tmp_path)
    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "demo environment" in report


def test_report_does_not_crash_when_db_file_missing(tmp_path):
    """DailyJournal must handle a non-existent DB gracefully."""
    db_path = str(tmp_path / "does_not_exist.sqlite3")
    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert TARGET_DATE in report
    assert "No snapshots recorded" in report
    assert "No signals recorded" in report


# ── Snapshot section ──────────────────────────────────────────────────────────

def test_report_counts_snapshots(tmp_path):
    db_path = make_db(tmp_path)
    insert_snapshot(db_path, TARGET_DATE, "account_summary")
    insert_snapshot(db_path, TARGET_DATE, "positions")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Total: 2" in report


def test_report_lists_snapshot_types(tmp_path):
    db_path = make_db(tmp_path)
    insert_snapshot(db_path, TARGET_DATE, "account_summary")
    insert_snapshot(db_path, TARGET_DATE, "positions")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "account_summary" in report
    assert "positions" in report


def test_report_excludes_snapshots_from_other_dates(tmp_path):
    db_path = make_db(tmp_path)
    insert_snapshot(db_path, TARGET_DATE, "account_summary")
    insert_snapshot(db_path, OTHER_DATE, "positions")  # different date — must be excluded

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Total: 1" in report
    assert "positions" not in report  # from other date


# ── Signal counts and breakdown ───────────────────────────────────────────────

def test_report_counts_total_signals(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY")
    insert_signal(db_path, TARGET_DATE, action="BUY")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Total signals: 2" in report


def test_report_breaks_down_signals_by_action(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY")
    insert_signal(db_path, TARGET_DATE, action="BUY")
    insert_signal(db_path, TARGET_DATE, action="SELL")
    insert_signal(db_path, TARGET_DATE, action="HOLD")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "BUY: 2" in report
    assert "SELL: 1" in report
    assert "HOLD: 1" in report


def test_report_shows_approved_vs_rejected_counts(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY", approved=True)
    insert_signal(db_path, TARGET_DATE, action="HOLD", approved=False)

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Approved: 1" in report
    assert "Rejected: 1" in report


def test_report_shows_dry_run_vs_live_counts(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY", dry_run=True)
    insert_signal(db_path, TARGET_DATE, action="BUY", dry_run=True)

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Dry-run: 2" in report
    assert "Live: 0" in report


def test_report_filters_signals_by_date(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY")
    insert_signal(db_path, OTHER_DATE, action="SELL")  # different date — excluded

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Total signals: 1" in report


# ── Signal detail table ───────────────────────────────────────────────────────

def test_report_signal_table_contains_ticker_and_action(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY", ticker="TSLA_US_EQ")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "TSLA_US_EQ" in report
    assert "BUY" in report


# ── Top signal reasons ────────────────────────────────────────────────────────

def test_report_shows_top_signal_reasons_with_count(tmp_path):
    db_path = make_db(tmp_path)
    insert_signal(db_path, TARGET_DATE, action="BUY", reason="Price moved up 5.66%.")
    insert_signal(db_path, TARGET_DATE, action="BUY", reason="Price moved up 5.66%.")
    insert_signal(db_path, TARGET_DATE, action="BUY", reason="Different reason.")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    assert "Price moved up 5.66%." in report
    assert "2x" in report


def test_report_top_reasons_limited_to_three(tmp_path):
    db_path = make_db(tmp_path)
    for i in range(5):
        insert_signal(db_path, TARGET_DATE, action="BUY", reason=f"Reason {i}.")

    report = DailyJournal(db_path).generate(TARGET_DATE)

    # At most 3 numbered entries in the reasons section
    reason_lines = [ln for ln in report.splitlines() if ln.startswith(("1.", "2.", "3.", "4.", "5."))]
    assert len(reason_lines) <= 3
