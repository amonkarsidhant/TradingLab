"""Strategy sweeper — runs walk-forward backtests per strategy per regime window.

Phase 1 Milestone 1: Seed the strategy_regime_performance table with
empirical Sharpe, win-rate, and max-drawdown for every strategy-regime pair.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.backtest.metrics import compute_metrics
from trading_lab.data.market_data import make_provider
from trading_lab.regime.detector import HistoricalRegimeDetector
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.strategies import get_strategy, list_strategies

logger = logging.getLogger(__name__)


@dataclass
class SweepResult:
    strategy_id: str
    regime: str
    ticker: str
    period_start: str
    period_end: str
    sharpe: float
    win_rate: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float | None
    total_trades: int
    avg_hold_days: int


class StrategySweeper:
    """Walk-forward backtest sweep across strategies and regime windows."""

    DEFAULT_TICKERS = [
        "SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
        "AMD", "INTC", "CRM", "ADBE", "UNH", "JNJ", "V", "MA",
    ]
    BREADTH_TICKERS = [
        "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "JPM",
        "JNJ", "V", "PG", "UNH", "HD", "MA", "BAC", "ABBV", "PFE", "KO",
        "PEP", "WMT", "MRK", "AVGO", "TMO", "COST", "DIS", "ABT", "ACN",
        "DHR", "VZ", "NKE", "TXN", "ADBE", "CRM", "CMCSA", "XOM", "CVX",
        "LLY", "NFLX", "AMD", "QCOM", "HON", "INTC", "AMGN", "SPGI", "IBM",
    ]

    # How many days a regime must persist to be considered stable
    MIN_REGIME_WINDOW_DAYS = 10

    def __init__(
        self,
        tickers: list[str] | None = None,
        lookback_days: int = 126,  # 6 months
        warmup_days: int = 60,
    ):
        self.tickers = tickers or self.DEFAULT_TICKERS
        self.lookback_days = lookback_days
        self.warmup_days = warmup_days

    # ── Public API ──────────────────────────────────────────────────────────────

    def sweep(
        self,
        save_registry: bool = True,
    ) -> list[SweepResult]:
        """Run a full sweep: for each strategy, for each regime window, backtest.

        Returns a list of results. If save_registry is True, writes to
        strategy_regime_performance table (via StrategyPerformanceRegistry).
        """
        all_results: list[SweepResult] = []
        strategies = list_strategies()

        if not strategies:
            logger.warning("No strategies registered. Nothing to sweep.")
            return []

        # Fetch ALL data once for full lookback period (historical regime detection)
        logger.info("Fetching historical data for regime detection (lookback=%d)...", self.lookback_days)
        hist_data = self._fetch_all_data(self.lookback_days + self.warmup_days)

        if not hist_data:
            logger.warning("Could not fetch historical data for sweeper")
            return []

        spy_prices = hist_data.get("SPY", [])
        if len(spy_prices) < self.lookback_days:
            logger.warning(
                "Not enough SPY data (%d bars, need %d)", len(spy_prices), self.lookback_days
            )
            return []

        # Detect regime windows from historical data
        regime_windows = self._detect_regime_windows(hist_data)

        logger.info(
            "Sweeping %d strategies across %d regime windows on %d tickers",
            len(strategies), len(regime_windows), len(self.tickers),
        )

        for strategy_id in strategies:
            for window in regime_windows:
                result = self._sweep_strategy_in_window(
                    strategy_id, window, hist_data
                )
                if result:
                    all_results.append(result)

        if save_registry:
            self._save_to_registry(all_results)

        return all_results

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _fetch_all_data(
        self, lookback: int,
    ) -> dict[str, list[float]]:
        """Fetch all tickers once — avoids N× repeated yfinance requests."""
        all_tickers = list(set(self.tickers + ["SPY", "VIXY", "XLY", "XLP"] + self.BREADTH_TICKERS))
        data: dict[str, list[float]] = {}

        for ticker in all_tickers:
            try:
                provider = make_provider(source="yfinance", ticker=ticker)
                prices = provider.get_prices(ticker=ticker, lookback=lookback)
                if prices:
                    data[ticker] = prices
            except Exception as exc:
                logger.debug("Fetch skip %s: %s", ticker, exc)
                continue

        return data

    def _detect_regime_windows(
        self,
        data: dict[str, list[float]],
    ) -> list[dict]:
        """Detect contiguous regime windows from historical data arrays."""
        det = HistoricalRegimeDetector()

        spy_closes = data.get("SPY", [])
        n = len(spy_closes)

        if n < self.lookback_days:
            return []

        # Build per-day regime labels
        dates = [str(i) for i in range(n)]
        regimes: list[str] = []

        for i in range(self.warmup_days, n):
            # Prepare data up to day i
            spy_slice = spy_closes[: i + 1]
            vixy_slice = data.get("VIXY", spy_closes[: i + 1])[: i + 1]
            xly_slice = data.get("XLY", spy_closes[: i + 1])[: i + 1]
            xlp_slice = data.get("XLP", spy_closes[: i + 1])[: i + 1]

            # Breadth data: slice per ticker to day i
            bread: dict[str, list[float]] = {}
            for sym in self.BREADTH_TICKERS:
                if sym in data:
                    bread[sym] = data[sym][: i + 1]

            try:
                state = det.detect_from_data(
                    spy_closes=spy_slice,
                    vixy_closes=vixy_slice,
                    xly_closes=xly_slice,
                    xlp_closes=xlp_slice,
                    breadth_data=bread,
                )
                regimes.append(state.regime.value)
            except Exception:
                regimes.append("neutral")

        # Detect contiguous windows
        windows: list[dict] = []
        current_regime = None
        window_start = None
        window_start_idx = None

        for i, regime in enumerate(regimes):
            idx = i + self.warmup_days  # actual index in full array
            if regime != current_regime:
                if current_regime and window_start_idx is not None:
                    window_len = idx - window_start_idx
                    if window_len >= self.MIN_REGIME_WINDOW_DAYS:
                        windows.append({
                            "regime": current_regime,
                            "start_idx": window_start_idx,
                            "end_idx": idx - 1,
                            "length": window_len,
                            "start": dates[window_start_idx],
                            "end": dates[idx - 1],
                        })
                current_regime = regime
                window_start_idx = idx

        # Close last window
        if current_regime and window_start_idx is not None:
            window_len = n - window_start_idx
            if window_len >= self.MIN_REGIME_WINDOW_DAYS:
                windows.append({
                    "regime": current_regime,
                    "start_idx": window_start_idx,
                    "end_idx": n - 1,
                    "length": window_len,
                    "start": dates[window_start_idx],
                    "end": dates[n - 1],
                })

        if not windows:
            # Fallback: entire period as one window
            windows.append({
                "regime": "neutral",
                "start_idx": n - self.lookback_days,
                "end_idx": n - 1,
                "length": self.lookback_days,
                "start": dates[n - self.lookback_days],
                "end": dates[n - 1],
            })

        return windows

    def _sweep_strategy_in_window(
        self,
        strategy_id: str,
        window: dict,
        data: dict[str, list[float]],
    ) -> SweepResult | None:
        """Backtest a single strategy within a single regime window across all tickers."""
        results_per_ticker: list[dict] = []

        for ticker in self.tickers:
            try:
                closes = data.get(ticker, [])
                # Slice to actual window boundaries
                start = max(0, window["start_idx"])
                end = min(len(closes), window["end_idx"] + 1)
                window_closes = closes[start:end]
                tick_dates = [str(i) for i in range(len(window_closes))]

                if len(window_closes) < 20:
                    continue

                strategy = get_strategy(strategy_id)
                engine = BacktestEngine(strategy, initial_capital=10_000.0)
                result = engine.run(prices=window_closes, dates=tick_dates, ticker=ticker)

                results_per_ticker.append({
                    "ticker": ticker,
                    "metrics": result.metrics,
                    "trades": result.trades,
                })

            except Exception as exc:
                logger.debug("Sweep skip %s/%s: %s", strategy_id, ticker, exc)
                continue

        if not results_per_ticker:
            return None

        # Aggregate across tickers
        wins = sum(
            1 for r in results_per_ticker
            for t in r["trades"] if getattr(t, "pnl", 0) > 0
        )
        total_trades = sum(len(r["trades"]) for r in results_per_ticker)
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        ticker_returns = [
            r["metrics"]["total_return_pct"] / 100
            for r in results_per_ticker
            if r["metrics"].get("total_return_pct") is not None
        ]

        if len(ticker_returns) >= 2:
            mean_ret = sum(ticker_returns) / len(ticker_returns)
            var = sum((r - mean_ret) ** 2 for r in ticker_returns) / (len(ticker_returns) - 1)
            std = np.sqrt(var) if var > 0 else 0.0
            sharpe = (mean_ret - 0.04 / 252) / std * np.sqrt(252) if std > 0 else 0.0
        else:
            sharpe = 0.0

        max_dd = max(
            (r["metrics"].get("max_drawdown_pct") or 0)
            for r in results_per_ticker
            if r["metrics"].get("max_drawdown_pct") is not None
        ) if results_per_ticker else 0.0

        total_pf = [
            r["metrics"].get("profit_factor")
            for r in results_per_ticker
            if r["metrics"].get("profit_factor") is not None
        ]
        avg_pf = sum(total_pf) / len(total_pf) if total_pf else None

        return SweepResult(
            strategy_id=strategy_id,
            regime=window["regime"],
            ticker="ALL",
            period_start=window["start"],
            period_end=window["end"],
            sharpe=round(sharpe, 3),
            win_rate=round(win_rate, 3),
            total_return_pct=round(
                sum(r["metrics"].get("total_return_pct", 0) for r in results_per_ticker) / len(results_per_ticker),
                2,
            ),
            max_drawdown_pct=round(max_dd, 2),
            profit_factor=round(avg_pf, 2) if avg_pf else None,
            total_trades=total_trades,
            avg_hold_days=window["length"],
        )

    def _save_to_registry(self, results: list[SweepResult]) -> None:
        """Write sweep results to strategy_regime_performance."""
        registry = StrategyPerformanceRegistry()

        grouped: dict[tuple[str, str], list[SweepResult]] = {}
        for r in results:
            key = (r.strategy_id, r.regime)
            grouped.setdefault(key, []).append(r)

        for (strategy_id, regime), group in grouped.items():
            pnl_series = [r.total_return_pct / 100 for r in group]
            hold_days = [r.avg_hold_days for r in group]
            registry.record_performance(
                strategy_id=strategy_id,
                regime=regime,
                pnl_series=pnl_series,
                hold_days=hold_days,
            )
            logger.info(
                "Registry: %s / %s → Sharpe=%.2f, win=%.0f%%, trades=%d",
                strategy_id, regime,
                sum(pnl_series) / len(pnl_series) * np.sqrt(252) / max(0.01, np.std(pnl_series)),
                sum(r.win_rate for r in group) / len(group) * 100,
                sum(r.total_trades for r in group),
            )


def run_sweep(tickers: list[str] | None = None) -> list[dict]:
    """CLI entry point. Return a list of dicts for JSON serialization."""
    sweeper = StrategySweeper(tickers=tickers)
    results = sweeper.sweep(save_registry=True)
    return [r.__dict__ for r in results]
