from __future__ import annotations

from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy, register_strategy


@register_strategy(
    name="sentiment",
    category="sentiment",
    hypothesis="Extreme market fear creates buying opportunities; extreme greed signals a top.",
    expected_market_regime="any",
    failure_modes=[
        "Stub implementation — always returns HOLD until Fear & Greed Index is wired up",
        "Sentiment can remain extreme for extended periods, leading to premature counter-trend entries",
        "Requires external API integration for actionable signals",
    ],
    parameters={
        "fear_threshold": (20, "Fear & Greed Index value below which is extreme fear"),
        "greed_threshold": (80, "Fear & Greed Index value above which is extreme greed"),
    },
    required_data="sentiment",
)
class SentimentStrategy(Strategy):
    def __init__(self, fear_threshold: int = 20, greed_threshold: int = 80):
        super().__init__()
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
