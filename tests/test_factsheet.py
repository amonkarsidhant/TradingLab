"""Tests for strategy factsheet system with static data."""
from trading_lab.factsheet.engine import FactsheetEngine, _buy_and_hold_return, _parameter_stability
from trading_lab.factsheet.report import render_factsheet
from trading_lab.strategies import get_strategy


STATIC_PRICES = [100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 107.5, 108.0, 109.2, 110.5, 112.0]


def test_buy_and_hold_return():
    r = _buy_and_hold_return([100.0, 110.0])
    assert r == 10.0


def test_buy_and_hold_return_falling():
    r = _buy_and_hold_return([100.0, 95.0, 90.0])
    assert r == -10.0


def test_buy_and_hold_return_insufficient_data():
    r = _buy_and_hold_return([100.0])
    assert r == 0.0


def test_parameter_stability_same_values():
    class MockResult:
        def __init__(self, r):
            self.metrics = {"total_return_pct": r}
    results = [MockResult(10), MockResult(10), MockResult(10)]
    stab = _parameter_stability(results)
    assert stab["std_return"] == 0.0
    assert stab["stable_range"] is True


def test_parameter_stability_high_variance():
    class MockResult:
        def __init__(self, r):
            self.metrics = {"total_return_pct": r}
    results = [MockResult(-20), MockResult(0), MockResult(30)]
    stab = _parameter_stability(results)
    assert stab["cv"] is not None
    assert stab["cv"] > 1.0


def test_factsheet_generates_with_static_data():
    engine = FactsheetEngine("simple_momentum", "test", capital=10000)
    data = engine.generate(prices=STATIC_PRICES)
    assert data["strategy"] == "simple_momentum"
    assert data["ticker"] == "test"
    assert data["metadata"]["category"] == "momentum"
    assert data["metadata"]["hypothesis"] is not None
    assert len(data["metadata"]["failure_modes"]) > 0
    assert data["backtest"]["metrics"]["total_trades"] >= 0
    assert data["benchmark"]["buy_and_hold_return_pct"] is not None
    assert len(data["cost_sensitivity"]) == 4
    assert data["verdict"] in ("research", "watch", "reject")


def test_factsheet_metadata_all_strategies():
    from trading_lab.strategies import list_strategies
    for name, cls in list_strategies().items():
        if name in ("sentiment",):
            continue
        meta = cls.metadata
        assert meta is not None, f"{name} missing metadata"
        assert meta.name == name
        assert meta.category in ("momentum", "mean_reversion", "trend", "breakout", "sentiment")
        assert meta.hypothesis is not None
        assert len(meta.failure_modes) > 0
        assert meta.required_data in ("close", "sentiment")


def test_factsheet_renders_markdown():
    engine = FactsheetEngine("simple_momentum", "test", capital=10000)
    data = engine.generate(prices=STATIC_PRICES)
    report = render_factsheet(data)
    assert "# Strategy Factsheet:" in report
    assert "## Strategy Hypothesis" in report
    assert "## Backtest Performance" in report
    assert "## Benchmark Comparison" in report
    assert "## Cost Sensitivity" in report
    assert "## Verdict" in report


def test_factsheet_cost_sensitivity_static():
    engine = FactsheetEngine("simple_momentum", "test", capital=10000)
    costs = engine.cost_sensitivity(prices=STATIC_PRICES)
    assert len(costs) == 4
    for c in costs:
        assert "scenario" in c
        assert "total_return_pct" in c
        assert "sharpe_ratio" in c


def test_factsheet_benchmark_static():
    engine = FactsheetEngine("simple_momentum", "test", capital=10000)
    bench = engine.benchmark_comparison(prices=STATIC_PRICES)
    assert "buy_and_hold_return_pct" in bench
    assert "strategy_return_pct" in bench


def test_factsheet_parameter_stability_static():
    engine = FactsheetEngine("simple_momentum", "test", capital=10000)
    stab = engine.parameter_stability(prices=STATIC_PRICES)
    assert "combinations" in stab
    assert "best_params" in stab
