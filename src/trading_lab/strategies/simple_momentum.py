from __future__ import annotations

from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy, register_strategy


@register_strategy(
    name="simple_momentum",
    category="momentum",
    hypothesis="Assets that have moved up recently tend to continue moving up (and vice versa for moves down).",
    expected_market_regime="bull_trending",
    failure_modes=[
        "Fails in ranging/choppy markets where prices oscillate without direction",
        "Whipsaw losses when trend reverses abruptly after entry signal",
        "Confidence scales with move size, creating larger entries near local tops",
    ],
    parameters={
        "lookback": (5, "Number of periods to measure price change"),
        "threshold_pct": (1.0, "Minimum % change to trigger a signal"),
    },
    required_data="close",
)
class SimpleMomentumStrategy(Strategy):
    def __init__(self, lookback: int = 5, threshold_pct: float = 1.0):
        super().__init__()
        self.lookback = lookback
        self.threshold_pct = threshold_pct

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        if len(prices) < self.lookback + 1:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="Not enough price data.",
            )

        start = prices[-self.lookback - 1]
        end = prices[-1]
        move_pct = ((end - start) / start) * 100

        if move_pct >= self.threshold_pct:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.BUY,
                confidence=min(0.95, 0.5 + move_pct / 10),
                reason=f"Price moved up {move_pct:.2f}% over lookback window.",
                suggested_quantity=1.0,
            )

        if move_pct <= -self.threshold_pct:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.SELL,
                confidence=min(0.95, 0.5 + abs(move_pct) / 10),
                reason=f"Price moved down {move_pct:.2f}% over lookback window.",
                suggested_quantity=-1.0,
            )

        return Signal(
            strategy=self.name,
            ticker=ticker,
            action=SignalAction.HOLD,
            confidence=0.5,
            reason=f"Move {move_pct:.2f}% did not cross threshold.",
        )