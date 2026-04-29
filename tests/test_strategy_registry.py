"""
Tests for the strategy registry.

No network calls. No API keys. No broker integration.
"""
import pytest

from trading_lab.strategies import get_strategy, list_strategies
from trading_lab.strategies.base import Strategy


def test_registry_returns_all_strategies():
    """list_strategies() must include all three concrete strategies."""
    registry = list_strategies()
    assert "simple_momentum" in registry
    assert "ma_crossover" in registry
    assert "mean_reversion" in registry
    assert len(registry) >= 3


def test_registry_classes_are_strategy_subclasses():
    """Every entry must be a subclass of Strategy."""
    for name, cls in list_strategies().items():
        assert issubclass(cls, Strategy), f"{name} is not a Strategy subclass"


def test_get_strategy_defaults():
    """get_strategy() must return a Strategy instance with default params."""
    for name in list_strategies():
        strategy = get_strategy(name)
        assert isinstance(strategy, Strategy), f"{name}: {type(strategy)}"
        assert strategy.name == name


def test_get_strategy_with_kwargs():
    """Extra kwargs must be forwarded to the strategy constructor."""
    strategy = get_strategy("ma_crossover", fast=5, slow=15)
    assert strategy.fast == 5
    assert strategy.slow == 15


def test_get_strategy_unknown_raises():
    """An unrecognised strategy name must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown strategy"):
        get_strategy("nonexistent_strategy")


def test_get_strategy_error_includes_available_names():
    """The error message must list available strategies."""
    with pytest.raises(ValueError, match="simple_momentum"):
        get_strategy("bogus")


def test_registry_does_not_include_abstract_base():
    """Strategy ABC must not appear in the registry."""
    registry = list_strategies()
    for cls in registry.values():
        assert cls is not Strategy
