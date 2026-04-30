# Slash Command: /scan
Run a full portfolio scan using all three strategies across the watchlist.

## Steps
1. Read `memory/strategy.md` for current watchlist
2. For each ticker in Core watchlist, run all 3 strategies:
   ```
   source .venv/bin/activate && python -m trading_lab.cli run-strategy --data-source chained --ticker <TICKER> --strategy simple_momentum --dry-run
   source .venv/bin/activate && python -m trading_lab.cli run-strategy --data-source chained --ticker <TICKER> --strategy ma_crossover --dry-run
   source .venv/bin/activate && python -m trading_lab.cli run-strategy --data-source chained --ticker <TICKER> --strategy mean_reversion --dry-run
   ```
3. Summarize results: BUY signals with confidence > 0.5, agreement across strategies
4. Update `memory/trade_log.md` with scan results
5. Log all signals to SQLite if actionable
