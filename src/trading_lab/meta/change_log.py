"""Change Log — immutable audit trail of every strategy mutation.

Phase 2 Milestone 6: SQLite-backed strategy_change_log table.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChangeLogRecord:
    id: int
    timestamp: str
    strategy_id: str
    action: str
    reason: str
    baseline_hash: str | None
    variant_hash: str | None
    performance_before: float
    performance_after: float
    regime_at_change: str
    llm_prompt: str
    llm_response: str
    composite_score: float
    p_value: float | None
    adopted_by: str


class ChangeLog:
    """SQLite-backed audit log for strategy mutations."""

    def __init__(self, db_path: str = "./trading_lab.sqlite3") -> None:
        self.db_path = db_path
        self._init_schema()

    def _connection(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS strategy_change_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    strategy_id     TEXT    NOT NULL,
                    action          TEXT    NOT NULL,
                    reason          TEXT    NOT NULL,
                    baseline_hash   TEXT,
                    variant_hash    TEXT,
                    performance_before REAL,
                    performance_after  REAL,
                    regime_at_change   TEXT,
                    llm_prompt         TEXT,
                    llm_response       TEXT,
                    composite_score    REAL,
                    p_value            REAL,
                    adopted_by         TEXT DEFAULT 'auto'
                )"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_change_log_strategy
                    ON strategy_change_log(strategy_id, timestamp DESC)"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_change_log_action
                    ON strategy_change_log(action, timestamp DESC)"""
            )

    # ── Write ────────────────────────────────────────────────────────────────────

    def record(
        self,
        strategy_id: str,
        action: str,
        reason: str,
        baseline_hash: str | None = None,
        variant_hash: str | None = None,
        performance_before: float = 0.0,
        performance_after: float = 0.0,
        regime_at_change: str = "",
        llm_prompt: str = "",
        llm_response: str = "",
        composite_score: float = 0.0,
        p_value: float | None = None,
        adopted_by: str = "auto",
    ) -> int:
        """Insert a change record. Returns the new row id."""
        ts = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """INSERT INTO strategy_change_log
                    (timestamp, strategy_id, action, reason, baseline_hash, variant_hash,
                     performance_before, performance_after, regime_at_change,
                     llm_prompt, llm_response, composite_score, p_value, adopted_by)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, strategy_id, action, reason, baseline_hash, variant_hash,
                 performance_before, performance_after, regime_at_change,
                 llm_prompt, llm_response, composite_score, p_value, adopted_by),
            )
            return cursor.lastrowid or 0

    # ── Read ─────────────────────────────────────────────────────────────────────

    def list_changes(
        self,
        strategy_id: str = "",
        action: str = "",
        since: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """Query change log with optional filters."""
        with self._connection() as conn:
            conn.row_factory = sqlite3.Row
            conditions = ["1=1"]
            params: list[Any] = []
            if strategy_id:
                conditions.append("strategy_id = ?")
                params.append(strategy_id)
            if action:
                conditions.append("action = ?")
                params.append(action)
            if since:
                conditions.append("timestamp >= ?")
                params.append(since)
            sql = (
                f"SELECT * FROM strategy_change_log WHERE {' AND '.join(conditions)} "
                f"ORDER BY timestamp DESC LIMIT {limit}"
            )
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows] if rows else []

    def latest_for(self, strategy_id: str) -> dict | None:
        """Return the most recent change for a strategy."""
        rows = self.list_changes(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    def success_rate(self) -> float:
        """Percentage of adoptions that were NOT rolled back."""
        with self._connection() as conn:
            adopted = conn.execute(
                "SELECT COUNT(*) FROM strategy_change_log WHERE action = 'adopt'"
            ).fetchone()[0] or 0
            rollbacked = conn.execute(
                "SELECT COUNT(*) FROM strategy_change_log WHERE action = 'rollback'"
            ).fetchone()[0] or 0
            if adopted == 0:
                return 0.0
            return round((adopted - rollbacked) / adopted * 100, 1)

    def adoption_count(self, strategy_id: str = "") -> int:
        """Count of adoptions (total or per strategy)."""
        with self._connection() as conn:
            if strategy_id:
                row = conn.execute(
                    "SELECT COUNT(*) FROM strategy_change_log WHERE strategy_id = ? AND action = 'adopt'",
                    (strategy_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM strategy_change_log WHERE action = 'adopt'"
                ).fetchone()
            return row[0] if row else 0


def strategy_history(strategy_id: str = "", limit: int = 50) -> list[dict]:
    """CLI entry point. Returns list of dicts for JSON serialization."""
    log = ChangeLog()
    return log.list_changes(strategy_id=strategy_id, limit=limit)
