"""
Round-trip tracking for Sid Trading Lab.

Groups entry + exit trades into coherent round trips per position_id.
Inspired by go-trader's position_id grouping.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class RoundTrip:
    ticker: str
    position_id: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    days_held: int
    strategy: str
    entry_date: str
    exit_date: str
    id: int | None = None


class RoundTripTracker:
    """Tracks round trips from executed trades in the signals table."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS round_trips (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at      TEXT    NOT NULL,
                    closed_at       TEXT    NOT NULL,
                    ticker          TEXT    NOT NULL,
                    position_id     TEXT    NOT NULL,
                    entry_price     REAL    NOT NULL,
                    exit_price      REAL    NOT NULL,
                    quantity        REAL    NOT NULL,
                    pnl             REAL    NOT NULL,
                    pnl_pct         REAL    NOT NULL,
                    days_held       INTEGER NOT NULL,
                    strategy        TEXT    DEFAULT ''
                )
            """)

    def record(self, round_trip: RoundTrip) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO round_trips
                   (created_at, closed_at, ticker, position_id, entry_price,
                    exit_price, quantity, pnl, pnl_pct, days_held, strategy)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    round_trip.entry_date,
                    round_trip.exit_date,
                    round_trip.ticker,
                    round_trip.position_id,
                    round_trip.entry_price,
                    round_trip.exit_price,
                    round_trip.quantity,
                    round_trip.pnl,
                    round_trip.pnl_pct,
                    round_trip.days_held,
                    round_trip.strategy,
                ),
            )

    def get_trips(self, ticker: str = "", limit: int = 50) -> list[RoundTrip]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM round_trips"
            params: tuple = ()
            if ticker:
                sql += " WHERE ticker = ?"
                params = (ticker,)
            sql += " ORDER BY closed_at DESC LIMIT ?"
            params += (limit,)
            rows = conn.execute(sql, params).fetchall()
            return [
                RoundTrip(
                    ticker=r["ticker"],
                    position_id=r["position_id"],
                    entry_price=r["entry_price"],
                    exit_price=r["exit_price"],
                    quantity=r["quantity"],
                    pnl=r["pnl"],
                    pnl_pct=r["pnl_pct"],
                    days_held=r["days_held"],
                    strategy=r["strategy"],
                    entry_date=r["created_at"],
                    exit_date=r["closed_at"],
                )
                for r in rows
            ]

    def get_sharpe_for(self, ticker: str = "", risk_free_rate: float = 0.04) -> dict:
        """Compute Sharpe ratio from round-trip returns."""
        trips = self.get_trips(ticker=ticker)
        if len(trips) < 3:
            return {"trips": 0, "sharpe": None, "avg_pnl_pct": None, "win_rate": None}

        returns = [t.pnl_pct / 100 for t in trips]
        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1) if len(returns) > 1 else 0
        std = var ** 0.5
        sharpe = (mean_ret - risk_free_rate / 252) / std * (252 ** 0.5) if std > 0 else 0.0

        wins = sum(1 for t in trips if t.pnl > 0)
        return {
            "trips": len(trips),
            "sharpe": round(sharpe, 2),
            "avg_pnl_pct": round(sum(t.pnl_pct for t in trips) / len(trips), 2),
            "win_rate": round(wins / len(trips) * 100, 1),
        }
