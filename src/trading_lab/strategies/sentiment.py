"""
Sentiment Strategy — uses market sentiment to generate signals.

For now this is a stub that returns HOLD, but the architecture is ready
for integration with:
  - Fear & Greed Index (CNN)
  - Reddit / X sentiment APIs
  - News sentiment (Adanos, etc.)
  - Polymarket prediction markets

When sentiment data is available, it will:
  - BUY when fear is high (extreme fear = opportunity)
  - SELL when greed is extreme (extreme greed = top)
"""
from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy


class SentimentStrategy(Strategy):
    """BUY on extreme fear, SELL on extreme greed."""

    name = "sentiment"

    def __init__(self, fear_threshold: int = 20, greed_threshold: int = 80):
        self.fear_threshold = fear_threshold
        self.greed_threshold = greed_threshold

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        # TODO: Integrate with Fear & Greed Index API or sentiment feed
        # For now, return HOLD as sentiment data is not yet wired up
        return Signal(
            strategy=self.name,
            ticker=ticker,
            action=SignalAction.HOLD,
            confidence=0.0,
            reason="Sentiment data not yet integrated. Set up Fear & Greed Index API.",
        )
