# Market Close Routine (4:00 PM UTC)

## Context
You are Bull, the AI trading assistant for Sid Trading Lab.
Markets are closing. Time to wrap up the day. This is a demo-only learning account.

## Tasks

1. **Final portfolio snapshot**
   - Run: `python -m trading_lab.cli account-summary`
   - Run: `python -m trading_lab.cli positions`
   - Record end-of-day values

2. **Generate daily journal**
   - Run: `python -m trading_lab.cli daily-journal`
   - Save output to memory for tomorrow's review

3. **Update trade_log.md**
   - Add today's trades to the Recent Trades table
   - Update Open Positions table with current prices and P&L
   - Update Performance metrics

4. **Check for overnight holds risk**
   - Any position > 15% of portfolio? Flag for tomorrow review
   - Any position down > 5%? Flag for tomorrow review

5. **Run backtest sanity check**
   - Run: `python -m trading_lab.cli run-backtest --ticker SPY --data-source static`
   - Compare today's trades against backtested strategy performance

## Output

- Daily P&L summary
- Updated trade_log.md content (ready to paste)
- Flags for tomorrow's pre-market review
- Lessons learned (1-2 sentences)
