"""Parameter sweep backtest engine.

Runs a strategy against a grid of parameter combinations and
ranks results by the best-performing variant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading_lab.backtest.engine import BacktestEngine, BacktestResult
from trading_lab.round_trips import NullRoundTripTracker
from trading_lab.strategies.base import Strategy


@dataclass
class SweepResult:
    """Aggregated sweep result: all combos + best."""
    strategy_name: str
    ticker: str
    params_grid: dict[str, list[Any]]
    results: list[BacktestResult] = field(default_factory=list)
    best: BacktestResult | None = None
    best_params: dict[str, Any] = field(default_factory=dict)
    best_metric: str = ""
    best_value: float = 0.0


class SweepEngine:
    """Run backtests over a parameter grid and find the optimal combination.

    Usage:
        engine = SweepEngine(strategy_cls, param_grid={
            "lookback": [3, 5, 10, 20],
            "threshold_pct": [0.5, 1.0, 2.0, 3.0],
        })
        result = engine.run(prices=prices, ticker="AAPL", capital=10000)
    """

    RANK_METRICS = [
        ("sharpe_ratio", True, "Sharpe"),
        ("profit_factor", True, "Profit Factor"),
        ("total_return_pct", True, "Return %"),
        ("max_drawdown_pct", False, "Max DD %"),
        ("win_rate", True, "Win Rate %"),
    ]

    def __init__(
        self,
        strategy_cls: type[Strategy],
        param_grid: dict[str, list[Any]],
        rank_by: str = "sharpe_ratio",
        capital: float = 10_000.0,
    ) -> None:
        self._cls = strategy_cls
        self._grid = param_grid
        self._rank_by = rank_by
        self._capital = capital

    def run(
        self,
        prices: list[float],
        dates: list[str] | None = None,
        ticker: str = "TEST",
    ) -> SweepResult:
        param_names = list(self._grid.keys())
        combos = self._combinations()
        results: list[BacktestResult] = []

        for combo in combos:
            kwargs = dict(zip(param_names, combo))
            strategy = self._cls(**kwargs)
            engine = BacktestEngine(strategy, initial_capital=self._capital)
            bt_result = engine.run(prices=prices, dates=dates, ticker=ticker, tracker=NullRoundTripTracker())
            bt_result.strategy_name = f"{strategy.name}({self._format_params(kwargs)})"
            results.append(bt_result)

        best, best_params = self._pick_best(results)
        best_value = best.metrics.get(self._rank_by, 0) if best else 0

        return SweepResult(
            strategy_name=self._cls.name,
            ticker=ticker,
            params_grid=self._grid,
            results=results,
            best=best,
            best_params=best_params,
            best_metric=self._rank_by,
            best_value=best_value,
        )

    def _combinations(self) -> list[tuple]:
        keys = list(self._grid.keys())
        values = list(self._grid.values())
        return self._product(values)

    @staticmethod
    def _product(lists: list[list]) -> list[tuple]:
        if not lists:
            return [()]
        rest = SweepEngine._product(lists[1:])
        result = []
        for x in lists[0]:
            for r in rest:
                result.append((x,) + r)
        return result

    def _pick_best(
        self, results: list[BacktestResult]
    ) -> tuple[BacktestResult | None, dict[str, Any]]:
        if not results:
            return None, {}

        ascending = self._rank_by == "max_drawdown_pct"
        fallback = float("inf") if ascending else float("-inf")
        ranked = sorted(
            results,
            key=lambda r: r.metrics.get(self._rank_by) if r.metrics.get(self._rank_by) is not None else fallback,
            reverse=not ascending,
        )
        best = ranked[0]
        params_str = best.strategy_name.split("(", 1)
        params = {}
        if len(params_str) == 2:
            part = params_str[1].rstrip(")")
            for pair in part.split(", "):
                k, v = pair.split("=")
                try:
                    params[k] = float(v)
                except ValueError:
                    params[k] = v
        return best, params

    @staticmethod
    def _format_params(params: dict) -> str:
        return ", ".join(f"{k}={v}" for k, v in params.items())
