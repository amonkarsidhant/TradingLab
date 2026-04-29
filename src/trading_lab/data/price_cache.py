"""
SQLite price cache for OHLCV market data.

Stores daily OHLCV bars keyed by (ticker, date) so repeated queries
never hit the network.  Used transparently by YFinanceProvider.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


class SqlitePriceCache:
    """Stores and retrieves daily OHLCV bars in a local SQLite database."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_cache (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (ticker, date)
                )
            """)

    def get(self, ticker: str, from_date: str, to_date: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM price_cache
                   WHERE ticker = ? AND date >= ? AND date <= ?
                   ORDER BY date ASC""",
                (ticker, from_date, to_date),
            ).fetchall()
            return [dict(r) for r in rows]

    def put(self, ticker: str, bars: list[dict[str, Any]]) -> None:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO price_cache
                   (ticker, date, open, high, low, close, volume, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (ticker, b["date"], b["open"], b["high"], b["low"],
                     b["close"], b.get("volume", 0), now_iso)
                    for b in bars
                ],
            )

    def last_date(self, ticker: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM price_cache WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            return row[0] if row and row[0] else None
