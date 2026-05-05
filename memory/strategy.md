# Trading Strategy — Bull v1.1

## Philosophy
Beat the S&P 500 through disciplined, fundamentals-driven swing trading.
Not day trading. Not gambling. Patient capital allocation.

## Entry Criteria

1. **Price momentum** — 5-day lookback shows >1% move with confirmation
2. **Technical health** — RSI not overbought (< 70), not oversold (> 30)
3. **Market context** — No major macro red flags (Fed decisions, earnings warnings)
4. **Conviction** — At least 2 of 3 strategies agree on direction
5. **Position sizing** — Target 10-15% of portfolio per position
6. **Market-cap quality** — Prefer >$5B market cap. Sub-$5B positions get 0.5x score penalty.
7. **Earnings warning** — Check yfinance for earnings within 7 days. Warn, do not block.

## Exit Criteria

1. **Trailing stop** — -7% from peak price (not entry). Auto-adjusts as price rises.
2. **Profit taking** — +15% = sell 50%, let rest run with trailing stop
3. **Signal reversal** — Strategy generates SELL with > 0.60 confidence
4. **Time stop** — No action after 30 days = reassess
5. **Portfolio rebalance** — Position > 20% of total = trim
6. **Position limit** — Max 10 positions. No exceptions. Trim to add.

## Dynamic Parameters

Strategy parameters auto-adjust based on market regime:
- **Bull / trending**: wider lookbacks, larger position sizes
- **Bear / volatile**: tighter stops, smaller positions, higher cash reserve
- **Ranging / calm**: mean reversion favored, tighter profit targets

Current regime detected from VIX proxy + price volatility of SPY.

## Watchlist

### Core (always scan)
- AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA, AMD

### Growth
- CRM, ADBE, NFLX, UBER, COIN, PLTR

### Value/Dividend
- JNJ, PG, KO, V, MA

## What NOT to trade
- Options
- Leveraged ETFs
- Crypto
- Penny stocks (< $5)
- Biotech (binary outcomes)
- IPOs within first 6 months

## Lessons Learned (May 2026)

### May 1: Telegram Bot Health Audit
- PTB JobQueue > APScheduler for cron jobs (same event loop, no threading conflicts)
- HTML parse_mode requires `_esc()` on all dynamic text — backticks and angle brackets crash Telegram
- `KeepAlive` must use dict form: `{SuccessfulExit: false, Crashed: true}` to avoid restart loops
- Only one poller per bot token — `Conflict: terminated by other getUpdates request`

### May 4: Jarvis Scan + SELL Fix
- `EntryScorer` naming drift caused import crash (`SignalScorer` vs `EntryScorer`)
- Score dict extraction needed: `.get("score", 0)` before sorting
- T212 SELL 400 Bad Request: integer rounding broke `quantityAvailableForTrading`. Use `close_position()` with exact `-float(available)`.
- `close_position()` now has `dry_run=False` parameter for safety
- Earnings check via yfinance — no API key needed, FMP free tier is dead (403 Legacy Endpoint)
- Market-cap gate added: sub-$5B gets 0.5x penalty
- Grouped daily reports: Gainers / Losers / Activity / Risk Flags
- `sqlite3.OperationalError: too many open files` on macOS — sweep combos spawn 100+ SQLite connections. Use `NullRoundTripTracker` for sweeps.
- TSLA E2E test accidentally placed a real demo sell. Cancelled before fill. Lesson: always verify `dry_run` first.

## Open Improvements

1. **Trailing stop upgrade** — Switch from fixed -7% (entry) to peak-based. GOOGL +9% would keep stop at +2% (€356), not entry €328.
2. **Position trim logic** — At 10/10, new signals should suggest "trim X to add Y" not just skip.
3. **Profit-taking at +15%** — Currently no automation. Jarvis should flag when positions hit +15%.
4. **Earnings blocking** — Currently warns only. Consider `EARNINGS_BLOCK_MISSING=true` to block new entries with missing data.
5. **Market regime detection** — Currently stub. Need VIX proxy or SPY volatility calculation.
