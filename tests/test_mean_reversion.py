"""
Tests for MeanReversionStrategy (RSI-based).

No network calls. No API keys. All tests use deterministic price lists.
"""
import pytest

from trading_lab.models import SignalAction
from trading_lab.strategies.mean_reversion import MeanReversionStrategy


def test_rejects_invalid_thresholds():
    with pytest.raises(ValueError):
        MeanReversionStrategy(oversold=50, overbought=40)


def test_rejects_period_too_small():
    with pytest.raises(ValueError, match="period must be at least 2"):
        MeanReversionStrategy(period=1)


def test_holds_when_not_enough_data():
    strategy = MeanReversionStrategy(period=5, oversold=30, overbought=70)
    prices = [100.0] * 6  # need period+2 = 7
    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.HOLD
    assert "Need" in signal.reason


def test_buy_when_rsi_crosses_below_oversold():
    """RSI crossing below 30 must produce a BUY."""
    strategy = MeanReversionStrategy(period=5, oversold=30, overbought=70)

    # oscillating then a sharp drop: RSI crosses below 30.
    prices = [110.0, 108.0, 110.0, 108.0, 110.0, 108.0, 100.0]

    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.BUY
    assert "oversold" in signal.reason.lower()
    assert signal.suggested_quantity > 0


def test_sell_when_rsi_crosses_above_overbought():
    """RSI crossing above 70 must produce a SELL."""
    strategy = MeanReversionStrategy(period=5, oversold=30, overbought=70)

    # oscillating then a sharp rise: RSI crosses above 70.
    prices = [100.0, 102.0, 100.0, 102.0, 100.0, 102.0, 115.0]

    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.SELL
    assert "overbought" in signal.reason.lower()
    assert signal.suggested_quantity < 0


def test_hold_when_rsi_in_middle():
    """RSI between oversold and overbought must HOLD."""
    strategy = MeanReversionStrategy(period=5, oversold=30, overbought=70)

    # flat/oscillating prices keep RSI in mid-range.
    prices = [100.0, 100.5, 100.0, 100.5, 100.0, 100.5, 100.0]

    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.HOLD
    assert "no threshold breach" in signal.reason.lower()


def test_signal_includes_strategy_name_and_ticker():
    strategy = MeanReversionStrategy(period=5, oversold=30, overbought=70)
    prices = [100.0, 100.5, 100.0, 100.5, 100.0, 100.5, 100.0]
    signal = strategy.generate_signal("TSLA_US_EQ", prices)
    assert signal.strategy == "mean_reversion"
    assert signal.ticker == "TSLA_US_EQ"


def test_rsi_boundary_all_gain_is_100():
    """All gains (RSI=100) must not crash."""
    strategy = MeanReversionStrategy(period=3, oversold=30, overbought=70)
    prices = [100.0, 101.0, 102.0, 103.0, 104.0]  # all gains, period+2=5
    signal = strategy.generate_signal("TEST", prices)
    assert signal.action in {SignalAction.HOLD, SignalAction.SELL}


def test_rsi_boundary_all_loss_is_zero():
    """All losses (RSI=0) must not crash."""
    strategy = MeanReversionStrategy(period=3, oversold=30, overbought=70)
    prices = [100.0, 99.0, 98.0, 97.0, 96.0]  # all losses, period+2=5
    signal = strategy.generate_signal("TEST", prices)
    assert signal.action in {SignalAction.HOLD, SignalAction.BUY}
