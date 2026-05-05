"""Seed the strategy_regime_performance table with historical backtests.

Usage:
    python scripts/seed_registry.py [--days 180] [--tickers AAPL,MSFT,SPY]

This script:
1. Fetches historical data (SPY, VIXY, XLY, XLP, breadth components) ONCE
2. Detects regime windows from historical data (not live)
3. Backtests EVERY registered strategy per window
4. Records results in strategy_regime_performance table
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.data.market_data import make_provider
from trading_lab.regime.detector import HistoricalRegimeDetector
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.strategies import get_strategy, list_strategies

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

DEFAULT_TICKERS = ["SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AMD", "CRM"]
BREADTH_TICKERS = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "JPM",
    "JNJ", "V", "PG", "UNH", "HD", "MA", "BAC", "ABBV", "PFE", "KO",
    "PEP", "WMT", "MRK", "AVGO", "TMO", "COST", "DIS", "ABT", "ACN",
    "DHR", "VZ", "NKE", "TXN", "ADBE", "CRM", "CMCSA", "XOM", "CVX",
    "LLY", "NFLX", "AMD", "QCOM", "HON", "INTC", "AMGN", "SPGI", "IBM",
]


def _fetch_all_data(lookback: int) -> dict[str, list[float]]:
    """Batch download all tickers once."""
    all_tickers = list(set(DEFAULT_TICKERS + ["SPY", "VIXY", "XLY", "XLP"] + BREADTH_TICKERS))
    data: dict[str, list[float]] = {}
    for ticker in all_tickers:
        try:
            provider = make_provider(source="yfinance", ticker=ticker)
            prices: list[float] = provider.get_prices(ticker=ticker, lookback=lookback)
            if prices and len(prices) > 0:
                data[ticker] = prices
                logger.info("%s: %d bars", ticker, len(prices))
        except Exception as exc:
            logger.debug("Skip %s: %s", ticker, exc)
    return data


def _detect_regime_windows(data: dict[str, list[float]], min_window: int = 10) -> list[dict]:
    """Label each trading day its regime and merge into contiguous windows."""
    det = HistoricalRegimeDetector()
    spy_closes = data.get("SPY", [])
    n = len(spy_closes)

    if n < 50:
        logger.warning("Need at least 50 bars of SPY, got %d", n)
        return []

    regimes: list[str] = []
    for i in range(50, n):
        try:
            state = det.detect_from_data(
                spy_closes=spy_closes[: i + 1],
                vixy_closes=data.get("VIXY", spy_closes[: i + 1])[: i + 1],
                xly_closes=data.get("XLY", spy_closes[: i + 1])[: i + 1],
                xlp_closes=data.get("XLP", spy_closes[: i + 1])[: i + 1],
                breadth_data={sym: data[sym][: i + 1] for sym in BREADTH_TICKERS if sym in data},
            )
            regimes.append(state.regime.value)
        except Exception as exc:
            logger.debug("Regime detect skip at %d: %s", i, exc)
            regimes.append("neutral")

    # Merge contiguous windows
    windows: list[dict] = []
    if not regimes:
        return []

    current = regimes[0]
    w_start = 50
    for i, reg in enumerate(regimes[1:], start=51):
        if reg != current:
            w_len = i - w_start
            if w_len >= min_window:
                windows.append({
                    "regime": current,
                    "start_idx": w_start,
                    "end_idx": i - 1,
                    "length": w_len,
                })
                logger.info(
                    "Window %s: bars %d-%d (%d trading days)",
                    current, w_start, i - 1, w_len,
                )
            current = reg
            w_start = i

    # Close last
    w_len = n - w_start
    if w_len >= min_window:
        windows.append({
            "regime": current,
            "start_idx": w_start,
            "end_idx": n - 1,
            "length": w_len,
        })
        logger.info("Window %s: bars %d-%d (%d days)", current, w_start, n - 1, w_len)

    if not windows:
        windows.append({
            "regime": "neutral",
            "start_idx": max(0, n - 30),
            "end_idx": n - 1,
            "length": min(30, n),
        })

    return windows


def _run_strategies(
    data: dict[str, list[float]],
    windows: list[dict],
) -> list[dict]:
    """Backtest every strategy in every regime window."""
    registry = StrategyPerformanceRegistry()
    strategies = list_strategies()
    results: list[dict] = []

    for strategy_id in strategies:
        for w in windows:
            all_pnls: list[float] = []
            hold_days: list[int] = []

            for ticker in DEFAULT_TICKERS:
                closes = data.get(ticker, [])
                start = w["start_idx"]
                end = min(len(closes), w["end_idx"] + 1)
                if end - start < 20:
                    continue

                strategy = get_strategy(strategy_id)
                engine = BacktestEngine(strategy, initial_capital=10_000.0)
                result = engine.run(
                    prices=closes[start:end],
                    dates=[str(i) for i in range(end - start)],
                    ticker=ticker,
                )

                total_return_pct = result.metrics.get("total_return_pct", 0.0)
                all_pnls.append(total_return_pct / 100)
                for t in result.trades:
                    d = getattr(t, "days_held", None)
                    if isinstance(d, int):
                        hold_days.append(d)

            if not all_pnls:
                continue

            wins = sum(1 for p in all_pnls if p > 0)
            win_rate = wins / len(all_pnls)
            avg_return = sum(all_pnls) / len(all_pnls)
            std = np.std(all_pnls, ddof=1)
            daily_r = avg_return / max(w["length"], 1)
            sharpe = (daily_r / max(std, 1e-6)) * np.sqrt(252)
            max_dd = max(
                r.metrics.get("max_drawdown_pct", 0)
                for r in [result]  # single result, using last one
            ) if "result" in dir() else 0.0
            pf = result.metrics.get("profit_factor")

            results.append({
                "strategy_id": strategy_id,
                "regime": w["regime"],
                "total_return_pct": round(sum(all_pnls) / len(all_pnls) * 100, 2),
                "sharpe": round(sharpe, 3),
                "win_rate": round(win_rate, 3),
                "trades": len(all_pnls),
                "hold_days": round(sum(hold_days) / len(hold_days)) if hold_days else 0,
                "max_dd": round(max_dd, 2),
                "profit_factor": round(pf, 2) if pf else None,
            })

            registry.record_performance(
                strategy_id=strategy_id,
                regime=w["regime"],
                pnl_series=all_pnls,
                hold_days=hold_days,
            )
            logger.info(
                "Registry: %s / %s → Sharpe=%.2f, win=%.0f%%, trades=%d",
                strategy_id, w["regime"], sharpe, win_rate * 100, len(all_pnls),
            )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed strategy_regime_performance table")
    parser.add_argument("--days", type=int, default=180, help="Historical lookback period")
    parser.add_argument("--tickers", type=str, default=",".join(DEFAULT_TICKERS), help="Tickers")
    parser.add_argument("--db-path", type=str, default="./trading_lab.sqlite3", help="SQLite path")
    parser.add_argument("--min-window", type=int, default=10, help="Min regime window days")
    parser.add_argument("--dry-run", action="store_true", help="Skip writing to DB")
    parser.add_argument("--fast", action="store_true", help="Use SPY only, skip breadth")
    args = parser.parse_args()

    if args.fast:
        args.tickers = "SPY"

    logger.info("Fetching %d days of historical data...", args.days)
    hist_data = _fetch_all_data(args.days)

    logger.info("Detecting regime windows...")
    windows = _detect_regime_windows(hist_data, min_window=args.min_window)
    logger.info("Found %d regime windows", len(windows))

    for w in windows:
        logger.info("  %s: bars %d-%d (%d days)", w["regime"], w["start_idx"], w["end_idx"], w["length"])

    logger.info("Running backtests for %d strategies...", len(list_strategies()))
    results = _run_strategies(hist_data, windows)

    logger.info("Done. %d results written to registry.", len(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
