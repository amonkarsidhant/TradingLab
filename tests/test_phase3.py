"""
Phase 3 integration tests for signal_bridge, failure_alerts, and discord wiring.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import tempfile
import os

from trading_lab.models import Signal, SignalAction
from trading_lab.round_trips import RoundTrip, RoundTripTracker
from trading_lab.signal_bridge import SignalRoundTripBridge
from trading_lab.watcher.failure_alerts import FailureAlertThrottle


def test_signal_round_trip_bridge():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "test.db")
        bridge = SignalRoundTripBridge(db)

        # BUY opens a slot
        buy_sig = Signal(
            strategy="simple_momentum",
            ticker="AAPL_US_EQ",
            action=SignalAction.BUY,
            confidence=0.8,
            reason="momentum spike",
            suggested_quantity=10,
        )
        bridge.on_signal(signal=buy_sig, price=150.0, dry_run=False)

        # SELL closes it
        sell_sig = Signal(
            strategy="simple_momentum",
            ticker="AAPL_US_EQ",
            action=SignalAction.SELL,
            confidence=0.7,
            reason="profit target",
            suggested_quantity=10,
        )
        bridge.on_signal(signal=sell_sig, price=165.0, dry_run=False)

        trips = bridge.get_trips("AAPL_US_EQ")
        assert len(trips) == 1, f"expected 1 trip, got {len(trips)}"
        trip = trips[0]
        assert trip.ticker == "AAPL_US_EQ"
        assert trip.entry_price == 150.0
        assert trip.exit_price == 165.0
        assert trip.pnl == 150.0  # (165-150)*10
        assert trip.pnl_pct == 10.0
        print("  signal_bridge: PASS")


def test_failure_alert_throttle():
    throttle = FailureAlertThrottle()

    ep = "positions"
    err = "connection timeout"

    # First failure → notify
    n, c = throttle.record(ep, err)
    assert n is True and c == 1

    # Same error, 2nd-9th → no notify
    for _ in range(8):
        n, c = throttle.record(ep, err)
        assert n is False

    # 10th failure → notify
    n, c = throttle.record(ep, err)
    assert n is True and c == 10

    # clear resets
    throttle.clear(ep, err)
    n, c = throttle.record(ep, err)
    assert n is True and c == 1

    # Different error signature → immediate notify
    n, c = throttle.record(ep, "502 bad gateway")
    assert n is True and c == 1

    print("  failure_alerts: PASS")


def test_round_trip_db_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "rt.db")
        rt = RoundTripTracker(db)
        trip = RoundTrip(
            ticker="TSLA_US_EQ",
            position_id="TSLA_123",
            entry_price=200.0,
            exit_price=220.0,
            quantity=5.0,
            pnl=100.0,
            pnl_pct=10.0,
            days_held=5,
            strategy="ma_crossover",
            entry_date="2024-01-01",
            exit_date="2024-01-06",
        )
        rt.record(trip)
        stats = rt.get_sharpe_for("TSLA_US_EQ")
        assert stats["trips"] == 0
        assert stats["sharpe"] is None
        assert stats["avg_pnl_pct"] is None  # <3 trips → no stats
        print("  round_trips persistence: PASS")


if __name__ == "__main__":
    test_signal_round_trip_bridge()
    test_failure_alert_throttle()
    test_round_trip_db_persistence()
    print("\nAll Phase 3 tests passed.")
