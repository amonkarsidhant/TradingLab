"""Meta-learning engine for Sid Trading Lab Phase 1-2.

Modules:
  - sweeper: Walk-forward strategy backtest sweep per regime window
  - allocator: Regime-aware capital allocation (Sharpe-weighted sizing)
  - ab_harness: A/B statistical comparison of two strategies
  - performance_feedback: Live vs backtest divergence detection
  - variant_generator: LLM-driven strategy parameter mutation (Phase 2)
  - sandbox: Syntax + safety validation for generated code (Phase 2)
  - variant_validator: Backtest + A/B composite gate for variants (Phase 2)
  - adoption_manager: Git commit + swap active strategy + rollback (Phase 2)
  - watchdog: 48h observation window post-adoption (Phase 2)
  - change_log: Immutable audit trail of strategy mutations (Phase 2)
"""
from trading_lab.meta.ab_harness import ABHarness, ABResult
from trading_lab.meta.adoption_manager import AdoptionManager, AdoptionResult
from trading_lab.meta.allocator import CapitalAllocator, CapitalAllocationResult
from trading_lab.meta.change_log import ChangeLog, ChangeLogRecord
from trading_lab.meta.performance_feedback import PerformanceFeedback
from trading_lab.meta.sandbox import SandboxResult, SyntaxSandbox
from trading_lab.meta.sweeper import StrategySweeper, SweepResult
from trading_lab.meta.variant_generator import StrategyVariant, StrategyVariantGenerator
from trading_lab.meta.variant_validator import VariantValidationResult, VariantValidator
from trading_lab.meta.watchdog import AdoptionWatchdog, WatchdogCheckResult

__all__ = [
    "ABHarness",
    "ABResult",
    "AdoptionManager",
    "AdoptionResult",
    "AdoptionWatchdog",
    "CapitalAllocator",
    "CapitalAllocationResult",
    "ChangeLog",
    "ChangeLogRecord",
    "PerformanceFeedback",
    "SandboxResult",
    "StrategySweeper",
    "SweepResult",
    "StrategyVariant",
    "StrategyVariantGenerator",
    "SyntaxSandbox",
    "VariantValidationResult",
    "VariantValidator",
    "WatchdogCheckResult",
]
