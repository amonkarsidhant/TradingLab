"""Strategy performance registry — tracks Sharpe/win-rate per regime, supports auto-selection."""
from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StrategyRegimeRecord:
    strategy_id: str
    regime: str
    sharpe: float
    win_rate: float
    avg_hold_days: float
    trade_count: int
    updated_at: str


class StrategyPerformanceRegistry:
    """SQLite-backed registry for strategy performance by market regime."""

    def __init__(self, db_path: str = "./trading_lab.sqlite3") -> None:
        self.db_path = db_path
        self._init_schema()

    def _connection(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS strategy_regime_performance (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id     TEXT    NOT NULL,
                    regime          TEXT    NOT NULL,
                    sharpe          REAL,
                    win_rate        REAL,
                    avg_hold_days   REAL,
                    trade_count     INTEGER DEFAULT 0,
                    updated_at      TEXT    NOT NULL,
                    UNIQUE(strategy_id, regime)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cycles (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    regime          TEXT    NOT NULL,
                    confidence      REAL    NOT NULL,
                    strategy        TEXT    NOT NULL,
                    signals_count   INTEGER,
                    executed_count  INTEGER,
                    pnl_after_cycle REAL,
                    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_strategy_regime
                    ON strategy_regime_performance(strategy_id, regime)"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_cycles_timestamp
                    ON cycles(timestamp)"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS ab_results (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    baseline        TEXT    NOT NULL,
                    variant         TEXT    NOT NULL,
                    ticker          TEXT    NOT NULL,
                    baseline_trades INTEGER,
                    variant_trades  INTEGER,
                    sharpe_diff     REAL,
                    win_rate_diff   REAL,
                    t_stat          REAL,
                    p_value         REAL,
                    verdict         TEXT    NOT NULL,
                    reason          TEXT,
                    adopted         INTEGER DEFAULT 0,
                    UNIQUE(baseline, variant, ticker, timestamp)
                )"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_ab_results_variant
                    ON ab_results(baseline, variant)"""
            )

    # ── Write ──────────────────────────────────────────────────────────────────

    def record_performance(
        self,
        strategy_id: str,
        regime: str,
        pnl_series: list[float],
        hold_days: list[float] | None = None,
    ) -> None:
        """Compute and store/update performance for a strategy + regime."""
        from datetime import datetime, timezone

        updated_at = datetime.now(timezone.utc).isoformat()
        sharpe = self._compute_sharpe(pnl_series)
        win_rate = self._compute_win_rate(pnl_series)
        avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0.0
        n = len(pnl_series)

        with self._connection() as conn:
            existing = conn.execute(
                "SELECT trade_count FROM strategy_regime_performance "
                "WHERE strategy_id = ? AND regime = ?",
                (strategy_id, regime),
            ).fetchone()

            if existing:
                old_n = existing[0] or 0
                conn.execute(
                    """UPDATE strategy_regime_performance SET
                        sharpe = ?,
                        win_rate = ?,
                        avg_hold_days = ?,
                        trade_count = trade_count + ?,
                        updated_at = ?
                     WHERE strategy_id = ? AND regime = ?""",
                    (sharpe, win_rate, avg_hold, n, updated_at, strategy_id, regime),
                )
            else:
                conn.execute(
                    """INSERT INTO strategy_regime_performance
                        (strategy_id, regime, sharpe, win_rate, avg_hold_days, trade_count, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (strategy_id, regime, sharpe, win_rate, avg_hold, n, updated_at),
                )

    def log_cycle(
        self,
        timestamp: str,
        regime: str,
        confidence: float,
        strategy: str,
        signals_count: int = 0,
        executed_count: int = 0,
        pnl_after_cycle: Optional[float] = None,
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO cycles
                    (timestamp, regime, confidence, strategy, signals_count, executed_count, pnl_after_cycle)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (timestamp, regime, confidence, strategy, signals_count, executed_count, pnl_after_cycle),
            )

    def save_ab_result(
        self,
        *,
        baseline: str,
        variant: str,
        ticker: str,
        baseline_trades: int,
        variant_trades: int,
        sharpe_diff: float,
        win_rate_diff: float,
        t_stat: float | None,
        p_value: float | None,
        verdict: str,
        reason: str,
        adopted: bool = False,
    ) -> None:
        """Persist an A/B comparison result."""
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO ab_results
                    (timestamp, baseline, variant, ticker, baseline_trades, variant_trades,
                     sharpe_diff, win_rate_diff, t_stat, p_value, verdict, reason, adopted)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, baseline, variant, ticker, baseline_trades, variant_trades,
                 sharpe_diff, win_rate_diff, t_stat, p_value, verdict, reason, int(adopted)),
            )

    def get_ab_results(
        self,
        baseline: str = "",
        variant: str = "",
        adopted_only: bool = False,
        limit: int = 100,
    ) -> list[dict]:
        """Query persisted A/B results."""
        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            conditions = ["1=1"]
            params: list = []
            if baseline:
                conditions.append("baseline = ?")
                params.append(baseline)
            if variant:
                conditions.append("variant = ?")
                params.append(variant)
            if adopted_only:
                conditions.append("adopted = 1")
            sql = f"SELECT * FROM ab_results WHERE {' AND '.join(conditions)} ORDER BY timestamp DESC LIMIT {limit}"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows] if rows else []

    # ── Read ───────────────────────────────────────────────────────────────────

    def best_for_regime(self, regime: str, min_trades: int = 5) -> Optional[str]:
        """Return the best strategy_id for a given regime, or None."""
        with self._connection() as conn:
            row = conn.execute(
                """SELECT strategy_id FROM strategy_regime_performance
                    WHERE regime = ? AND trade_count >= ?
                    ORDER BY sharpe DESC LIMIT 1""",
                (regime, min_trades),
            ).fetchone()
            return row[0] if row else None

    def all_for_regime(self, regime: str) -> list[dict]:
        """Return all strategies ranked by Sharpe for a regime."""
        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM strategy_regime_performance
                    WHERE regime = ?
                    ORDER BY sharpe DESC""",
                (regime,),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_for(self, strategy_id: str, regime: str) -> Optional[StrategyRegimeRecord]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM strategy_regime_performance WHERE strategy_id = ? AND regime = ?",
                (strategy_id, regime),
            ).fetchone()
            if not row:
                return None
            # row_factory is not set by default, use index access
            return StrategyRegimeRecord(
                strategy_id=row[1],
                regime=row[2],
                sharpe=row[3],
                win_rate=row[4],
                avg_hold_days=row[5],
                trade_count=row[6],
                updated_at=row[7],
            )

    # ── Stats ────────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_sharpe(returns: list[float], risk_free_rate: float = 0.04) -> float:
        n = len(returns)
        if n < 2:
            return 0.0
        mean_ret = sum(returns) / n
        variance = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else 0.0
        if std == 0:
            return 0.0
        return (mean_ret - risk_free_rate / 252) / std * (252 ** 0.5)

    @staticmethod
    def _compute_win_rate(returns: list[float]) -> float:
        if not returns:
            return 0.0
        wins = sum(1 for r in returns if r > 0)
        return wins / len(returns)
