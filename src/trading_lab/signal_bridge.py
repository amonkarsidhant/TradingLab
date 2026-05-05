"""
Trade-to-round-trip bridge.

Converts entry+exit signal pairs into closed RoundTrip records,
persisted to SQLite so backtests and live trades feed the same Sharpe/win-rate engine.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from trading_lab.models import Signal, SignalAction
from trading_lab.round_trips import RoundTrip, RoundTripTracker


class SignalRoundTripBridge:
    """Bridge: turns executed signals into round trips and persists them."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._tracker = RoundTripTracker(db_path)
        self._open: dict[str, dict[str, Any]] = {}

    def on_signal(self, *, signal: Signal, price: float, dry_run: bool, regime: str = "") -> None:        """Called after a signal is executed (or backtested).

        On BUY: open a pending round-trip slot with regime context.
        On SELL: close the matching open trip and write to DB (with regime).
        """
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        key = signal.ticker
        if signal.action == SignalAction.BUY and not dry_run:
            self._open[key] = {
                "entry_price": price,
                "quantity": max(signal.suggested_quantity, 1.0),
                "strategy": signal.strategy,
                "date": ts,
                "position_id": f"{key}_{ts}",
                "regime": regime or getattr(signal, "regime", ""),
            }
        elif signal.action == SignalAction.SELL and key in self._open:
            entry = self._open.pop(key)
            qty = min(entry["quantity"], max(signal.suggested_quantity, 1.0))
            pnl = (price - entry["entry_price"]) * qty
            pnl_pct = (
                (price - entry["entry_price"]) / entry["entry_price"] * 100
                if entry["entry_price"] > 0
                else 0.0
            )
            days_held = 0
            trip = RoundTrip(
                ticker=key,
                position_id=entry["position_id"],
                entry_price=entry["entry_price"],
                exit_price=price,
                quantity=qty,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                days_held=days_held,
                strategy=entry["strategy"],
                regime=entry.get("regime", ""),
                entry_date=entry["date"],
                exit_date=ts,
            )
            self._tracker.record(trip)

    def get_stats(self, ticker: str = "") -> dict[str, Any]:
        """Proxy to RoundTripTracker.get_sharpe_for()."""
        return self._tracker.get_sharpe_for(ticker)

    def get_trips(self, ticker: str = "", limit: int = 50) -> list[RoundTrip]:
        """Proxy to RoundTripTracker.get_trips()."""
        return self._tracker.get_trips(ticker, limit)
