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
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.regime.detector import RegimeDetector
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
        self.detector = RegimeDetector()

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

        # First: detect regime windows from SPY history for the lookback period
        regime_windows = self._detect_regime_windows()

        logger.info(
            "Sweeping %d strategies across %d regime windows on %d tickers",
            len(strategies), len(regime_windows), len(self.tickers),
        )

        for strategy_id in strategies:
            for window in regime_windows:
                result = self._sweep_strategy_in_window(strategy_id, window)
                if result:
                    all_results.append(result)

        if save_registry:
            self._save_to_registry(all_results)

        return all_results

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _detect_regime_windows(self) -> list[dict]:
        """Detect contiguous regime windows from SPY history over lookback_days."""
        provider = make_provider(source="yfinance", ticker="SPY")
        prices_data = provider.get_prices(ticker="SPY", lookback=self.lookback_days + self.warmup_days)

        if not prices_data or not hasattr(prices_data, "values"):
            logger.warning("Could not fetch SPY prices for regime window detection")
            return []

        closes = prices_data["Close"].values if hasattr(prices_data, "values") else prices_data
        dates = (
            prices_data.index.strftime("%Y-%m-%d").tolist()
            if hasattr(prices_data, "index")
            else [str(i) for i in range(len(closes))]
        )

        if len(closes) < self.lookback_days:
            logger.warning("Not enough SPY history for regime windows")
            return []

        windows: list[dict] = []
        current_regime = None
        window_start = None
        window_start_idx = None

        for i in range(self.warmup_days, len(closes)):
            window = closes[: i + 1]
            signal = self.detector.detect()
            regime = signal.regime.value

            if regime != current_regime:
                # Close previous window
                if current_regime and window_start_idx is not None:
                    window_len = i - window_start_idx
                    if window_len >= self.MIN_REGIME_WINDOW_DAYS:
                        windows.append({
                            "regime": current_regime,
                            "start": window_start,
                            "end": dates[i - 1],
                            "start_idx": window_start_idx,
                            "end_idx": i - 1,
                            "length": window_len,
                        })
                        logger.info(
                            "Regime window: %s [%s → %s] (%d days)",
                            current_regime, window_start, dates[i - 1], window_len,
                        )
                current_regime = regime
                window_start = dates[i]
                window_start_idx = i

        # Close last window
        if current_regime and window_start_idx is not None:
            window_len = len(closes) - window_start_idx
            if window_len >= self.MIN_REGIME_WINDOW_DAYS:
                windows.append({
                    "regime": current_regime,
                    "start": window_start,
                    "end": dates[-1],
                    "start_idx": window_start_idx,
                    "end_idx": len(closes) - 1,
                    "length": window_len,
                })

        if not windows:
            # Fallback: just use the last 30 days as a single window
            windows.append({
                "regime": "neutral",
                "start": dates[-self.lookback_days] if len(dates) >= self.lookback_days else dates[0],
                "end": dates[-1],
                "start_idx": max(0, len(closes) - self.lookback_days),
                "end_idx": len(closes) - 1,
                "length": min(self.lookback_days, len(closes)),
            })

        return windows

    def _sweep_strategy_in_window(
        self,
        strategy_id: str,
        window: dict,
    ) -> SweepResult | None:
        """Backtest a single strategy within a single regime window across all tickers."""
        results_per_ticker: list[dict] = []

        for ticker in self.tickers:
            try:
                # Fetch prices for this regime window
                provider = make_provider(source="yfinance", ticker=ticker)
                prices_data = provider.get_prices(ticker=ticker, lookback=window["length"] + 5)

                if prices_data is None:
                    continue
                closes = prices_data["Close"].values if hasattr(prices_data, "values") else prices_data
                tick_dates = (
                    prices_data.index.strftime("%Y-%m-%d").tolist()
                    if hasattr(prices_data, "index")
                    else [str(i) for i in range(len(closes))]
                )

                if len(closes) < 20:
                    continue

                strategy = get_strategy(strategy_id)
                engine = BacktestEngine(strategy, initial_capital=10_000.0)
                result = engine.run(prices=closes, dates=tick_dates, ticker=ticker)

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
        combined_trades = []
        for r in results_per_ticker:
            combined_trades.extend(r["trades"])

        # Build a pseudo equity curve for combined metrics
        # (Simple average of returns per ticker, normalized)
        ticker_returns = [
            r["metrics"]["total_return_pct"] / 100
            for r in results_per_ticker
            if r["metrics"].get("total_return_pct") is not None
        ]

        # Win-rate across all tickers
        wins = sum(1 for r in results_per_ticker for t in r["trades"] if getattr(t, "pnl", 0) > 0)
        total_trades = sum(len(r["trades"]) for r in results_per_ticker)
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        # Pseudo-sharpe: use cross-ticker returns
        if len(ticker_returns) >= 2:
            mean_ret = sum(ticker_returns) / len(ticker_returns)
            var = sum((r - mean_ret) ** 2 for r in ticker_returns) / (len(ticker_returns) - 1)
            std = np.sqrt(var) if var > 0 else 0.0
            sharpe = (mean_ret - 0.04 / 252) / std * np.sqrt(252) if std > 0 else 0.0
        else:
            sharpe = 0.0

        # Max drawdown: worst single-ticker
        max_dd = max(
            (r["metrics"].get("max_drawdown_pct") or 0)
            for r in results_per_ticker
            if r["metrics"].get("max_drawdown_pct") is not None
        ) if results_per_ticker else 0.0

        # Profit factor
        total_pf = [
            r["metrics"].get("profit_factor")
            for r in results_per_ticker
            if r["metrics"].get("profit_factor") is not None
        ]
        avg_pf = sum(total_pf) / len(total_pf) if total_pf else None

        # Average hold days
        hold_days = [
            r["length"] for r in results_per_ticker if "length" in r
        ]  # Not directly available; use window length as proxy
        avg_hold = window["length"]  # simplified proxy

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
            avg_hold_days=avg_hold,
        )

    def _save_to_registry(self, results: list[SweepResult]) -> None:
        """Write sweep results to strategy_regime_performance."""
        registry = StrategyPerformanceRegistry()

        # Group by strategy_id + regime
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
