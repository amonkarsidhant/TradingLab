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
                    approval_reason TEXT    NOT NULL
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
                    suggested_qty, dry_run, approved, approval_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                ),
            )
