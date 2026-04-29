"""
Engine safety tests — verify the ExecutionEngine enforces dry_run and
never calls the broker on rejected signals.

Uses unittest.mock.MagicMock for the broker so no real network calls are made.
"""
import sqlite3
from unittest.mock import MagicMock

import pytest

from trading_lab.engine import ExecutionEngine
from trading_lab.models import Signal, SignalAction
from trading_lab.risk import RiskPolicy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _buy_signal(**overrides) -> Signal:
    defaults = dict(
        strategy="test",
        ticker="AAPL_US_EQ",
        action=SignalAction.BUY,
        confidence=0.9,
        reason="Test BUY",
        suggested_quantity=1.0,
    )
    defaults.update(overrides)
    return Signal(**defaults)


def _mock_broker(dry_run_return: bool = True) -> MagicMock:
    broker = MagicMock()
    broker.market_order.return_value = {
        "dry_run": dry_run_return,
        "message": "Market order not sent.",
        "payload": {},
    }
    return broker


# ── dry_run forwarding ────────────────────────────────────────────────────────

def test_engine_passes_dry_run_true_to_broker():
    """handle_signal(dry_run=True) must call broker.market_order with dry_run=True."""
    broker = _mock_broker()
    engine = ExecutionEngine(broker=broker, risk_policy=RiskPolicy())

    engine.handle_signal(_buy_signal(), dry_run=True)

    broker.market_order.assert_called_once()
    assert broker.market_order.call_args.kwargs["dry_run"] is True


def test_engine_result_shows_not_executed_on_dry_run():
    """Result dict must have executed=False when dry_run=True."""
    broker = _mock_broker()
    engine = ExecutionEngine(broker=broker, risk_policy=RiskPolicy())

    result = engine.handle_signal(_buy_signal(), dry_run=True)

    assert result["executed"] is False


# ── Broker not called on rejected signals ─────────────────────────────────────

def test_engine_never_calls_broker_on_hold_signal():
    """HOLD signals are rejected by RiskPolicy; broker must not be called."""
    broker = _mock_broker()
    engine = ExecutionEngine(broker=broker, risk_policy=RiskPolicy())

    engine.handle_signal(
        Signal(
            strategy="test",
            ticker="AAPL_US_EQ",
            action=SignalAction.HOLD,
            confidence=0.9,
            reason="No trade",
        ),
        dry_run=True,
    )

    broker.market_order.assert_not_called()


def test_engine_never_calls_broker_on_low_confidence_signal():
    """Signals below the confidence threshold must not reach the broker."""
    broker = _mock_broker()
    engine = ExecutionEngine(
        broker=broker, risk_policy=RiskPolicy(min_confidence_to_trade=0.70)
    )

    engine.handle_signal(_buy_signal(confidence=0.50), dry_run=True)

    broker.market_order.assert_not_called()


def test_engine_never_calls_broker_on_oversized_signal():
    """Signals exceeding max_quantity_per_order must not reach the broker."""
    broker = _mock_broker()
    engine = ExecutionEngine(
        broker=broker, risk_policy=RiskPolicy(max_quantity_per_order=1.0)
    )

    engine.handle_signal(_buy_signal(suggested_quantity=5.0), dry_run=True)

    broker.market_order.assert_not_called()


# ── Signal journaling via logger ──────────────────────────────────────────────

def test_engine_journals_approved_signal_when_logger_provided(tmp_path):
    """Approved signals must be written to the signals table."""
    from trading_lab.logger import SnapshotLogger

    db_path = str(tmp_path / "test.sqlite3")
    logger = SnapshotLogger(db_path)
    broker = _mock_broker()
    engine = ExecutionEngine(broker=broker, risk_policy=RiskPolicy(), logger=logger)

    engine.handle_signal(_buy_signal(), dry_run=True)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT ticker, action, approved FROM signals"
        ).fetchone()

    assert row[0] == "AAPL_US_EQ"
    assert row[1] == "BUY"
    assert row[2] == 1  # approved=True


def test_engine_journals_rejected_signal_when_logger_provided(tmp_path):
    """Rejected signals must also be written — approved=0, broker not called."""
    from trading_lab.logger import SnapshotLogger

    db_path = str(tmp_path / "test.sqlite3")
    logger = SnapshotLogger(db_path)
    broker = _mock_broker()
    engine = ExecutionEngine(broker=broker, risk_policy=RiskPolicy(), logger=logger)

    engine.handle_signal(
        Signal(
            strategy="test",
            ticker="AAPL_US_EQ",
            action=SignalAction.HOLD,
            confidence=0.9,
            reason="No trade",
        ),
        dry_run=True,
    )

    broker.market_order.assert_not_called()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT approved FROM signals").fetchone()

    assert row[0] == 0  # approved=False


def test_engine_works_without_logger():
    """Passing no logger must not raise — logger is optional."""
    broker = _mock_broker()
    engine = ExecutionEngine(broker=broker, risk_policy=RiskPolicy(), logger=None)

    result = engine.handle_signal(_buy_signal(), dry_run=True)

    assert "signal" in result
