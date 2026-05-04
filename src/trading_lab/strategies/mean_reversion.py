from __future__ import annotations

from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy, register_strategy


@register_strategy(
    name="mean_reversion",
    category="mean_reversion",
    hypothesis="Extreme price moves in one direction are likely to revert toward the mean. RSI below oversold signals a bounce; above overbought signals a pullback.",
    expected_market_regime="ranging_calm",
    failure_modes=[
        "Catastrophic losses in strong trends: buying dips in a bear market (catching falling knives)",
        "RSI can stay overbought/oversold for extended periods during strong trends",
        "Fails in low-volatility markets where RSI rarely crosses thresholds",
    ],
    parameters={
        "period": (14, "RSI calculation period (Wilder's smoothing)"),
        "oversold": (30, "RSI threshold for oversold condition"),
        "overbought": (70, "RSI threshold for overbought condition"),
    },
    required_data="close",
)
class MeanReversionStrategy(Strategy):
    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70):
        if oversold >= overbought:
            raise ValueError(f"oversold ({oversold}) must be less than overbought ({overbought})")
        if period < 2:
            raise ValueError(f"period must be at least 2, got {period}")
        super().__init__()
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        required = self.period + 2
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
    deltas = [prices[i] - prices[i - 1] for i in range(-period, 0)]
    gain = sum(d for d in deltas if d > 0) / period
    loss = sum(-d for d in deltas if d < 0) / period
    if loss == 0:
        return 100.0
    rs = gain / loss
    return 100.0 - (100.0 / (1.0 + rs))