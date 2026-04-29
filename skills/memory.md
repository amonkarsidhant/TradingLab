# Skill: Memory Management

## Description
Read and update the agent's persistent memory files.

## Files

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

## Commands

### Read Memory
Use the Read tool on the file paths above.

### Update Trade Log
After market close:
1. Read current trade_log.md
2. Update Open Positions table with current prices
3. Add new trades to Recent Trades table
4. Update Performance metrics
5. Write back with Write tool

### Update Strategy
After weekly review:
1. Read current strategy.md
2. Adjust rules based on performance
3. Document changes in decision-log.md
