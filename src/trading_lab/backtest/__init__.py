"""
Backtest engine for Sid Trading Lab.

Walk-forward backtesting: slide a window through historical prices,
feed each window to a strategy, simulate entries and exits, and
compute standard performance metrics.

No network calls. No broker calls. No order placement.
"""
from trading_lab.backtest.engine import BacktestEngine, BacktestResult, BacktestTrade
from trading_lab.backtest.metrics import compute_metrics
from trading_lab.backtest.report import render_report

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BacktestTrade",
    "compute_metrics",
    "render_report",
]
