"""Seed the strategy_regime_performance table with historical backtests.

Usage:
    python scripts/seed_registry.py [--days 180] [--tickers AAPL,MSFT,SPY]

This script:
1. Fetches historical data (SPY, VIXY, XLY, XLP)
2. Computes regime state for each day in the lookback period
3. Identifies contiguous regime windows (min 10 days)
4. Runs backtests for every registered strategy in every regime window
5. Stores aggregated results (pnl series + hold days) in the SQLite table
"""
from __future__ import annotations

import argparse
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import yfinance as yf

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.regime.detector import RegimeDetector
from trading_lab.strategies import get_strategy, list_strategies

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class HistoricalRegimeRow:
    date: str
    regime: str
    vix_proxy: float
    trend_score: float
    confidence: float


def fetch_history(ticker: str, days: int) -> dict:
    """Fetch closing prices and dates for ticker from yfinance."""
    try:
        df = yf.Ticker(ticker).history(period=f"{days + 30}d", interval="1d")
        if df.empty:
            return {"dates": [], "closes": []}
        df = df.dropna()
        return {
            "dates": df.index.strftime("%Y-%m-%d").tolist(),
            "closes": df["Close"].values.tolist(),
        }
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", ticker, exc)
        return {"dates": [], "closes": []}


def compute_historical_regimes(spy: dict, vixy: dict, detector: RegimeDetector) -> list[HistoricalRegimeRow]:
    n = len(spy["dates"])
    if n == 0:
        return []
    rows: list[HistoricalRegimeRow] = []
    for i in range(60, n):
        vix = vixy["closes"][i] if i < len(vixy["closes"]) else 15.0
        closes = np.array(spy["closes"][: i + 1])
        trend = _calc_trend(closes)
        regime, conf = detector._classify(vix, 0.5, 1.0, trend)
        rows.append(HistoricalRegimeRow(
            date=spy["dates"][i], regime=regime.value,
            vix_proxy=round(float(vix), 2),
            trend_score=round(trend, 6), confidence=round(conf, 4),
        ))
    return rows


def _calc_trend(closes: np.ndarray) -> float:
    if len(closes) < 50:
        return 0.0
    ema20 = _ema(closes, 20)
    sma50 = np.mean(closes[-50:])
    if sma50 == 0:
        return 0.0
    return float((closes[-1] - ema20) / ema20 - (closes[-1] - sma50) / sma50)


def _ema(values: np.ndarray, period: int) -> float:
    alpha = 2 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return float(ema)


def find_regime_windows(rows: list[HistoricalRegimeRow], min_window_days: int) -> list[dict]:
    if not rows:
        return []
    windows: list[dict] = []
    current = None
    start_idx = None
    for i, r in enumerate(rows):
        if current is None:
            current = r.regime
            start_idx = i
        elif r.regime != current:
            length = i - start_idx
            if length >= min_window_days:
                windows.append({
                    "regime": current,
                    "start_date": rows[start_idx].date,
                    "end_date": rows[i - 1].date,
                    "length": length,
                })
            current = r.regime
            start_idx = i
    # close final
    if current and start_idx is not None:
        length = len(rows) - start_idx
        if length >= min_window_days:
            windows.append({
                "regime": current, "start_date": rows[start_idx].date,
                "end_date": rows[-1].date, "length": length,
            })
    return windows


