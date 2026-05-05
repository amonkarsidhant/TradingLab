"""Capital Allocator — regime-aware position sizing.

Phase 1 Milestone 3: Compute position sizes weighted by regime-specific
strategy confidence, bounded by hard safety rails.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.risk import RiskPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Allocation:
    ticker: str
    target_value: float
    target_pct: float
    confidence: float
    regime: str
    strategy: str
    reason: str


class CapitalAllocator:
    """Regime-aware position sizing.

    Hard rails (immutable):
    - Minimum 10% cash always
    - Maximum 20% per position
    - No more than 10 positions

    Soft rules (regime-aware):
    - Weight by strategy.regime Sharpe (normalized)
    - Higher Sharpe = larger size (up to 20%)
    - risk_off with Sharpe < 0 = reduce to 5%
    - trending with Sharpe > 1.0 = max 20%
    """

    MIN_CASH_PCT = 0.10
    MAX_POSITION_PCT = 0.20
    MAX_POSITIONS = 10

    # Regime-adjusted size multipliers (applied to base allocation)
    SHARPE_TO_SIZE = {
        (float("-inf"), 0.0): 0.05,
        (0.0, 0.5): 0.08,
        (0.5, 1.0): 0.12,
        (1.0, 1.5): 0.16,
        (1.5, float("inf")): 0.20,
    }

    def __init__(
        self,
        registry: StrategyPerformanceRegistry | None = None,
        risk_policy: RiskPolicy | None = None,
    ):
        self.registry = registry or StrategyPerformanceRegistry()
        self.risk_policy = risk_policy

    def allocate(
        self,
        regime: str,
        strategy_id: str,
        total_equity: float,
        open_positions: int = 0,
        tickers: list[str] | None = None,
        current_cash: float | None = None,
    ) -> list[Allocation]:
        """Compute allocations for a set of tickers given regime + strategy.

        Returns a list of Allocation objects. Zero-allocation tickers are
        included if explicitly passed with reason = "skip: reason".
        """
        tickers = tickers or ["SPY"]
        cash = current_cash or (total_equity * self.MIN_CASH_PCT)
        cash_pct = cash / total_equity if total_equity > 0 else 0.0
        available_cash = max(0, cash - total_equity * self.MIN_CASH_PCT)

        # Get strategy's Sharpe for this regime
        record = self.registry.record_for(strategy_id, regime)
        sharpe = record.sharpe if record else 0.0

        # Map Sharpe to base size percentage
        base_pct = self._sharpe_to_size(sharpe)

        # Adjust for number of open positions (fewer open = more per position)
        slots_left = max(0, self.MAX_POSITIONS - open_positions)
        if slots_left <= 0:
            logger.warning("Max positions reached (%d). No new allocations.", self.MAX_POSITIONS)
            return [
                Allocation(
                    ticker=t, target_value=0.0, target_pct=0.0, confidence=0.0,
                    regime=regime, strategy=strategy_id, reason="skip: max_positions_reached"
                )
                for t in tickers
            ]

        # Scale down if too many tickers
        per_ticker_pct = min(base_pct, self.MAX_POSITION_PCT)
        num_tickers = len(tickers)
        if num_tickers > slots_left:
            per_ticker_pct = min(per_ticker_pct, self.MAX_POSITION_PCT * slots_left / num_tickers)

        # Adjust available cash
        raw_total = sum(per_ticker_pct for _ in tickers)
        if raw_total > (1.0 - self.MIN_CASH_PCT - cash_pct):
            scale = (1.0 - self.MIN_CASH_PCT - cash_pct) / max(raw_total, 0.001)
            per_ticker_pct *= scale

        allocations: list[Allocation] = []
        for ticker in tickers:
            target_value = total_equity * per_ticker_pct
            target_pct = per_ticker_pct

            if target_value <= 0:
                reason = "skip: zero_target"
            elif available_cash < target_value:
                reason = f"skip: insufficient_cash (need {target_value:.0f}, have {available_cash:.0f})"
                target_value = 0.0
                target_pct = 0.0
            else:
                reason = f"allocate: sharpe={sharpe:.2f}, base_pct={base_pct:.2%}, scaled={per_ticker_pct:.2%}"

            allocations.append(Allocation(
                ticker=ticker,
                target_value=round(target_value, 2),
                target_pct=round(target_pct, 4),
                confidence=round(self._sharpe_to_confidence(sharpe), 4),
                regime=regime,
                strategy=strategy_id,
                reason=reason,
            ))

        return allocations

    def allocate_single(
        self,
        regime: str,
        strategy_id: str,
        total_equity: float,
        open_positions: int = 0,
        current_cash: float | None = None,
    ) -> Allocation:
        """Convenience: allocate for a single-best ticker."""
        allocs = self.allocate(regime, strategy_id, total_equity, open_positions, ["BEST"], current_cash)
        return allocs[0]

    @staticmethod
    def _sharpe_to_size(sharpe: float) -> float:
        """Map Sharpe to position size %."""
        for lo, hi in [(float("-inf"), 0.0), (0.0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, float("inf"))]:
            if lo <= sharpe < hi or (sharpe >= lo and hi == float("inf")):
                return {
                    (float("-inf"), 0.0): 0.05,
                    (0.0, 0.5): 0.08,
                    (0.5, 1.0): 0.12,
                    (1.0, 1.5): 0.16,
                    (1.5, float("inf")): 0.20,
                }[(lo, hi)]
        return 0.10

    @staticmethod
    def _sharpe_to_confidence(sharpe: float) -> float:
        """Convert Sharpe to a [0,1] confidence score."""
        return min(0.95, max(0.05, sharpe / 2.0))
