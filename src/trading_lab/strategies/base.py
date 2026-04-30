from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from trading_lab.models import Signal


@dataclass
class StrategyMetadata:
    name: str
    category: str  # momentum, mean_reversion, trend, breakout, sentiment
    hypothesis: str
    expected_market_regime: str  # bull_trending, bear_volatile, ranging_calm, any
    failure_modes: list[str]
    parameters: dict[str, tuple[Any, str]] = field(default_factory=dict)
    required_data: str = "close"  # close, OHLCV, sentiment


class Strategy(ABC):
    name: str
    metadata: StrategyMetadata | None = None

    @abstractmethod
    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        raise NotImplementedError
