"""
Jarvis — Autonomous Demo Trading Agent.

Daily loop:
1. Read portfolio state
2. Check existing positions for SELL signals (rebalance)
3. Scan watchlist for new BUY signals
4. Score and rank all signals
5. Execute top-ranked BUYs (with cash/position limits)
6. Generate activity report

Usage:
    python scripts/jarvis.py

Safety:
- Demo environment only
- Max 10 positions
- Max 20% per position
- 10% cash reserve
- Logs every decision to SQLite
- Rate-limited API calls (6s between account summary requests)
"""
from __future__ import annotations

from datetime import datetime, timezone

from trading_lab.agentic.market_regime import MarketRegimeDetector
from trading_lab.agentic.portfolio import PortfolioManager
from trading_lab.agentic.scorer import EntryScorer
from trading_lab.config import get_settings
from trading_lab.data.market_data import make_provider
from trading_lab.models import SignalAction
from trading_lab.strategies import get_strategy

# -- Configuration --------------------------------------------------------------

WATCHLIST = [
    "AAPL_US_EQ", "TSLA_US_EQ", "NVDA_US_EQ", "MSFT_US_EQ",
    "AMZN_US_EQ", "GOOGL_US_EQ", "AMD_US_EQ", "NFLX_US_EQ",
    "INTC_US_EQ", "META_US_EQ", "CRM_US_EQ", "ADBE_US_EQ",
    "UBER_US_EQ", "COIN_US_EQ", "PLTR_US_EQ",
]


def _t212_to_yahoo(t212_ticker: str) -> str:
    if t212_ticker.endswith("_US_EQ"):
        return t212_ticker[:-6]
    if t212_ticker.endswith("_EQ"):
        return t212_ticker[:-3]
    return t212_ticker


# -- Main loop ------------------------------------------------------------------

