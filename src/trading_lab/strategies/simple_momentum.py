from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy


class SimpleMomentumStrategy(Strategy):
    name = "simple_momentum"

    def __init__(self, lookback: int = 5, threshold_pct: float = 1.0):
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
