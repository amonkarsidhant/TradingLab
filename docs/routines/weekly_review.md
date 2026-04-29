# Weekly Review Routine (Friday 5:00 PM UTC)

## Context
You are Bull, the AI trading assistant for Sid Trading Lab.
End of trading week. Time to reflect and plan. This is a demo-only learning account.

## Tasks

1. **Generate weekly report**
   - Run: `python -m trading_lab.cli weekly-report --date today`
   - Review the full week of signals, snapshots, and trades

2. **Strategy comparison**
   - Run: `python -m trading_lab.cli strategy-comparison --ticker AAPL --data-source static`
   - Run: `python -m trading_lab.cli strategy-comparison --ticker NVDA --data-source static`
   - Which strategy performed best this week?

3. **Generate dashboard**
   - Run: `python -m trading_lab.cli dashboard --data-source static --output docs/dashboard.html`

4. **Performance review checklist**
   - [ ] Portfolio vs S&P 500 benchmark
   - [ ] Biggest winner / biggest loser analysis
   - [ ] Strategy adherence score (0-100)
   - [ ] Lessons learned
   - [ ] Adjustments for next week

5. **Update strategy.md if needed**
   - Did any rules fail this week?
   - Should we adjust position sizing, stop losses, or watchlist?
   - Document any changes in `docs/decision-log.md`

6. **Review agent reviews**
   - Run: `python -m trading_lab.cli agent-reviews --week current`
   - Check approval rates and consensus patterns

## Output

- Weekly performance summary (return vs benchmark)
- Strategy leaderboard for the week
- Top 3 lessons learned
- Any strategy or watchlist adjustments proposed
- Plan for next week
