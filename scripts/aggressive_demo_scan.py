"""
Aggressive demo trading scan.

Scans multiple tickers across strategies, shows signals,
and places demo orders for BUY signals above confidence threshold.

Usage:
    python scripts/aggressive_demo_scan.py
"""
import json
from datetime import datetime, timezone

from trading_lab.config import get_settings
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.data.market_data import make_provider
from trading_lab.engine import ExecutionEngine
from trading_lab.logger import SnapshotLogger
from trading_lab.risk import RiskPolicy
from trading_lab.strategies import get_strategy, list_strategies

# -- Configuration --------------------------------------------------------------

T212_TICKERS = [
    "AAPL_US_EQ", "TSLA_US_EQ", "NVDA_US_EQ", "MSFT_US_EQ",
    "AMZN_US_EQ", "GOOGL_US_EQ", "AMD_US_EQ", "NFLX_US_EQ",
    "INTC_US_EQ", "META_US_EQ",
]

STRATEGIES = ["simple_momentum", "ma_crossover", "mean_reversion"]


def _t212_to_yahoo(t212_ticker: str) -> str:
    """Strip T212 suffixes to get Yahoo Finance ticker."""
    if t212_ticker.endswith("_US_EQ"):
        return t212_ticker[:-6]
    if t212_ticker.endswith("_EQ"):
        return t212_ticker[:-3]
    return t212_ticker


def _yahoo_to_t212(yahoo_ticker: str) -> str:
    """Map Yahoo ticker back to T212 ticker for order placement."""
    for t in T212_TICKERS:
        if _t212_to_yahoo(t) == yahoo_ticker:
            return t
    return yahoo_ticker + "_US_EQ"

# Aggressive risk policy — lower bar, larger positions
RISK = RiskPolicy(
    max_quantity_per_order=10.0,
    min_confidence_to_trade=0.50,
)

# -- Helpers ------------------------------------------------------------------

def _fmt_signal(signal):
    return (
        f"[{signal.action.value}] {signal.ticker} via {signal.strategy} "
        f"(conf={signal.confidence:.2f}) — {signal.reason}"
    )


def main():
    settings = get_settings()
    print(f"Environment: {settings.t212_env}")
    print(f"Can place orders: {settings.can_place_orders}")
    print(f"DB: {settings.db_path}")
    print(f"Cash: €5,000")
    print(f"Risk threshold: {RISK.min_confidence_to_trade} | Max qty: {RISK.max_quantity_per_order}")
    print()

    client = Trading212Client(settings)
    logger = SnapshotLogger(settings.db_path)
    engine = ExecutionEngine(
        broker=client,
        risk_policy=RISK,
        logger=logger,
    )

    signals_found = []
    orders_placed = []
    orders_skipped = []

    for t212_ticker in T212_TICKERS:
        print(f"--- {t212_ticker} ---")
        yahoo_ticker = _t212_to_yahoo(t212_ticker)
        provider = make_provider(
            source="yfinance",
            ticker=yahoo_ticker,
            cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
        )
        try:
            prices = provider.get_prices(ticker=yahoo_ticker, lookback=60)
        except Exception as exc:
            print(f"  Price fetch failed: {exc}")
            continue

        if len(prices) < 20:
            print(f"  Not enough price data ({len(prices)} bars)")
            continue

        for strat_name in STRATEGIES:
            try:
                kwargs = {}
                if strat_name == "simple_momentum":
                    kwargs = {"lookback": 5}
                elif strat_name == "ma_crossover":
                    kwargs = {"fast": 10, "slow": 30}
                elif strat_name == "mean_reversion":
                    kwargs = {"period": 14, "oversold": 30, "overbought": 70}
                strategy = get_strategy(strat_name, **kwargs)
                signal = strategy.generate_signal(ticker=t212_ticker, prices=prices)
            except Exception as exc:
                print(f"  {strat_name}: ERROR — {exc}")
                continue

            if signal.action.value in ("BUY", "SELL") and signal.confidence >= RISK.min_confidence_to_trade:
                signals_found.append(signal)
                print(f"  SIGNAL: {_fmt_signal(signal)}")

                # Place demo order
                try:
                    result = engine.handle_signal(signal, dry_run=False)
                    if result["executed"]:
                        orders_placed.append(result)
                        print(f"    -> DEMO ORDER PLACED ✓")
                    else:
                        orders_skipped.append((signal, result["reason"]))
                        print(f"    -> SKIPPED: {result['reason']}")
                except Exception as exc:
                    orders_skipped.append((signal, str(exc)))
                    print(f"    -> ERROR: {exc}")
            else:
                print(f"  {strat_name}: HOLD ({signal.reason[:50]})")

    # -- Summary ----------------------------------------------------------------
    print()
    print("=" * 60)
    print("SCAN COMPLETE")
    print(f"Signals found: {len(signals_found)}")
    print(f"Demo orders placed: {len(orders_placed)}")
    print(f"Skipped/rejected: {len(orders_skipped)}")
    print()

    if orders_placed:
        print("Orders placed:")
        for o in orders_placed:
            s = o["signal"]
            print(f"  {s['action']} {s['ticker']} qty={s['suggested_quantity']} — {s['reason'][:60]}")

    if orders_skipped:
        print()
        print("Skipped/rejected:")
        for s, reason in orders_skipped[:10]:
            print(f"  {s.ticker} ({s.strategy}): {reason}")

    # Final account check
    print()
    print("--- Final Account Snapshot ---")
    summary = client.account_summary()
    print(json.dumps(summary, indent=2))
    positions = client.positions()
    print(f"Positions: {len(positions)}")
    for p in positions:
        print(f"  {p.get('ticker')} qty={p.get('quantity')} value={p.get('currentValue')}")


if __name__ == "__main__":
    main()
