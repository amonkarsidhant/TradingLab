"""Meta-learning engine for Sid Trading Lab Phase 1.

Modules:
  - sweeper: Walk-forward strategy backtest sweep per regime window
  - allocator: Regime-aware capital allocation (Sharpe-weighted sizing)
  - ab_harness: A/B statistical comparison of strategies
  - performance_feedback: Live vs backtest divergence detection
"""
from __future__ import annotations

from trading_lab.meta.sweeper import StrategySweeper, run_sweep
from trading_lab.meta.allocator import CapitalAllocator, Allocation
from trading_lab.meta.ab_harness import ABHarness, run_ab_test
from trading_lab.meta.performance_feedback import PerformanceFeedback, run_feedback

__all__ = [
    "StrategySweeper",
    "run_sweep",
    "CapitalAllocator",
    "Allocation",
    "ABHarness",
    "run_ab_test",
    "PerformanceFeedback",
    "run_feedback",
]
