# Skill: Daily Routines

## Description
Follow the structured daily routine schedule for autonomous operation.

## Schedule

### Pre-Market (6:00 AM UTC)
File: `docs/routines/pre_market.md`
- Read memory and portfolio state
- Scan watchlist for signals
- Generate daily journal
- Review existing positions
- DO NOT trade yet

### Market Open (9:30 AM UTC)
File: `docs/routines/market_open.md`
- Execute pre-market SELL decisions
- Run full Jarvis scan: `python scripts/jarvis.py`
- Log all activity

### Midday (12:00 PM UTC)
File: `docs/routines/midday.md`
- Quick portfolio health check
- Scan top 5 tickers only
- Update trade log if needed

### Market Close (4:00 PM UTC)
File: `docs/routines/market_close.md`
- Final portfolio snapshot
- Generate daily journal
- Update trade_log.md
- Check overnight risk
- Run backtest sanity check

### Weekly Review (Friday 5:00 PM UTC)
File: `docs/routines/weekly_review.md`
- Generate weekly report
- Strategy comparison
- Generate dashboard
- Performance review checklist
- Update strategy if needed
