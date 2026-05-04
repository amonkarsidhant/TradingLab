"""Walk-forward backtest engine.

Simulates running a strategy day by day through historical prices.
No network. No broker. No order placement.  Deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trading_lab.backtest.metrics import compute_metrics
from trading_lab.models import Signal, SignalAction
from trading_lab.round_trips import RoundTrip, RoundTripTracker
from trading_lab.strategies.base import Strategy


@dataclass
class BacktestTrade:
    entry_date: str
    entry_price: float
    entry_signal: Signal
    exit_date: str | None = None
    exit_price: float | None = None
    exit_signal: Signal | None = None
    pnl: float | None = None
    return_pct: float | None = None


@dataclass
class BacktestResult:
    strategy_name: str
    ticker: str
    initial_capital: float
    final_equity: float
    signals: list[Signal] = field(default_factory=list)
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class BacktestEngine:
    """Walk-forward backtest: slide a window through prices, feed each window
    to a strategy, simulate entries and exits.

    Only long positions are supported in v1.  Commission and slippage
    are excluded — this is a signal-quality tool, not an execution
    simulator.
    """

    def __init__(
        self,
        strategy: Strategy,
        initial_capital: float = 10_000.0,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
    ) -> None:
        self._strategy = strategy
        self._initial_capital = initial_capital
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct

    def run(
        self,
        prices: list[float],
        dates: list[str] | None = None,
        ticker: str = "TEST",
    ) -> BacktestResult:
        if dates is None:
            dates = [str(i) for i in range(len(prices))]
        if len(prices) != len(dates):
            raise ValueError(
                f"prices ({len(prices)}) and dates ({len(dates)}) must have the same length"
            )

        cash = self._initial_capital
        position: float = 0.0  # number of shares held
        equity_curve: list[dict[str, Any]] = []
        signals: list[Signal] = []
        trades: list[BacktestTrade] = []
        open_trade: BacktestTrade | None = None
        tracker = RoundTripTracker(
            str(Path("./round_trips.sqlite3"))
        )

        # Find the minimum window size the strategy needs.
        # We determine this empirically: feed growing windows until the
        # strategy stops saying "not enough data".
        min_window = self._find_min_window(prices)
        if min_window > len(prices):
            min_window = len(prices)

        for i in range(min_window - 1, len(prices)):
            date = dates[i]
            price = prices[i]
            window = prices[: i + 1]

            signal = self._strategy.generate_signal(ticker=ticker, prices=window)
            signals.append(signal)

            # -- Entry -------------------------------------------------
            if signal.action == SignalAction.BUY and open_trade is None:
                entry_price = price * (1 + self._slippage_pct)
                qty = max(signal.suggested_quantity, 1.0)
                cost = qty * entry_price
                commission = cost * self._commission_pct
                if cost + commission > cash:
                    qty = cash / (entry_price * (1 + self._commission_pct))
                    cost = qty * entry_price
                    commission = cost * self._commission_pct
                cash -= (cost + commission)
                position = qty
                open_trade = BacktestTrade(
                    entry_date=date,
                    entry_price=entry_price,
                    entry_signal=signal,
                )

            # -- Exit --------------------------------------------------
            elif signal.action == SignalAction.SELL and open_trade is not None:
                exit_price = price * (1 - self._slippage_pct)
                gross = position * exit_price
                commission = gross * self._commission_pct
                cash += gross - commission
                pnl = (exit_price - open_trade.entry_price) * position
                open_trade.exit_date = date
                open_trade.exit_price = exit_price
                open_trade.exit_signal = signal
                open_trade.pnl = round(pnl - commission, 4)
                open_trade.return_pct = round(
                    (exit_price - open_trade.entry_price) / open_trade.entry_price * 100, 2
                )
                trades.append(open_trade)
                # -- Record to round-trip tracker BEFORE nulling out -----
                closed_trade = open_trade
                closed_qty = position
                position = 0.0
                open_trade = None
                if tracker is not None:
                    trip = RoundTrip(
                        ticker=ticker,
                        position_id=f"{ticker}_{closed_trade.entry_date}",
                        entry_price=closed_trade.entry_price,
                        exit_price=exit_price,
                        quantity=closed_qty,
                        pnl=round(closed_trade.pnl or 0, 2),
                        pnl_pct=round(closed_trade.return_pct or 0, 2),
                        days_held=0,
                        strategy=closed_trade.entry_signal.strategy,
                        entry_date=closed_trade.entry_date,
                        exit_date=date,
                    )
                    tracker.record(trip)

            # -- Mark-to-market equity ---------------------------------
            mtm = cash + (position * price)
            equity_curve.append({"date": date, "equity": round(mtm, 2)})

        # Close any open trade at the last price.
        if open_trade is not None:
            last_price = prices[-1]
            exit_price = last_price * (1 - self._slippage_pct)
            gross = position * exit_price
            commission = gross * self._commission_pct
            cash += gross - commission
            pnl = (exit_price - open_trade.entry_price) * position
            open_trade.exit_date = dates[-1]
            open_trade.exit_price = exit_price
            open_trade.pnl = round(pnl - commission, 4)
            open_trade.return_pct = round(
                (exit_price - open_trade.entry_price) / open_trade.entry_price * 100, 2
            )
            trades.append(open_trade)

        final_equity = equity_curve[-1]["equity"] if equity_curve else self._initial_capital

        trade_dicts = [
            {
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "return_pct": t.return_pct,
            }
            for t in trades
        ]
        metrics = compute_metrics(equity_curve, trade_dicts, self._initial_capital)

        return BacktestResult(
            strategy_name=self._strategy.name,
            ticker=ticker,
            initial_capital=self._initial_capital,
            final_equity=round(final_equity, 2),
            signals=signals,
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics,
        )

    def _find_min_window(self, prices: list[float]) -> int:
        """Smallest window size that produces a non-'not enough data' signal."""
        for n in range(2, len(prices) + 1):
            window = prices[:n]
            signal = self._strategy.generate_signal(ticker="PROBE", prices=window)
            if "not enough" not in signal.reason.lower():
                return n
        return len(prices)
