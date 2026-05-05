"""Adoption Watchdog — 48h observation window after strategy adoption.

Phase 2 Milestone 5: Monitor live P&L post-adoption, trigger rollback if
performance degrades below backtest expectation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trading_lab.meta.adoption_manager import AdoptionManager
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.round_trips import RoundTripTracker

logger = logging.getLogger(__name__)


@dataclass
class WatchdogCheckResult:
    variant_id: str
    status: str  # 'observing', 'confirmed', 'rollback_triggered', 'insufficient_data'
    live_sharpe: float
    expected_sharpe: float
    live_drawdown: float
    expected_drawdown: float
    hours_elapsed: float
    reason: str


class AdoptionWatchdog:
    """Monitors a strategy variant for 48h after adoption."""

    # Rollback triggers
    SHARPE_DEGRADATION = 0.20   # live < expected - 0.20
    DRAWDOWN_TOLERANCE = 3.0      # live > expected + 3.0%
    MIN_HOURS = 48.0              # must wait 48h before rollback decision

    def __init__(self) -> None:
        self._registry = StrategyPerformanceRegistry()
        self._tracker = RoundTripTracker()

    # ── Public API ──────────────────────────────────────────────────────────────

    def check(
        self,
        variant_id: str,
        baseline_id: str,
        adoption_time: str | None = None,
    ) -> WatchdogCheckResult:
        """Check if variant should be rolled back.

        If adoption_time is None, queries the latest adoption from strategy_change_log.
        """
        if adoption_time is None:
            adoption_time = self._latest_adoption_time(variant_id)

        if not adoption_time:
            return WatchdogCheckResult(
                variant_id=variant_id,
                status="insufficient_data",
                live_sharpe=0.0,
                expected_sharpe=0.0,
                live_drawdown=0.0,
                expected_drawdown=0.0,
                hours_elapsed=0.0,
                reason="No adoption record found",
            )

        adopted_dt = datetime.fromisoformat(adoption_time)
        now = datetime.now(timezone.utc)
        hours_elapsed = (now - adopted_dt).total_seconds() / 3600

        if hours_elapsed < self.MIN_HOURS:
            return WatchdogCheckResult(
                variant_id=variant_id,
                status="observing",
                live_sharpe=0.0,
                expected_sharpe=0.0,
                live_drawdown=0.0,
                expected_drawdown=0.0,
                hours_elapsed=round(hours_elapsed, 1),
                reason=f"Only {hours_elapsed:.1f}h elapsed (need {self.MIN_HOURS}h)",
            )

        # Query live performance
        live = self._query_live_performance(variant_id, adoption_time)
        expected = self._query_expected_performance(variant_id)

        # Rollback checks
        reasons: list[str] = []
        if live.sharpe < expected.sharpe - self.SHARPE_DEGRADATION:
            reasons.append(
                f"Sharpe degraded: {live.sharpe:.2f} < {expected.sharpe:.2f} - {self.SHARPE_DEGRADATION}"
            )
        if live.max_drawdown > expected.max_drawdown + self.DRAWDOWN_TOLERANCE:
            reasons.append(
                f"Drawdown exceeded: {live.max_drawdown:.1f}% > {expected.max_drawdown:.1f}% + {self.DRAWDOWN_TOLERANCE}%"
            )

        if reasons:
            # Trigger rollback
            manager = AdoptionManager()
            rollback_result = manager.rollback(variant_id, baseline_id, reason="; ".join(reasons))
            if rollback_result.success:
                return WatchdogCheckResult(
                    variant_id=variant_id,
                    status="rollback_triggered",
                    live_sharpe=live.sharpe,
                    expected_sharpe=expected.sharpe,
                    live_drawdown=live.max_drawdown,
                    expected_drawdown=expected.max_drawdown,
                    hours_elapsed=round(hours_elapsed, 1),
                    reason="; ".join(reasons),
                )
            else:
                return WatchdogCheckResult(
                    variant_id=variant_id,
                    status="rollback_failed",
                    live_sharpe=live.sharpe,
                    expected_sharpe=expected.sharpe,
                    live_drawdown=live.max_drawdown,
                    expected_drawdown=expected.max_drawdown,
                    hours_elapsed=round(hours_elapsed, 1),
                    reason=f"Rollback failed: {rollback_result.error}",
                )

        return WatchdogCheckResult(
            variant_id=variant_id,
            status="confirmed",
            live_sharpe=live.sharpe,
            expected_sharpe=expected.sharpe,
            live_drawdown=live.max_drawdown,
            expected_drawdown=expected.max_drawdown,
            hours_elapsed=round(hours_elapsed, 1),
            reason="Performance within expected bounds",
        )

    # ── Internal ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _latest_adoption_time(variant_id: str) -> str | None:
        """Query strategy_change_log for latest adoption timestamp."""
        from trading_lab.meta.change_log import ChangeLog
        latest = ChangeLog().latest_for(variant_id)
        return latest.get("timestamp") if latest else None

    def _query_live_performance(self, variant_id: str, since: str) -> "_Perf":
        """Compute Sharpe and max drawdown from round_trips since adoption."""
        # RoundTripTracker doesn't have a "query by strategy + date" method.
        # We load all and filter manually.
        all_trips = self._tracker.load_all()
        trips = [
            t for t in all_trips
            if getattr(t, "strategy", "") == variant_id and getattr(t, "entry_date", "") >= since
        ]
        if not trips:
            return _Perf(sharpe=0.0, max_drawdown=0.0)

        returns = [t.pnl_pct / 100 for t in trips if hasattr(t, "pnl_pct")]
        if len(returns) < 2:
            return _Perf(sharpe=0.0, max_drawdown=0.0)

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std = variance ** 0.5 if variance > 0 else 0.0
        sharpe = (mean_ret * 252) / (std * (252 ** 0.5)) if std > 0 else 0.0

        # Simple drawdown from cumulative equity
        equity = [10_000.0]
        for r in returns:
            equity.append(equity[-1] * (1 + r))
        peak = equity[0]
        max_dd = 0.0
        for e in equity:
            if e > peak:
                peak = e
            dd = (peak - e) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return _Perf(sharpe=round(sharpe, 3), max_drawdown=round(max_dd, 2))

    def _query_expected_performance(self, variant_id: str) -> "_Perf":
        """Get backtest-expected Sharpe from strategy_regime_performance."""
        rec = self._registry.record_for(variant_id, "neutral")
        if rec:
            return _Perf(sharpe=rec.sharpe, max_drawdown=0.0)
        return _Perf(sharpe=0.0, max_drawdown=0.0)


@dataclass
class _Perf:
    sharpe: float
    max_drawdown: float


def watchdog_check(variant_id: str, baseline_id: str = "simple_momentum") -> dict:
    """CLI entry point. Returns dict for JSON serialization."""
    w = AdoptionWatchdog()
    result = w.check(variant_id, baseline_id)
    return {
        "variant": result.variant_id,
        "status": result.status,
        "live_sharpe": result.live_sharpe,
        "expected_sharpe": result.expected_sharpe,
        "live_drawdown": result.live_drawdown,
        "expected_drawdown": result.expected_drawdown,
        "hours_elapsed": result.hours_elapsed,
        "reason": result.reason,
    }
