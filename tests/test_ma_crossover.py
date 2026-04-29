"""
Tests for MovingAverageCrossoverStrategy.

No network calls. No API keys. All tests use deterministic price lists.
"""
import pytest

from trading_lab.models import SignalAction
from trading_lab.strategies.ma_crossover import MovingAverageCrossoverStrategy


def test_rejects_fast_not_less_than_slow():
    with pytest.raises(ValueError, match="fast period"):
        MovingAverageCrossoverStrategy(fast=10, slow=10)

    with pytest.raises(ValueError, match="fast period"):
        MovingAverageCrossoverStrategy(fast=20, slow=10)


def test_holds_when_not_enough_data():
    strategy = MovingAverageCrossoverStrategy(fast=5, slow=20)
    prices = [100.0] * 20  # exactly slow, need slow+1
    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.HOLD
    assert "Need" in signal.reason


def test_buy_on_bullish_crossover():
    """Fast SMA crossing above slow SMA must produce a BUY."""
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)

    # Decreasing trend then a jump up: fast SMA crosses above slow SMA.
    prices = [110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 98.0, 115.0]

    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.BUY


def test_sell_on_bearish_crossover():
    """Fast SMA crossing below slow SMA must produce a SELL."""
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)

    # Increasing trend then a drop: fast SMA crosses below slow SMA.
    prices = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 95.0]

    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.SELL


def test_hold_when_no_crossover():
    """When fast SMA stays above slow SMA (no cross), must HOLD."""
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)

    prices = [
        100.0, 101.0, 102.0, 103.0, 104.0,
        105.0, 106.0, 107.0,
    ]

    signal = strategy.generate_signal("TEST", prices)
    assert signal.action == SignalAction.HOLD
    assert "No crossover" in signal.reason


def test_signal_includes_strategy_name_and_ticker():
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
    signal = strategy.generate_signal("AAPL_US_EQ", prices)
    assert signal.strategy == "ma_crossover"
    assert signal.ticker == "AAPL_US_EQ"


def test_buy_sets_positive_quantity():
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)
    prices = [110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 98.0, 115.0]
    signal = strategy.generate_signal("TEST", prices)
    assert signal.suggested_quantity > 0


def test_sell_sets_negative_quantity():
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)
    prices = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 95.0]
    signal = strategy.generate_signal("TEST", prices)
    assert signal.suggested_quantity < 0
