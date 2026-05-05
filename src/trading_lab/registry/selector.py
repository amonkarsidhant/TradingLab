"""Auto-strategy selector — pick best strategy for current regime, with confidence fallback."""
from __future__ import annotations

import logging
from typing import Optional

from trading_lab.regime.detector import RegimeState
from trading_lab.registry.performance import StrategyPerformanceRegistry

logger = logging.getLogger(__name__)


class StrategySelector:
    """Selects the best strategy for a given regime, falling back to default if confidence is low.
    Phase 1 M4: adds PAUSE_THRESHOLD for autonomous cycle halt."""

    DEFAULT_STRATEGY = "simple_momentum"
    CONFIDENCE_THRESHOLD = 0.60  # for strategy selection
    PAUSE_THRESHOLD = 0.40         # Phase 1 M4: halt new entries below this
    MIN_TRADES = 5

    def __init__(
        self,
        registry: Optional[StrategyPerformanceRegistry] = None,
        default: str = "",
        confidence_threshold: float = 0.0,
        min_trades: int = 0,
    ) -> None:
        self.registry = registry or StrategyPerformanceRegistry()
        self.default = default or self.DEFAULT_STRATEGY
        self.confidence_threshold = confidence_threshold or self.CONFIDENCE_THRESHOLD
        self.min_trades = min_trades or self.MIN_TRADES

    def select(self, regime_state: RegimeState) -> tuple[str, float]:
        """Return (strategy_id, confidence) for the current regime."""
        regime = regime_state.regime
        confidence = regime_state.confidence

        if confidence < self.confidence_threshold:
            logger.info(
                "Regime confidence %.2f below threshold %.2f — using default %s",
                confidence, self.confidence_threshold, self.default,
            )
            return self.default, 0.0

        best = self.registry.best_for_regime(regime.value, min_trades=self.min_trades)
        if best:
            logger.info(
                "Selected strategy %s for regime %s (confidence %.2f)",
                best, regime.value, confidence,
            )
            return best, confidence

        logger.info(
            "No strategy with >= %d trades for regime %s — using default %s",
            self.min_trades, regime.value, self.default,
        )
        return self.default, 0.0

    def all_ranked(self, regime_state: RegimeState) -> list[dict]:
        """Return all strategies ranked by Sharpe for the current regime."""
        return self.registry.all_for_regime(regime_state.regime.value)
