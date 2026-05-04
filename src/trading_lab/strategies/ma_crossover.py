from __future__ import annotations

from typing import Any

from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy, register_strategy


@register_strategy(
    name="ma_crossover",
    category="trend",
    hypothesis="When a short-term moving average crosses above a long-term one, a new uptrend is confirmed. Cross below signals a downtrend.",
    expected_market_regime="bull_trending",
    failure_modes=[
        "Whipsaws in ranging markets: crossovers produce false signals that reverse immediately",
        "Lagging indicator: signals arrive late, missing the bulk of the move",
        "Slow SMAs smooth out noise but also delay signal response to sudden reversals",
    ],
    parameters={
        "fast": (10, "Fast SMA period"),
        "slow": (30, "Slow SMA period (must be > fast)"),
    },
    required_data="close",
)
class MovingAverageCrossoverStrategy(Strategy):
    def __init__(self, fast: int = 10, slow: int = 30):
        if fast >= slow:
            raise ValueError(f"fast period ({fast}) must be less than slow period ({slow})")
        super().__init__()
        self.fast = fast
        self.slow = slow

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        required = self.slow + 1
        if len(prices) < required:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.HOLD,
                confidence=0.0,
                reason=f"Need {required} prices, got {len(prices)}.",
            )

        fast_curr = _sma(prices, self.fast)
        slow_curr = _sma(prices, self.slow)
        fast_prev = _sma(prices[:-1], self.fast)
        slow_prev = _sma(prices[:-1], self.slow)

        if fast_prev <= slow_prev and fast_curr > slow_curr:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.BUY,
                confidence=0.7,
                reason=f"Fast SMA({self.fast}) crossed above Slow SMA({self.slow}).",
                suggested_quantity=1.0,
            )

        if fast_prev >= slow_prev and fast_curr < slow_curr:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.SELL,
                confidence=0.7,
                reason=f"Fast SMA({self.fast}) crossed below Slow SMA({self.slow}).",
                suggested_quantity=-1.0,
            )

        return Signal(
            strategy=self.name,
            ticker=ticker,
            action=SignalAction.HOLD,
            confidence=0.5,
            reason="No crossover detected.",
        )


def _sma(prices: list[float], period: int) -> float:
    return sum(prices[-period:]) / period