def backtest_strategy_in_window(
    strategy_id: str, ticker: str, window: dict, capital: float = 10_000.0,
) -> dict | None:
    try:
        end = datetime.strptime(window["end_date"], "%Y-%m-%d") + timedelta(days=5)
        start = datetime.strptime(window["start_date"], "%Y-%m-%d") - timedelta(days=10)
        df = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d"
        )
        if df.empty:
            return None
        df = df.dropna()
        closes = df["Close"].values.tolist()
        dates = df.index.strftime("%Y-%m-%d").tolist()
        if len(closes) < 20:
            return None

        strategy = get_strategy(strategy_id)
        engine = BacktestEngine(strategy, initial_capital=capital)
        result = engine.run(prices=closes, dates=dates, ticker=ticker)

        trades = result.trades
        pnls = [float(getattr(t, "pnl", 0)) for t in trades]
        hold_days = []
        for t in trades:
            try:
                ed = datetime.strptime(str(t.exit_date), "%Y-%m-%d")
                sd = datetime.strptime(str(t.entry_date), "%Y-%m-%d")
                hold_days.append((ed - sd).days)
            except Exception:
                hold_days.append(0)

        return {
            "strategy_id": strategy_id,
            "regime": window["regime"],
            "ticker": ticker,
            "pnls": pnls,
            "hold_days": hold_days,
            "total_trades": len(trades),
            "total_return_pct": result.metrics.get("total_return_pct", 0.0),
        }
    except Exception as exc:
        logger.debug("Backtest error %s/%s: %s", strategy_id, ticker, exc)
        return None


def main():
    parser = argparse.ArgumentParser(description="Seed strategy_regime_performance")
    parser.add_argument("--days", type=int, default=180, help="Lookback days")
    parser.add_argument("--tickers", default="SPY,AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,CRM",
                        help="Tickers")
    parser.add_argument("--db-path", default="./trading_lab.sqlite3")
    parser.add_argument("--min-window", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fast", action="store_true",
                        help="Seed with a single backtest per strategy (faster)")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",")]
    detector = RegimeDetector()

    logger.info("Fetching SPY + VIXY history (%d days)...", args.days)
    spy = fetch_history("SPY", args.days)
    vixy = fetch_history("VIXY", args.days)
    if not spy["dates"] or not vixy["dates"]:
        logger.error("Failed to fetch required history. Aborting.")
        return

    logger.info("Computing historical regimes (%d days)...", len(spy["dates"]))
    rows = compute_historical_regimes(spy, vixy, detector)
    windows = find_regime_windows(rows, args.min_window)
    if not windows:
        logger.error("No regime windows found. Try --min-window 5")
        return

    logger.info("Found %d regime windows:", len(windows))
    for w in windows:
        logger.info("  %s: %s → %s (%d days)", w["regime"], w["start_date"], w["end_date"], w["length"])

    strategies = list_strategies()
    registry = StrategyPerformanceRegistry(db_path=args.db_path) if not args.dry_run else None

    # Accumulator: strategy_regime -> list of pnls and hold_days
    accumulator: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for window in windows:
        for strategy_id in strategies:
            # Fast mode: only backtest SPY
            tickers_to_test = ["SPY"] if args.fast else tickers
            for ticker in tickers_to_test:
                result = backtest_strategy_in_window(strategy_id, ticker, window)
                if result:
                    accumulator[(strategy_id, window["regime"])].append(result)

    total_inserted = 0
    for (sid, regime), results in accumulator.items():
        all_pnls = []
        all_holds = []
        total_trades = 0
        for r in results:
            all_pnls.extend(r["pnls"])
            all_holds.extend(r["hold_days"])
            total_trades += r["total_trades"]

        if not all_pnls:
            continue

        # For the registry we use trade returns (pnl / capital)
        pnl_returns = [p / 10_000.0 if p != 0 else 0 for p in all_pnls]

        if args.dry_run:
            logger.info(
                "[DRY RUN] %s/%s: trades=%d, avg_return=%.4f",
                sid, regime, total_trades, sum(pnl_returns) / len(pnl_returns)
            )
            total_inserted += 1
            continue

        registry.record_performance(
            strategy_id=sid,
            regime=regime,
            pnl_series=pnl_returns,
            hold_days=all_holds,
        )
        total_inserted += 1
        logger.info("Registered: %s/%s — %d trades", sid, regime, total_trades)

    msg = "would insert" if args.dry_run else "inserted"
    logger.info("Done. %s %d strategy-regime combinations", msg, total_inserted)


if __name__ == "__main__":
    main()
