"""
Tests for Shadow Account v1.

No network. No broker. No order placement.
All tests use tmp_path SQLite databases for signal journaling.
"""
import sqlite3
from datetime import datetime, timezone

import pytest

from trading_lab.models import Signal, SignalAction
from trading_lab.shadow.account import ShadowAccount, ShadowResult, _overtrading_score
from trading_lab.shadow.report import render_shadow_report
from trading_lab.strategies.simple_momentum import SimpleMomentumStrategy


def _make_signal(action=SignalAction.BUY, strategy="simple_momentum", ticker="TEST",
                 confidence=0.8, reason="Upward momentum.", quantity=1.0):
    return Signal(
        strategy=strategy, ticker=ticker, action=action,
        confidence=confidence, reason=reason, suggested_quantity=quantity,
    )


def _journal_signals(db_path: str, signals: list[Signal]) -> None:
    """Write signals into the SQLite signals table (mimics SnapshotLogger)."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                strategy TEXT,
                ticker TEXT,
                action TEXT,
                confidence REAL,
                reason TEXT,
                suggested_qty REAL,
                dry_run INTEGER,
                approved INTEGER,
                approval_reason TEXT
            )
        """)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for s in signals:
            conn.execute(
                """INSERT INTO signals
                   (created_at, strategy, ticker, action, confidence, reason,
                    suggested_qty, dry_run, approved, approval_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, '')""",
                (now, s.strategy, s.ticker, s.action.value, s.confidence,
                 s.reason, s.suggested_quantity),
            )


# ── ShadowAccount ──────────────────────────────────────────────────────────────

def test_shadow_result_structure(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    result = shadow.compare(prices=prices, ticker="TEST")

    assert isinstance(result, ShadowResult)
    assert result.strategy_name == "simple_momentum"
    assert result.ticker == "TEST"
    assert result.shadow_trades >= 0
    assert result.shadow_return_pct is not None
    assert result.total_signals_journaled == 0  # empty DB
    assert isinstance(result.gap_notes, list)
    assert len(result.gap_notes) >= 1


def test_shadow_detects_missed_entries(tmp_path):
    """When backtest produces BUY signals but none are journaled,
    missed_entries must be > 0."""
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3, threshold_pct=1.0)
    shadow = ShadowAccount(strategy, db_path=db)

    # Trending prices → shadow will BUY.
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    result = shadow.compare(prices=prices, ticker="TEST")

    # The backtest should have bought.  Journal is empty → missed entries.
    assert result.shadow_trades > 0
    assert result.missed_entries > 0
    assert "missed" in " ".join(result.gap_notes).lower()


def test_shadow_detects_hold_overrides(tmp_path):
    """Journaled HOLD signals with non-zero confidence = overrides."""
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    # Journal a HOLD that had confidence (an override).
    _journal_signals(db, [
        _make_signal(action=SignalAction.HOLD, confidence=0.7, reason="Overridden by user."),
    ])

    prices = [100.0] * 10
    result = shadow.compare(prices=prices, ticker="TEST")

    assert result.signals_overridden > 0
    assert any("override" in n.lower() or "HOLD" in n for n in result.gap_notes)


def test_shadow_reads_journaled_signals(tmp_path):
    """Journaled BUY/SELL signals should be counted correctly."""
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    _journal_signals(db, [
        _make_signal(action=SignalAction.BUY),
        _make_signal(action=SignalAction.BUY),
        _make_signal(action=SignalAction.SELL),
        _make_signal(action=SignalAction.HOLD, confidence=0.0),
    ])

    prices = [100.0, 101.0, 102.0, 103.0, 104.0]
    result = shadow.compare(prices=prices, ticker="TEST")

    assert result.buy_signals == 2
    assert result.sell_signals == 1
    assert result.hold_signals == 1
    assert result.total_signals_journaled == 4


def test_shadow_adherence_perfect_when_no_journaled_signals(tmp_path):
    """Zero journaled signals → adherence should be None (not computable)."""
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3, threshold_pct=1.0)
    shadow = ShadowAccount(strategy, db_path=db)

    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    result = shadow.compare(prices=prices, ticker="TEST")

    assert result.adherence_pct == 100.0 or result.adherence_pct is None


def test_shadow_does_not_crash_with_missing_db(tmp_path):
    """Missing DB file should not crash — just return zero journaled signals."""
    db = str(tmp_path / "does_not_exist" / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    prices = [100.0, 101.0, 102.0, 103.0, 104.0]
    result = shadow.compare(prices=prices, ticker="TEST")

    assert result.total_signals_journaled == 0
    assert result.buy_signals == 0


def test_shadow_handles_from_and_to_dates(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    result = shadow.compare(
        prices=prices, ticker="TEST",
        from_date="2026-04-01", to_date="2026-04-29",
    )

    assert result.from_date == "2026-04-01"
    assert result.to_date == "2026-04-29"


# ── Overtrading score ──────────────────────────────────────────────────────────

def test_overtrading_zero_when_perfect_match():
    score = _overtrading_score(journaled_total=5, backtest_total=5, extra=0, overridden=0)
    assert score == 0.0


def test_overtrading_high_when_way_more_journaled():
    score = _overtrading_score(journaled_total=50, backtest_total=10, extra=40, overridden=10)
    assert score > 50


def test_overtrading_100_when_no_backtest_but_journaled():
    score = _overtrading_score(journaled_total=10, backtest_total=0, extra=0, overridden=0)
    assert score == 100.0


def test_overtrading_zero_when_both_zero():
    score = _overtrading_score(journaled_total=0, backtest_total=0, extra=0, overridden=0)
    assert score == 0.0


# ── Shadow report rendering ────────────────────────────────────────────────────

def test_render_shadow_report_includes_all_sections(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    result = shadow.compare(prices=prices, ticker="TEST")
    report = render_shadow_report(result)

    assert "Shadow Account" in report
    assert "## Summary" in report
    assert "## Drift metrics" in report
    assert "Signal adherence" in report
    assert "Missed entries" in report
    assert "## Behavioral gap analysis" in report
    assert "## How to read this" in report


def test_render_shadow_report_includes_guidance(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    prices = [100.0, 101.0, 102.0, 103.0, 104.0]
    result = shadow.compare(prices=prices, ticker="TEST")
    report = render_shadow_report(result)

    assert "doesn't judge" in report
    assert "Shadow (mechanical)" in report
    assert "Actual (journaled)" in report


def test_shadow_extra_signals_detected(tmp_path):
    """When journal has more signals than backtest, extra_signals > 0."""
    db = str(tmp_path / "test.sqlite3")
    strategy = SimpleMomentumStrategy(lookback=3)
    shadow = ShadowAccount(strategy, db_path=db)

    # Journal many signals even though prices are flat (backtest will HOLD).
    _journal_signals(db, [
        _make_signal(action=SignalAction.BUY, confidence=0.5, reason="Impulse."),
        _make_signal(action=SignalAction.SELL, confidence=0.5, reason="Panic."),
        _make_signal(action=SignalAction.BUY, confidence=0.5, reason="FOMO."),
        _make_signal(action=SignalAction.SELL, confidence=0.5, reason="Fear."),
    ])

    prices = [100.0] * 5
    result = shadow.compare(prices=prices, ticker="TEST")

    assert result.extra_signals > 0
    assert "extra" in " ".join(result.gap_notes).lower()
