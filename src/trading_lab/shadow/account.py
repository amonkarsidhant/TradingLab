"""Shadow account: compares mechanical strategy execution against
journaled signals to measure behavioral drift.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from trading_lab.backtest.engine import BacktestEngine, BacktestResult
from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy


@dataclass
class ShadowResult:
    strategy_name: str
    ticker: str
    from_date: str
    to_date: str
    generated_at: str

    # Shadow (mechanical backtest)
    shadow_trades: int
    shadow_final_equity: float
    shadow_return_pct: float
    shadow_sharpe: float | None

    # Journaled signals
    total_signals_journaled: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    signals_overridden: int  # HOLD signals where confidence > 0

    # Drift metrics
    adherence_pct: float | None  # % of trade signals that were actioned
    missed_entries: int  # BUY signals not followed by an entry
    extra_signals: int  # signals generated outside strategy logic
    overtrading_score: float  # 0-100; higher = more deviation from plan

    # Behavioral gap notes
    gap_notes: list[str] = field(default_factory=list)

    # Full backtest for reference
    backtest: BacktestResult | None = None


class ShadowAccount:
    """Compares a strategy backtest (shadow) against journaled signals (actual).

    The shadow is the strategy executed mechanically.  The actual is
    what you journaled — every HOLD-override, every missed entry,
    every discretionary deviation.

    Usage:
        sa = ShadowAccount(strategy, db_path="./trading_lab.sqlite3")
        result = sa.compare(ticker="AAPL_US_EQ", prices=prices,
                            from_date="2026-04-01", to_date="2026-04-29")
    """

    def __init__(self, strategy: Strategy, db_path: str) -> None:
        self._strategy = strategy
        self._db_path = db_path

    def compare(
        self,
        prices: list[float],
        dates: list[str] | None = None,
        ticker: str = "TEST",
        from_date: str = "",
        to_date: str = "",
    ) -> ShadowResult:
        # -- Shadow: mechanical backtest ---------------------------------
        engine = BacktestEngine(self._strategy)
        bt = engine.run(prices=prices, dates=dates, ticker=ticker)
        bt_metrics = bt.metrics

        # -- Actual: journaled signals -----------------------------------
        journaled = self._fetch_signals(ticker, from_date, to_date)

        total = len(journaled)
        buys = sum(1 for s in journaled if s["action"] == "BUY")
        sells = sum(1 for s in journaled if s["action"] == "SELL")
        holds = sum(1 for s in journaled if s["action"] == "HOLD")

        # Overrides: HOLD signals where strategy confidence was non-zero
        # (meaning the strategy thought about it but you chose not to act).
        overridden = sum(
            1 for s in journaled
            if s["action"] == "HOLD" and s.get("confidence", 0) > 0
        )

        # -- Drift metrics -----------------------------------------------
        trade_signals = buys + sells
        shadow_trades = bt_metrics.get("total_trades", 0)

        # Adherence: of the journaled trade signals, how many became actual
        # trades?  We approximate this by comparing journaled trade signals
        # against the backtest trade count.
        adherence = None
        if trade_signals > 0:
            # If journaled trade signals exist, adherence = how many would
            # have been profitable to follow (shadow trades vs total signals).
            adherence = min(100.0, (shadow_trades / max(trade_signals, 1)) * 100)

        # Missed entries: BUY signals in journal that are fewer than
        # shadow BUY count (the strategy wanted more entries than you logged).
        bt_buys = sum(1 for s in bt.signals if s.action == SignalAction.BUY)
        missed = max(0, bt_buys - buys)

        # Extra signals: signals in journal beyond what strategy generates.
        # A rough measure of overtrading / noise.
        extra = max(0, total - len(bt.signals))

        # Overtrading score: composite 0-100.
        ot_score = _overtrading_score(
            journaled_total=total,
            backtest_total=len(bt.signals),
            extra=extra,
            overridden=overridden,
        )

        # -- Gap notes ---------------------------------------------------
        gap_notes: list[str] = []
        if overridden > 0:
            gap_notes.append(
                f"{overridden} HOLD-override(s) detected — strategy confidence was "
                f"non-zero but no action was taken."
            )
        if missed > 0:
            gap_notes.append(
                f"{missed} potential missed entr{'y' if missed == 1 else 'ies'} — "
                f"the strategy signaled BUY more times than were journaled."
            )
        if extra > 0:
            gap_notes.append(
                f"{extra} extra signal(s) in journal beyond what strict "
                f"strategy-following would produce."
            )
        if shadow_trades > 0 and trade_signals == 0:
            gap_notes.append(
                "Strategy produced trade signals in backtest but none were "
                "journaled — possible review gap."
            )
        if adherence is not None and adherence < 50:
            gap_notes.append(
                f"Low signal adherence ({adherence:.0f}%) — significant divergence "
                f"between what the strategy recommended and what was acted on."
            )
        if not gap_notes:
            gap_notes.append("No significant behavioral gaps detected.")

        return ShadowResult(
            strategy_name=self._strategy.name,
            ticker=ticker,
            from_date=from_date or (dates[0] if dates else ""),
            to_date=to_date or (dates[-1] if dates else ""),
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            shadow_trades=shadow_trades,
            shadow_final_equity=bt.final_equity,
            shadow_return_pct=bt_metrics.get("total_return_pct", 0.0),
            shadow_sharpe=bt_metrics.get("sharpe_ratio"),
            total_signals_journaled=total,
            buy_signals=buys,
            sell_signals=sells,
            hold_signals=holds,
            signals_overridden=overridden,
            adherence_pct=round(adherence, 1) if adherence is not None else None,
            missed_entries=missed,
            extra_signals=extra,
            overtrading_score=round(ot_score, 1),
            gap_notes=gap_notes,
            backtest=bt,
        )

    def _fetch_signals(
        self, ticker: str, from_date: str, to_date: str
    ) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM signals
                       WHERE ticker = ?
                         AND (? = '' OR date(created_at) >= ?)
                         AND (? = '' OR date(created_at) <= ?)
                       ORDER BY created_at ASC""",
                    (ticker, from_date, from_date, to_date, to_date),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []


def _overtrading_score(
    journaled_total: int,
    backtest_total: int,
    extra: int,
    overridden: int,
) -> float:
    """0 = perfectly follows strategy.  100 = total chaos."""
    if backtest_total == 0:
        return 100.0 if journaled_total > 0 else 0.0

    ratio = journaled_total / backtest_total
    if ratio <= 1:
        # Fewer signals than strategy → maybe under-trading.
        base = (1 - ratio) * 30  # max 30 for under-trading
    else:
        # More signals than strategy → overtrading.
        base = min(50, (ratio - 1) * 50)  # up to 50 for over-trading

    # Overrides add penalty.
    override_penalty = min(30, overridden * 5)

    # Extra signals add penalty.
    extra_penalty = min(20, extra * 3)

    return min(100.0, base + override_penalty + extra_penalty)
