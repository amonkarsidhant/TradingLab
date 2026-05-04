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


# ── Registry ──────────────────────────────────────────────────────────────────
_REGISTRY: dict[str, type["Strategy"]] = {}


def register_strategy(
    name: str,
    *,
    category: str = "uncategorized",
    hypothesis: str = "",
    expected_market_regime: str = "any",
    failure_modes: list[str] | None = None,
    parameters: dict[str, tuple[Any, str]] | None = None,
    required_data: str = "close",
) -> callable:
    """Decorator that auto-registers a strategy class.

    Usage:
        @register_strategy(
            name="my_strategy",
            category="momentum",
            hypothesis="RSI reversal predicts mean reversion",
        )
        class MyStrategy(Strategy):
            ...
    """
    def decorator(cls: type["Strategy"]) -> type["Strategy"]:
        cls.name = name
        cls.metadata = StrategyMetadata(
            name=name,
            category=category,
            hypothesis=hypothesis,
            expected_market_regime=expected_market_regime,
            failure_modes=failure_modes or [],
            parameters=parameters or {},
            required_data=required_data,
        )
        _REGISTRY[name] = cls
        return cls

    return decorator


class Strategy(ABC):
    name: str = ""
    metadata: StrategyMetadata | None = None

    def __init__(self) -> None:
        pass  # Subclasses call super().__init__() after setting their own attrs

    @abstractmethod
    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        raise NotImplementedError
