"""Factsheet engine — comprehensive strategy evaluation report."""
from __future__ import annotations

from trading_lab.backtest.engine import BacktestEngine, BacktestResult
from trading_lab.backtest.sweep import SweepEngine
from trading_lab.round_trips import NullRoundTripTracker
from trading_lab.strategies.base import StrategyMetadata
from trading_lab.strategies import get_strategy, list_strategies

_COST_SCENARIOS = [
    ("0%/0% (ideal)", 0.0, 0.0),
    ("0.1%/0.05% (low)", 0.001, 0.0005),
    ("0.5%/0.2% (typical)", 0.005, 0.002),
    ("1%/0.5% (high)", 0.01, 0.005),
]


def _buy_and_hold_return(prices):
    if len(prices) < 2:
        return 0.0
    return (prices[-1] - prices[0]) / prices[0] * 100


def _parameter_stability(results):
    returns = [r.metrics.get("total_return_pct", 0) or 0 for r in results]
    if len(returns) < 2:
        return {"mean_return": 0, "std_return": 0, "cv": None, "stable_range": False}
    mean_r = sum(returns) / len(returns)
    std_r = (sum((r - mean_r) ** 2 for r in returns) / max(len(returns) - 1, 1)) ** 0.5
    cv = std_r / abs(mean_r) if abs(mean_r) > 0.01 else None
    return {
        "mean_return": round(mean_r, 2),
        "std_return": round(std_r, 2),
        "cv": round(cv, 2) if cv else None,
        "stable_range": cv is not None and cv < 1.0,
    }


def _verdict(metrics, sweeps, meta):
    sharpe = metrics.get("sharpe_ratio") or 0
    dd = abs(metrics.get("max_drawdown_pct") or 0)
    trades = metrics.get("total_trades") or 0
    stable = _parameter_stability(sweeps).get("stable_range", False) if sweeps else False
    issues = []
    if sharpe < 0.5:
        issues.append("sharpe")
    if dd > 40:
        issues.append("drawdown")
    if trades < 5:
        issues.append("few-trades")
    if not stable and sweeps:
        issues.append("unstable")
    if len(issues) >= 3:
        return "reject"
    if len(issues) >= 1:
        return "watch"
    return "research"


class FactsheetEngine:
    def __init__(self, strategy_name: str, ticker: str, capital: float = 10000.0):
        self.strategy_name = strategy_name
        self.ticker = ticker
        self.capital = capital
        cls = list_strategies().get(strategy_name)
        if not cls:
            raise ValueError(f"Unknown strategy '{strategy_name}'")
        self._cls = cls

    def metadata(self) -> StrategyMetadata | None:
        return getattr(self._cls, "metadata", None)

    def run_backtest(self, commission_pct=0.0, slippage_pct=0.0, prices=None):
        kwargs = self._default_params()
        strategy = self._cls(**kwargs) if isinstance(kwargs, dict) else self._cls()
        engine = BacktestEngine(strategy, self.capital, commission_pct, slippage_pct)
        if prices is None:
            from trading_lab.data.market_data import make_provider
            provider = make_provider(source="chained", ticker=self.ticker, cache_db="./trading_lab_cache.sqlite3")
            prices = provider.get_prices(ticker=self.ticker, lookback=252)
        return engine.run(prices=prices, ticker=self.ticker, tracker=NullRoundTripTracker())

    def cost_sensitivity(self, prices):
        results = []
        for label, comm, slip in _COST_SCENARIOS:
            bt = self.run_backtest(commission_pct=comm, slippage_pct=slip, prices=prices)
            results.append({
                "scenario": label,
                "commission_pct": comm,
                "slippage_pct": slip,
                "total_return_pct": bt.metrics.get("total_return_pct"),
                "sharpe_ratio": bt.metrics.get("sharpe_ratio"),
                "max_drawdown_pct": bt.metrics.get("max_drawdown_pct"),
                "total_trades": bt.metrics.get("total_trades"),
            })
        return results

    def parameter_stability(self, prices):
        grid = self._param_grid()
        if not grid:
            return {"_results": []}
        engine = SweepEngine(self._cls, param_grid=grid, capital=self.capital)
        result = engine.run(prices=prices, ticker=self.ticker)
        stab = _parameter_stability(result.results) if result.results else {}
        best = result.best
        return {
            "grid": grid,
            "combinations": len(result.results),
            **stab,
            "_results": result.results if result.results else [],
            "best_params": result.best_params,
            "best_metrics": {
                k: best.metrics.get(k) for k in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate"]
            } if best else None,
        }

    def benchmark_comparison(self, prices):
        bh = _buy_and_hold_return(prices)
        bt = self.run_backtest(prices=prices)
        strat_return = bt.metrics.get("total_return_pct")
        return {
            "buy_and_hold_return_pct": round(bh, 2),
            "strategy_return_pct": strat_return,
            "outperformance_pct": round((strat_return or 0) - bh, 2) if strat_return is not None else None,
        }

    def generate(self, prices=None):
        from trading_lab.data.market_data import make_provider
        provider = make_provider(source="chained", ticker=self.ticker, cache_db="./trading_lab_cache.sqlite3")
        p = prices if prices is not None else provider.get_prices(ticker=self.ticker, lookback=252)
        bt = self.run_backtest(prices=p)
        costs = self.cost_sensitivity(prices=p)
        stability = self.parameter_stability(prices=p)
        benchmark = self.benchmark_comparison(prices=p)
        meta = self.metadata()
        verdict = _verdict(bt.metrics, stability.get("_results", []), meta)
        return {
            "strategy": self.strategy_name,
            "ticker": self.ticker,
            "data_source": "chained",
            "metadata": {
                "hypothesis": meta.hypothesis if meta else None,
                "category": meta.category if meta else None,
                "expected_market_regime": meta.expected_market_regime if meta else None,
                "failure_modes": meta.failure_modes if meta else [],
                "parameters": meta.parameters if meta else {},
                "required_data": meta.required_data if meta else "close",
            },
            "backtest": {
                "initial_capital": self.capital,
                "final_equity": bt.final_equity,
                "metrics": bt.metrics,
            },
            "cost_sensitivity": costs,
            "parameter_stability": stability,
            "benchmark": benchmark,
            "verdict": verdict,
        }

    def _default_params(self):
        n = self.strategy_name
        if n == "simple_momentum":
            return {"lookback": 5, "threshold_pct": 1.0}
        if n == "ma_crossover":
            return {"fast": 10, "slow": 30}
        if n == "mean_reversion":
            return {"period": 14, "oversold": 30, "overbought": 70}
        if n == "volume_price":
            return {"lookback": 10, "threshold_pct": 2.0, "volume_multiplier": 1.5}
        return {}

    def _param_grid(self):
        n = self.strategy_name
        if n == "simple_momentum":
            return {"lookback": [3, 5, 7, 10, 14, 20], "threshold_pct": [0.5, 1.0, 2.0, 3.0]}
        if n == "ma_crossover":
            return {"fast": [5, 8, 13], "slow": [21, 34, 55]}
        if n == "mean_reversion":
            return {"period": [7, 14, 21], "oversold": [20, 25, 30], "overbought": [65, 70, 75]}
        return {}
