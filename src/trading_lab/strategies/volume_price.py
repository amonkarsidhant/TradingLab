from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy, StrategyMetadata


class VolumePriceStrategy(Strategy):
    name = "volume_price"
    metadata = StrategyMetadata(
        name="volume_price",
        category="breakout",
        hypothesis="Price breakouts accompanied by above-average volume have higher conviction and are more likely to sustain.",
        expected_market_regime="bull_trending",
        failure_modes=[
            "Volume data is simulated from price volatility when real volume unavailable",
            "Fails in low-volatility periods where no volume spikes occur",
            "Can produce false breakouts in high-volatility environments with noise",
        ],
        parameters={
            "lookback": (10, "Lookback period for price change and volume average"),
            "threshold_pct": (2.0, "Minimum % price move to trigger breakout check"),
            "volume_multiplier": (1.5, "Min ratio of current volume to average volume"),
        },
        required_data="close",
    )

    def __init__(self, lookback: int = 10, threshold_pct: float = 2.0, volume_multiplier: float = 1.5):
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self.volume_multiplier = volume_multiplier

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        # This strategy requires both prices and volumes
        # For now, we simulate volume from price volatility as a proxy
        # In a real implementation, we'd pass volumes as a separate array
        if len(prices) < self.lookback + 2:
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.HOLD,
                confidence=0.0,
                reason="Not enough price data.",
            )

        # Calculate price move
        start = prices[-self.lookback - 1]
        end = prices[-1]
        move_pct = ((end - start) / start) * 100

        # Simulate volume spike from recent volatility
        # Higher volatility = higher "volume"
        recent_returns = [abs(prices[i] - prices[i-1]) / prices[i-1] for i in range(-self.lookback, 0)]
        avg_volatility = sum(recent_returns) / len(recent_returns) if recent_returns else 0
        current_volatility = abs(prices[-1] - prices[-2]) / prices[-2] if len(prices) > 1 else 0
        volume_spike = current_volatility / avg_volatility if avg_volatility > 0 else 1.0

        if move_pct >= self.threshold_pct and volume_spike >= self.volume_multiplier:
            confidence = min(0.95, 0.5 + move_pct / 10 + (volume_spike - 1.0) * 0.2)
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.BUY,
                confidence=confidence,
                reason=f"Price up {move_pct:.2f}% with {volume_spike:.1f}x volume spike.",
                suggested_quantity=1.0,
            )

        if move_pct <= -self.threshold_pct and volume_spike >= self.volume_multiplier:
            confidence = min(0.95, 0.5 + abs(move_pct) / 10 + (volume_spike - 1.0) * 0.2)
            return Signal(
                strategy=self.name,
                ticker=ticker,
                action=SignalAction.SELL,
                confidence=confidence,
                reason=f"Price down {move_pct:.2f}% with {volume_spike:.1f}x volume spike.",
                suggested_quantity=-1.0,
            )

        return Signal(
            strategy=self.name,
            ticker=ticker,
            action=SignalAction.HOLD,
            confidence=0.5,
            reason=f"Move {move_pct:.2f}% / vol {volume_spike:.1f}x — no confirmation.",
        )
