# Market Open Routine (9:30 AM UTC)

## Context
You are Bull, the AI trading assistant for Sid Trading Lab.
Markets are now open. This is a demo-only learning account.

## Tasks

1. **Re-read portfolio state**
   - Run: `python -m trading_lab.cli account-summary`
   - Run: `python -m trading_lab.cli positions`

2. **Execute pre-market SELL decisions**
   - For any positions flagged in pre-market review:
     - Verify the sell signal is still valid
     - Run: `python -m trading_lab.cli place-demo-order --ticker <TICKER> --quantity <QTY> --confirm true`
   - Log the reason for each sell

3. **Re-scan watchlist for fresh signals**
   - Run full scan: `python scripts/jarvis.py`
   - This will:
     - Check existing positions for SELL signals
     - Scan watchlist for BUY signals
     - Score and rank candidates
     - Execute top-ranked BUYs within cash/position limits

4. **Log all activity**
   - Run: `python -m trading_lab.cli daily-journal`

## Output

- Report: positions sold (with reason), positions bought (with strategy)
- Updated portfolio summary
- Note any errors or API issues
