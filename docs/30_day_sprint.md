# 30-Day Sid Trading Sprint

## Rule of the sprint

No live trading automation.

The objective is not profit.  
The objective is disciplined trading practice.

## Phase 1 — Foundation, Days 1-5

Outcome: local repo, credentials, safe API access, GitHub history.

Tasks:
- Install Claude Code.
- Install Ollama.
- Create GitHub repo.
- Add Trading 212 demo credentials to `.env`.
- Fetch account summary.
- Fetch positions.
- Fetch instruments.
- Write first daily journal.

## Phase 2 — Data and observation, Days 6-10

Outcome: understand symbols, positions, watchlist, and basic price behavior.

Tasks:
- Build watchlist.
- Store instrument metadata.
- Pull historical orders/transactions from demo.
- Build a simple CSV/SQLite log.
- Define first 3 strategy hypotheses.

## Phase 3 — Strategy rules, Days 11-15

Outcome: strategies produce signals, not trades.

Candidate strategies:
- Simple momentum
- Mean reversion
- Breakout
- Moving average crossover
- Risk-off cash preservation rule

For each:
- Entry rule
- Exit rule
- Stop rule
- Max position size
- Failure mode

## Phase 4 — Backtesting and paper execution, Days 16-22

Outcome: dry-run and demo execution with logs.

Tasks:
- Build backtest runner.
- Compare strategy against buy-and-hold.
- Add transaction cost assumptions.
- Add max drawdown view.
- Paper trade only in demo.
- Review every signal manually.

## Phase 5 — Review and governance, Days 23-30

Outcome: go/no-go report.

Tasks:
- Summarize all trades/signals.
- Identify false confidence.
- Identify best and worst strategy.
- Decide whether to continue demo trading.
- Define strict criteria before any live trade.

## Go/no-go criteria after 30 days

Do not go live unless all are true:

- You understand every line of the code.
- You can explain every strategy rule.
- You have logs for all generated signals.
- You have reviewed losing signals.
- You have tested failure conditions.
- You have a written max-loss rule.
- You are willing to lose the money allocated.
- Live automation remains disabled until manually reviewed.
