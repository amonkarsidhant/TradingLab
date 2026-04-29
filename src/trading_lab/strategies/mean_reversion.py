from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy


class MeanReversionStrategy(Strategy):
    """BUY when RSI crosses below oversold. SELL when RSI crosses above overbought.

    Uses Wilder's smoothing for the RSI calculation.
    """

    name = "mean_reversion"

    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70):
        if oversold >= overbought:
            raise ValueError(f"oversold ({oversold}) must be less than overbought ({overbought})")
        if period < 2:
            raise ValueError(f"period must be at least 2, got {period}")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        required = self.period + 2  # period for RSI calc + 1 for the crossover check
        if len(prices) < required:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.HOLD,
                confidence=0.0,
                reason=f"Need {required} prices, got {len(prices)}.",
            )

        rsi_curr = _rsi(prices, self.period)
        rsi_prev = _rsi(prices[:-1], self.period)

        if rsi_prev >= self.oversold and rsi_curr < self.oversold:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.BUY,
                confidence=0.65,
                reason=f"RSI({self.period}) dropped below oversold ({self.oversold}): {rsi_curr:.1f}.",
                suggested_quantity=1.0,
            )

        if rsi_prev <= self.overbought and rsi_curr > self.overbought:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.SELL,
                confidence=0.65,
                reason=f"RSI({self.period}) rose above overbought ({self.overbought}): {rsi_curr:.1f}.",
                suggested_quantity=-1.0,
            )

        return Signal(
            strategy=self.name,
            ticker=ticker,
            action=SignalAction.HOLD,
            confidence=0.5,
            reason=f"RSI({self.period})={rsi_curr:.1f} — no threshold breach.",
        )


def _rsi(prices: list[float], period: int) -> float:
    """Wilder's RSI over the last `period` closes."""
    deltas = [prices[i] - prices[i - 1] for i in range(-period, 0)]
    gain = sum(d for d in deltas if d > 0) / period
    loss = sum(-d for d in deltas if d < 0) / period
    if loss == 0:
        return 100.0
    rs = gain / loss
    return 100.0 - (100.0 / (1.0 + rs))