def main():
    settings = get_settings()
    print(f"{'='*60}")
    print(f"JARVIS — Autonomous Demo Trading Agent")
    print(f"Environment: {settings.t212_env}")
    print(f"Orders enabled: {settings.can_place_orders}")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}")
    print()

    pm = PortfolioManager(settings)
    scorer = EntryScorer()
    regime_detector = MarketRegimeDetector()

    # 0. Detect market regime from SPY
    print("--- Market Regime ---")
    try:
        provider = make_provider(
            source="yfinance",
            ticker="SPY",
            cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
        )
        spy_prices = provider.get_prices(ticker="SPY", lookback=30)
        regime = regime_detector.detect(spy_prices)
        print(f"Regime: {regime.regime}")
        print(f"  {regime.description}")
        print(f"  Preferred strategies: {', '.join(regime.preferred_strategies)}")
        print(f"  Position size multiplier: {regime.position_size_multiplier:.1f}x")
        print(f"  Cash reserve multiplier: {regime.cash_reserve_multiplier:.1f}x")
        print(f"  Trailing stop: {regime.trailing_stop_pct:.1%}")
        strategies = regime.preferred_strategies
    except Exception as exc:
        print(f"Could not detect regime ({exc}). Using defaults.")
        regime = None
        strategies = ["simple_momentum", "ma_crossover", "mean_reversion"]
    print()

    # Build strategy kwargs from regime
    def _strategy_kwargs(name: str) -> dict:
        if not regime:
            if name == "simple_momentum":
                return {"lookback": 5}
            if name == "ma_crossover":
                return {"fast": 10, "slow": 30}
            if name == "mean_reversion":
                return {"period": 14, "oversold": 30, "overbought": 70}
            if name == "volume_price":
                return {"lookback": 10, "threshold_pct": 2.0, "volume_multiplier": 1.5}
            if name == "sentiment":
                return {"fear_threshold": 20, "greed_threshold": 80}
            return {}
        if name == "simple_momentum":
            return {"lookback": regime.momentum_lookback}
        if name == "ma_crossover":
            return {"fast": regime.ma_fast, "slow": regime.ma_slow}
        if name == "mean_reversion":
            return {"period": regime.mean_rev_period, "oversold": regime.mean_rev_oversold, "overbought": regime.mean_rev_overbought}
        if name == "volume_price":
            return {"lookback": regime.momentum_lookback, "threshold_pct": 2.0, "volume_multiplier": 1.5}
        if name == "sentiment":
            return {"fear_threshold": 20, "greed_threshold": 80}
        return {}

    # Override PortfolioManager risk params based on regime
    if regime:
        pm.TRAILING_STOP_PCT = regime.trailing_stop_pct
        pm.MIN_CASH_PCT = 0.10 * regime.cash_reserve_multiplier

    # 1. Read current state
    state = pm.state()
    print(f"--- Portfolio State ---")
    print(f"Cash: €{state.cash:,.2f}")
    print(f"Total Value: €{state.total_value:,.2f}")
    print(f"Invested: €{state.invested_value:,.2f}")
    print(f"Unrealized P&L: €{state.unrealized_pnl:,.2f}")
    print(f"Open Positions: {len(state.positions)}")
    for p in state.positions:
        print(f"  {p.ticker}: {p.quantity} @ €{p.avg_price:.2f} → €{p.current_price:.2f} (P&L: €{p.unrealized_pnl:.2f})")
    print()

    target_size = pm.target_position_size(state)
    if regime:
        target_size *= regime.position_size_multiplier
    print(f"Target position size: €{target_size:,.2f}")
    print(f"Can add positions: {pm.can_add_position(state)}")
    print()

    # 2. Check existing positions for SELL signals (trailing stop first)
    sell_orders = []
    print("--- Rebalancing Existing Positions ---")
    for pos in state.positions:
        # Check trailing stop first (-7% from peak)
        if pm.trailing_stop_hit(pos):
            drawdown = pm.position_drawdown(pos)
            print(f"  {pos.ticker}: TRAILING STOP HIT (drawdown {drawdown:.1%} from peak €{pos.peak_price:.2f})")
            try:
                result = pm.sell_position(pos)
                sell_orders.append((pos.ticker, result))
                print(f"    -> SOLD ✓ (trailing stop)")
            except Exception as exc:
                print(f"    -> ERROR: {exc}")
            continue

        yahoo_ticker = _t212_to_yahoo(pos.ticker)
        try:
            provider = make_provider(
                source="yfinance",
                ticker=yahoo_ticker,
                cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
            )
            prices = provider.get_prices(ticker=yahoo_ticker, lookback=30)
            if len(prices) < 5:
                print(f"  {pos.ticker}: insufficient data")
                continue

            for strat_name in strategies:
                kwargs = _strategy_kwargs(strat_name)
                strategy = get_strategy(strat_name, **kwargs)
                signal = strategy.generate_signal(ticker=pos.ticker, prices=prices)

                if signal.action == SignalAction.SELL and signal.confidence >= 0.50:
                    print(f"  {pos.ticker}: SELL signal ({strat_name}, conf={signal.confidence:.2f})")
                    try:
                        result = pm.sell_position(pos)
                        sell_orders.append((pos.ticker, result))
                        print(f"    -> SOLD ✓")
                        # rate limit handled by Trading212Client
                    except Exception as exc:
                        print(f"    -> ERROR: {exc}")
                    break
            else:
                print(f"  {pos.ticker}: HOLD (no SELL signal, peak €{pos.peak_price:.2f})")
        except Exception as exc:
            print(f"  {pos.ticker}: ERROR — {exc}")
    print()

    # Refresh state after sells
    if sell_orders:
        state = pm.state()
        print(f"Post-rebalance: Cash €{state.cash:,.2f}, Positions {len(state.positions)}")
        print()

    # 3. Scan watchlist for BUY signals
    buy_candidates = []
    print("--- Scanning Watchlist for BUY Signals ---")
    open_tickers = pm.get_open_tickers(state)

    for t212_ticker in WATCHLIST:
        if t212_ticker in open_tickers:
            continue  # already own it

        yahoo_ticker = _t212_to_yahoo(t212_ticker)
        try:
            provider = make_provider(
                source="yfinance",
                ticker=yahoo_ticker,
                cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
            )
            prices = provider.get_prices(ticker=yahoo_ticker, lookback=30)
            if len(prices) < 5:
                continue

            for strat_name in strategies:
                kwargs = _strategy_kwargs(strat_name)
                strategy = get_strategy(strat_name, **kwargs)
                signal = strategy.generate_signal(ticker=t212_ticker, prices=prices)

                if signal.action == SignalAction.BUY and signal.confidence >= 0.50:
                    score = scorer.score(signal, prices)
                    buy_candidates.append((signal, prices, score))
                    print(f"  {t212_ticker}: BUY ({strat_name}, conf={signal.confidence:.2f}, score={score})")
                    break
        except Exception as exc:
            print(f"  {t212_ticker}: SKIP — {exc}")
    print()

    # 4. Rank and execute top BUYs
    buy_orders = []
    if buy_candidates and pm.can_add_position(state):
        print("--- Executing Top BUY Signals ---")
        buy_candidates.sort(key=lambda x: x[2], reverse=True)

        for signal, prices, score in buy_candidates:
            if not pm.can_add_position(state):
                print(f"  Position limit reached. Skipping remaining.")
                break

            target = pm.target_position_size(state)
            if target <= 0:
                print(f"  No deployable cash. Stopping.")
                break

            current_price = prices[-1] if prices else 0
            if current_price <= 0:
                continue

            quantity = max(1, int(target / current_price))
            print(f"  {signal.ticker}: score={score} → buying {quantity} shares @ ~€{current_price:.2f} (target €{target:,.2f})")

            try:
                result = pm.place_order(signal.ticker, quantity)
                buy_orders.append((signal.ticker, quantity, result))
                print(f"    -> ORDER PLACED ✓")
                time.sleep(1)  # rate limit buffer
                state = pm.state()
            except Exception as exc:
                print(f"    -> ERROR: {exc}")
    else:
        print("--- No BUY candidates or no capacity ---")
    print()

    # 5. Final state
    state = pm.state()
    print("=" * 60)
    print("DAILY REPORT")
    print("=" * 60)
    print(f"Cash: €{state.cash:,.2f}")
    print(f"Total Value: €{state.total_value:,.2f}")
    print(f"Invested: €{state.invested_value:,.2f}")
    print(f"Unrealized P&L: €{state.unrealized_pnl:,.2f}")
    print(f"Open Positions: {len(state.positions)}")
    print()
    print(f"Orders SOLD: {len(sell_orders)}")
    for t, r in sell_orders:
        print(f"  SOLD {t}")
    print(f"Orders BOUGHT: {len(buy_orders)}")
    for t, q, r in buy_orders:
        print(f"  BOUGHT {q} {t}")
    print()
    print("Done. All demo trades logged to SQLite.")


if __name__ == "__main__":
    main()
