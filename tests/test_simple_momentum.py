from trading_lab.models import SignalAction
from trading_lab.strategies.simple_momentum import SimpleMomentumStrategy


def test_simple_momentum_buy_signal():
    strategy = SimpleMomentumStrategy(lookback=5, threshold_pct=1.0)
    signal = strategy.generate_signal("AAPL_US_EQ", [100, 101, 102, 103, 104, 106])

    assert signal.action == SignalAction.BUY
    assert signal.suggested_quantity == 1.0


def test_simple_momentum_hold_when_not_enough_data():
    strategy = SimpleMomentumStrategy(lookback=5, threshold_pct=1.0)
    signal = strategy.generate_signal("AAPL_US_EQ", [100, 101])

    assert signal.action == SignalAction.HOLD
