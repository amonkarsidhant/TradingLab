from trading_lab.models import Signal, SignalAction
from trading_lab.risk import RiskPolicy


def test_hold_signal_is_not_approved():
    policy = RiskPolicy()
    signal = Signal(
        strategy="test",
        ticker="AAPL_US_EQ",
        action=SignalAction.HOLD,
        confidence=0.9,
        reason="No trade",
    )

    approved, reason = policy.approve(signal)

    assert approved is False
    assert "HOLD" in reason


def test_large_quantity_is_not_approved():
    policy = RiskPolicy(max_quantity_per_order=1.0)
    signal = Signal(
        strategy="test",
        ticker="AAPL_US_EQ",
        action=SignalAction.BUY,
        confidence=0.9,
        reason="Test",
        suggested_quantity=2.0,
    )

    approved, reason = policy.approve(signal)

    assert approved is False
    assert "exceeds" in reason
