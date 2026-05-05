"""
SnapshotLogger — local SQLite persistence for API snapshots and signal journal.

Two tables:
  snapshots  — timestamped JSON blobs from API responses (account, positions, instruments)
  signals    — every signal produced by a strategy, with risk/approval outcome

This module has no network dependencies. It is safe to use in tests with a
tmp_path SQLite file.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from trading_lab.models import Signal


class SnapshotLogger:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at    TEXT    NOT NULL,
                    snapshot_type TEXT    NOT NULL,
                    data_json     TEXT    NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at      TEXT    NOT NULL,
                    strategy        TEXT    NOT NULL,
                    ticker          TEXT    NOT NULL,
                    action          TEXT    NOT NULL,
                    confidence      REAL    NOT NULL,
                    reason          TEXT    NOT NULL,
                    suggested_qty   REAL    NOT NULL,
                    dry_run         INTEGER NOT NULL,
                    approved        INTEGER NOT NULL,
                    approval_reason TEXT    NOT NULL,
                    regime          TEXT    DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watcher_events (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at    TEXT    NOT NULL,
                    ticker        TEXT    NOT NULL,
                    drawdown_pct  REAL    NOT NULL,
                    action_taken  TEXT    NOT NULL,
                    details       TEXT    DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watcher_state (
                    key         TEXT    PRIMARY KEY,
                    value       TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL
                )
            """)

    def save_snapshot(self, snapshot_type: str, data: Any) -> None:
        """Write an API response blob to the snapshots table."""
        created_at = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(data, default=str)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO snapshots (created_at, snapshot_type, data_json) VALUES (?, ?, ?)",
                (created_at, snapshot_type, data_json),
            )

    def save_signal(
        self,
        signal: Signal,
        *,
        dry_run: bool,
        approved: bool,
        approval_reason: str,
    ) -> None:
        """Write a generated signal and its risk outcome to the signals table."""
        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO signals
                   (created_at, strategy, ticker, action, confidence, reason,
                    suggested_qty, dry_run, approved, approval_reason, regime)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    created_at,
                    signal.strategy,
                    signal.ticker,
                    signal.action.value,
                    signal.confidence,
                    signal.reason,
                    signal.suggested_quantity,
                    int(dry_run),
                    int(approved),
                    approval_reason,
                    getattr(signal, "regime", "") or "",
                ),
            )

    def save_watcher_event(
        self, ticker: str, drawdown_pct: float, action_taken: str, details: str = ""
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO watcher_events (created_at, ticker, drawdown_pct, action_taken, details)
                   VALUES (?, ?, ?, ?, ?)""",
                (created_at, ticker, round(drawdown_pct, 4), action_taken, details),
            )

    def save_watcher_state(self, key: str, value: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO watcher_state (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, value, datetime.now(timezone.utc).isoformat()),
            )

    def get_watcher_state(self, key: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM watcher_state WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None

    def get_watcher_events(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM watcher_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_watcher_state(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM watcher_state").fetchall()
            return {row[0]: row[1] for row in rows}
