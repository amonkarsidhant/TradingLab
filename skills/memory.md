# Skill: Memory Management

## Description
Read and update the agent's persistent memory. Two systems work together:
1. **Markdown files** — human-readable memory in `memory/` and `docs/`
2. **MemPalace** — semantic search and cross-session recall via ChromaDB

## Markdown Files

### Trade Log
- Path: `memory/trade_log.md`
- Contains: open positions, recent trades, performance metrics
- Update: after market close, after any trade

### Strategy
- Path: `memory/strategy.md`
- Contains: entry/exit criteria, watchlist, rules
- Update: weekly review, after strategy changes

### Decision Log
- Path: `docs/decision-log.md`
- Contains: why trades were made, lessons learned
- Update: after significant trades or strategy shifts

## MemPalace (Semantic Memory)

### Structure
- Wing: `sid_trading_lab` — the entire trading lab knowledge base
- Rooms: `memory`, `src`, `documentation`, `scripts`, `skills`, `testing`
- 658 drawers indexed and searchable

### Commands
```
mempalace search "entry criteria for momentum trades"
mempalace status
mempalace list_rooms --wing sid_trading_lab
mempalace diary_write "Today's summary..."
mempalace diary_read
```

### Auto-ingest
The `mempalace-ingest.sh` hook auto-mines files on write/update.
No manual re-mining needed for individual file changes.

### When to use MemPalace vs Markdown
- **MemPalace**: research questions, "what did we decide about...", discovering past patterns
- **Markdown**: current state, open positions, active strategy parameters

## Commands

### Read Memory
Use the Read tool on the file paths above.

### Search Historical Context
Use `mempalace search "query"` for semantic recall across all past sessions.

### Update Trade Log
After market close:
1. Read current trade_log.md
2. Update Open Positions table with current prices
3. Add new trades to Recent Trades table
4. Update Performance metrics
5. Write back with Write tool
6. Auto-ingested to MemPalace by hook

### Update Strategy
After weekly review:
1. Read current strategy.md
2. Adjust rules based on performance
3. Document changes in decision-log.md
