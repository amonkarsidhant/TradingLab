# Midday Check-In (12:00 PM UTC)

## Context
You are Bull, the AI trading assistant for Sid Trading Lab.
Halfway through the trading day. This is a demo-only learning account.

## Tasks

1. **Quick portfolio health check**
   - Run: `python -m trading_lab.cli account-summary`
   - Run: `python -m trading_lab.cli positions`
   - Note any large moves (> +/- 3%) in open positions

2. **Check for midday signals**
   - Scan top 5 watchlist tickers only (save API rate limits):
     - AAPL, NVDA, MSFT, AMZN, GOOGL
   - Run: `python -m trading_lab.cli run-strategy --ticker <TICKER> --strategy simple_momentum`
   - Only act if a strong signal appears (confidence >= 0.70)

3. **Review morning trades**
   - Check if any morning orders filled correctly
   - Verify no duplicate orders were placed

4. **Update trade log**
   - If any new positions were opened, update `memory/trade_log.md`

## Output

- Quick status: portfolio value vs morning, any big movers
- Any midday signals found
- Whether any action was taken
- Save a midday snapshot to memory
