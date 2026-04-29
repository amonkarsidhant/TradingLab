"""
Tests for SnapshotLogger — SQLite persistence for API snapshots and signals.

All tests use pytest's tmp_path fixture so they write to a throwaway
SQLite file and never touch the real trading_lab.sqlite3 on disk.
"""
import json
import sqlite3

import pytest

from trading_lab.logger import SnapshotLogger
from trading_lab.models import Signal, SignalAction


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_logger(tmp_path) -> SnapshotLogger:
    return SnapshotLogger(str(tmp_path / "test.sqlite3"))


def make_signal(**overrides) -> Signal:
    defaults = dict(
        strategy="simple_momentum",
        ticker="AAPL_US_EQ",
        action=SignalAction.BUY,
        confidence=0.85,
        reason="Price moved up 5.00%",
        suggested_quantity=1.0,
    )
    defaults.update(overrides)
    return Signal(**defaults)


# ── Table creation ────────────────────────────────────────────────────────────

def test_init_creates_snapshots_and_signals_tables(tmp_path):
    """Both tables must exist after constructing a SnapshotLogger."""
    make_logger(tmp_path)

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert "snapshots" in tables
    assert "signals" in tables


def test_init_is_idempotent(tmp_path):
    """Constructing SnapshotLogger twice on the same DB must not raise."""
    db_path = str(tmp_path / "test.sqlite3")
    SnapshotLogger(db_path)
    SnapshotLogger(db_path)  # second init — CREATE TABLE IF NOT EXISTS should be safe


# ── save_snapshot ─────────────────────────────────────────────────────────────

def test_save_snapshot_writes_type_and_data(tmp_path):
    logger = make_logger(tmp_path)
    data = {"totalValue": 5000.0, "currency": "EUR"}

    logger.save_snapshot("account_summary", data)

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT snapshot_type, data_json FROM snapshots"
        ).fetchone()

    assert row[0] == "account_summary"
    assert json.loads(row[1]) == data


def test_save_snapshot_records_iso_timestamp(tmp_path):
    logger = make_logger(tmp_path)

    logger.save_snapshot("positions", [])

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        created_at = conn.execute("SELECT created_at FROM snapshots").fetchone()[0]

    assert created_at is not None
    assert "T" in created_at  # ISO 8601 format contains a 'T' separator


def test_save_snapshot_accumulates_multiple_rows(tmp_path):
    logger = make_logger(tmp_path)

    logger.save_snapshot("account_summary", {"a": 1})
    logger.save_snapshot("positions", [])
    logger.save_snapshot("instruments", [{"ticker": "AAPL_US_EQ"}])

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    assert count == 3


def test_save_snapshot_handles_list_data(tmp_path):
    """API endpoints like positions return lists, not dicts."""
    logger = make_logger(tmp_path)

    logger.save_snapshot("positions", [{"ticker": "TSLA_US_EQ", "quantity": 2.0}])

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT data_json FROM snapshots").fetchone()

    result = json.loads(row[0])
    assert isinstance(result, list)
    assert result[0]["ticker"] == "TSLA_US_EQ"


# ── save_signal ───────────────────────────────────────────────────────────────

def test_save_signal_writes_all_fields(tmp_path):
    logger = make_logger(tmp_path)
    signal = make_signal()

    logger.save_signal(signal, dry_run=True, approved=True, approval_reason="Approved by policy")

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """SELECT strategy, ticker, action, confidence, reason,
                      suggested_qty, dry_run, approved, approval_reason
               FROM signals"""
        ).fetchone()

    assert row[0] == "simple_momentum"
    assert row[1] == "AAPL_US_EQ"
    assert row[2] == "BUY"
    assert row[3] == pytest.approx(0.85)
    assert row[4] == "Price moved up 5.00%"
    assert row[5] == pytest.approx(1.0)
    assert row[6] == 1   # dry_run=True stored as INTEGER 1
    assert row[7] == 1   # approved=True stored as INTEGER 1
    assert row[8] == "Approved by policy"


def test_save_signal_stores_action_as_string(tmp_path):
    """SignalAction enum must be stored as its string value, not repr."""
    logger = make_logger(tmp_path)

    logger.save_signal(
        make_signal(action=SignalAction.SELL, suggested_quantity=-1.0),
        dry_run=True,
        approved=False,
        approval_reason="HOLD signal; no trade needed.",
    )

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        action = conn.execute("SELECT action FROM signals").fetchone()[0]

    assert action == "SELL"


def test_save_signal_stores_rejected_signal_correctly(tmp_path):
    """Rejected (approved=False) signals must still be written to the journal."""
    logger = make_logger(tmp_path)

    logger.save_signal(
        make_signal(action=SignalAction.HOLD, confidence=0.5, suggested_quantity=0.0),
        dry_run=True,
        approved=False,
        approval_reason="HOLD signal; no trade needed.",
    )

    db_path = str(tmp_path / "test.sqlite3")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT approved, approval_reason FROM signals").fetchone()

    assert row[0] == 0   # approved=False stored as INTEGER 0
    assert "HOLD" in row[1]
