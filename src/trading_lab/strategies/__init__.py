"""
Strategy registry for Sid Trading Lab.

Import all strategy modules here so Strategy.__subclasses__()
can discover them.  list_strategies() and get_strategy() are the
public API consumed by the CLI.
"""
from __future__ import annotations

from trading_lab.strategies.base import Strategy
from trading_lab.strategies.simple_momentum import SimpleMomentumStrategy
from trading_lab.strategies.ma_crossover import MovingAverageCrossoverStrategy
from trading_lab.strategies.mean_reversion import MeanReversionStrategy
from trading_lab.strategies.volume_price import VolumePriceStrategy
from trading_lab.strategies.sentiment import SentimentStrategy


def list_strategies() -> dict[str, type[Strategy]]:
    """Return {name: StrategyClass} for every concrete strategy."""
    result: dict[str, type[Strategy]] = {}
    for cls in Strategy.__subclasses__():
        name = getattr(cls, "name", cls.__name__)
        if name:
            result[name] = cls
    return result


def get_strategy(name: str, **kwargs) -> Strategy:
    """Instantiate a strategy by name.

    Raises ValueError if the name is not registered.
    """
    registry = list_strategies()
    if name not in registry:
        available = ", ".join(sorted(registry))
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return registry[name](**kwargs)
