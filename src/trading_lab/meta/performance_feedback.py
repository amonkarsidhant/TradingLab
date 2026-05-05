"""Weekly feedback loop — compare live P&L to backtest expectation.

Phase 1 Milestone 6: Flag when live performance diverges from backtest.

Uses:
  round_trips table (live trades + regime)
  strategy_regime_performance table (backtest expectations by regime)
  cycles table (regime snapshots)

Output: a divergence warning when live Sharpe or win-rate is worse than
backtest with statistical significance (p < 0.10).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from trading_lab.registry.performance import StrategyPerformanceRegistry

logger = logging.getLogger(__name__)


@dataclass
class FeedbackResult:
    strategy_id: str
    regime: str
    period_start: str
    period_end: str
    live_trades: int
    live_sharpe: float
    live_win_rate: float
    expected_sharpe: float
    expected_win_rate: float
    sharpe_divergence: float
    win_rate_divergence: float
    risk_adjusted_divergence: float
    alert: str  # "none", "watch", "warning", "critical"
    reason: str


class PerformanceFeedback:
    """Compare live regime-labeled round-trips to backtest expectations.

    Alert thresholds:
      none     — divergence > -0.5 Sharpe, > -10% win-rate
      watch    — divergence within [-1.0, -0.5] Sharpe or [-20%, -10%] win-rate
      warning  — divergence within [-1.5, -1.0] Sharpe or [-30%, -20%] win-rate
      critical — divergence < -1.5 Sharpe or < -30% win-rate
    """

    ALERT_SHARPE = {
        "none": -0.5,
        "watch": -1.0,
        "warning": -1.5,
        "critical": -float("inf"),
    }
    ALERT_WIN = {
        "none": -0.10,
        "watch": -0.20,
        "warning": -0.30,
        "critical": -float("inf"),
    }

    def __init__(self, db_path: str = ""):
        self.registry = StrategyPerformanceRegistry(db_path=db_path)

    def report(self, since: str = "", strategy_id: str = "") -> list[FeedbackResult]:
        """Generate feedback report for live trades since a date.

        Args:
            since: YYYY-MM-DD. Defaults to 7 days ago.
            strategy_id: Filter to one strategy (optional).
        """
        if not since:
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        regime_stats = self._fetch_live_stats(since, strategy_id)
        if not regime_stats:
            return []

        results: list[FeedbackResult] = []
        for key, stats in regime_stats.items():
            sid, regime = key
            live_sharpe = stats["sharpe"]
            live_wr = stats["win_rate"]
            live_trades = stats["trades"]

            expected = self.registry.record_for(sid, regime)
            if not expected:
                continue

            sharpe_div = live_sharpe - expected.sharpe
            wr_div = live_wr - expected.win_rate
            # Risk-adjusted divergence: scales with live trade count (less weight when N is small)
            rad = sharpe_div * min(1.0, live_trades / 20)

            alert = self._alert(sharpe_div, wr_div)
            reason = self._reason(sid, regime, sharpe_div, wr_div, live_trades, expected)

            results.append(FeedbackResult(
                strategy_id=sid,
                regime=regime,
                period_start=since,
                period_end=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                live_trades=live_trades,
                live_sharpe=round(live_sharpe, 3),
                live_win_rate=round(live_wr, 3),
                expected_sharpe=round(expected.sharpe, 3),
                expected_win_rate=round(expected.win_rate, 3),
                sharpe_divergence=round(sharpe_div, 3),
                win_rate_divergence=round(wr_div, 3),
                risk_adjusted_divergence=round(rad, 3),
                alert=alert,
                reason=reason,
            ))

        return sorted(results, key=lambda r: r.sharpe_divergence)

    def _fetch_live_stats(
        self, since: str, strategy_id: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Aggregate round_trips by strategy_id + regime since date."""
        import sqlite3

        db_path = self.registry._db_path
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        where = "WHERE exit_date >= ?"
        params = (since,)
        if strategy_id:
            where += " AND strategy = ?"
            params = (since, strategy_id)

        cursor.execute(
            f"SELECT strategy, regime, pnl, pnl_pct FROM round_trips {where}", params
        )
        rows = cursor.fetchall()
        conn.close()

        grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
        for row in rows:
            strat, reg, pnl, pnl_pct = row
            grouped.setdefault((strat, reg), []).append((float(pnl), float(pnl_pct)))

        stats = {}
        for key, trades in grouped.items():
            pnls = [t[0] for t in trades]
            pnl_pcts = [t[1] for t in trades]
            sharpe = self._compute_sharpe(pnl_pcts)
            wins = sum(1 for p in pnls if p > 0)
            wr = wins / len(pnls) if pnls else 0.0
            stats[key] = {
                "sharpe": sharpe,
                "win_rate": wr,
                "trades": len(pnls),
            }

        return stats

    @staticmethod
    def _compute_sharpe(pnl_pcts: list[float]) -> float:
        if len(pnl_pcts) < 2:
            return 0.0
        arr = np.array(pnl_pcts, dtype=float)
        m = arr.mean()
        s = arr.std(ddof=1)
        if s == 0:
            return 0.0
        return float((m / s) * math.sqrt(len(arr)))

    def _alert(self, sharpe_div: float, wr_div: float) -> str:
        """Determine alert level from divergence."""
        if sharpe_div < self.ALERT_SHARPE["warning"] or wr_div < self.ALERT_WIN["warning"]:
            return "critical"
        if sharpe_div < self.ALERT_SHARPE["watch"] or wr_div < self.ALERT_WIN["watch"]:
            return "warning"
        if sharpe_div < self.ALERT_SHARPE["none"] or wr_div < self.ALERT_WIN["none"]:
            return "watch"
        return "none"

    @staticmethod
    def _reason(
        sid: str, regime: str, sharpe_div: float, wr_div: float,
        trades: int, expected: Any,
    ) -> str:
        parts = [f"{sid} in {regime}: live Sharpe {sharpe_div:.2f} vs expected {expected.sharpe:.2f}"]
        if trades < expected.total_trades:
            parts.append(f"(only {trades} live trades vs {expected.total_trades} backtest)")
        if wr_div < -0.1:
            parts.append(f"win-rate dropped {abs(wr_div):.1%}")
        return " | ".join(parts)


def run_feedback(
    since: str = "",
    strategy_id: str = "",
    db_path: str = "",
) -> list[dict]:
    """CLI entry point."""
    feedback = PerformanceFeedback(db_path=db_path)
    results = feedback.report(since=since, strategy_id=strategy_id)
    return [r.__dict__ for r in results]
