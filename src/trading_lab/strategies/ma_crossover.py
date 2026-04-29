from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy


class MovingAverageCrossoverStrategy(Strategy):
    """BUY when fast SMA crosses above slow SMA. SELL on cross below."""

    name = "ma_crossover"

    def __init__(self, fast: int = 10, slow: int = 30):
        if fast >= slow:
            raise ValueError(f"fast period ({fast}) must be less than slow period ({slow})")
        self.fast = fast
        self.slow = slow

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        required = self.slow + 1  # need slow periods for the SMA + 1 for the crossover check
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
