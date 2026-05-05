# Phase 1 — Meta-Learning Engine
> Sid Trading Lab | Autonomous Agent Roadmap
> Status: **Ready to build** | Depends on: Phase 0 complete

---

## Goal

The agent learns **which strategy to use in which regime**, not just running the same default strategy across all market conditions. Capital allocation and strategy selection are driven by empirical evidence — not by the builder's opinion or momentum's "good intuition."

Phase 0 gave us regime detection and a selector. Phase 1 makes that selector **actually useful** by feeding it backtest data.

---

## Problem Statement

| Question | Phase 0 Answer | Phase 1 Target |
|---|---|---|
| Which strategy to use today? | Fallback to `simple_momentum` because registry has zero trades | Choose from backtested Sharpe per regime |
| How much conviction? | 0.0 confidence if no trades | Confidence = backtest Sharpe ratio / max observed |
| Where does the registry get data? | Requires live trades to populate | Pre-seeded with 6-month walk-forward backtests per strategy × regime |
| What if all strategies lose? | No change, still runs best-known anyway | Trigger "pause new entries" mode |
| When to override the selector? | Never, it's automatic | Human can pin a strategy via bot `/strategy pin <name>` |

---

## Architecture

```
       Backtest Engine ──┐
                         ▼
   ┌──────────────────────────────────────┐
   │   Strategy Sweeper (grid/bayesian)   │
   │   For each strategy:                   │
   │     Run 6-month walk-forward per regime │
   │     Store: Sharpe, win-rate, max DD   │
   │     in strategy_regime_performance     │
   └────────────────┬─────────────────────┘
                    │ seed
                    ▼
   ┌──────────────────────────────────────┐
   │   StrategySelector.now()               │
   │   current_regime → registry.best_for()│
   │   returns: (strategy_id, confidence)  │
   │   if no data: use default + low conf   │
   │   if < 2 strategies with data: flag  │
   └────────────┬─────────────────────────┘
                │
                ▼
   ┌──────────────────────────────────────┐
   │   Capital Allocator                    │
   │   Input: account value, regime, best   │
   │   Output: position size table          │
   │   Rule: min 10% cash always            │
   │   Rule: max 20% per position           │
   │   Rule: weight by normalized sharpe   │
   └────────────────────────────────────────┘
```

---

## Milestones (6 total)

### M1. Strategy Sweeper
Implement `src/trading_lab/meta/sweeper.py` that:
- Iterates all registered strategies in `src/trading_lab/strategies/`
- Runs a 6-month (126 bar) walk-forward backtest for each strategy against each regime window
- Regime window = contiguous days when regime detector output was stable (e.g., 8 of 10 days `risk_off`)
- Stores results in `strategy_regime_performance` table
- Command: `python -m trading_lab.cli sweep-strategies`

**Acceptance:** Run produces Sharpe values for each strategy-regime pair. Table is non-empty.

### M2. Pre-Seed Registry
Write a script `scripts/seed_registry.py` that:
- Reads historical regime detections (or generates them from SPY history)
- Maps every 30-day lookback window to a regime
- Runs backtests for all existing strategies in that window
- Inserts results into `strategy_regime_performance`

**Acceptance:** `best_for_regime("risk_off")` returns a real strategy, not None. `selector.select()` confidence > 0.50 for at least 2 regimes.

### M3. Capital Allocator
New module `src/trading_lab/meta/allocator.py` that:
- Reads `best_for_regime()` output
- Reads account cash + positions
- Computes target position sizes using regime-weighted allocation:
  - High Sharpe regime = larger position size (up to 20%)
  - Low Sharpe / risk_off = smaller position size (as low as 5%)
  - Always keep 10% cash
- Outputs a list of `(ticker, target_value, confidence)`

**Acceptance:** Given current `risk_off` with regime Sharpe = 0.3 and `simple_momentum` as best, allocates $2k to a $20k account. Given `trending` with Sharpe = 1.5, allocates $4k per position.

### M4. Confidence-Based Pause
When selector confidence < 0:40 (because few strategies have data for that regime):
- Log to SQLite `cycles` as `action: PAUSED`
- Bot Telegram message: "Regime: X, confidence: Y — insufficient strategy data. New entries paused."
- Continue scanning but mark all signals as `dry_run=True`
- Existing positions + stops continue normally

**Acceptance:** Manual test by deleting all rows for one regime from `strategy_regime_performance` and running autonomous cycle. Bot says paused, no new entries proposed.

### M5. A/B Harness for Strategy Variants
New module `src/trading_lab/meta/ab_harness.py` that:
- Takes two strategy configs (or module paths)
- Runs the same 6-month backtest on both
- Outputs: Sharpe diff, win-rate diff, max DD comparison
- Statistical significance test (Welch's t-test on daily returns)
- Produces a markdown report to `reports/ab/<id>.md`

Command: `python -m trading_lab.cli ab-test --baseline simple_momentum --variant pullback_mean_reversion`

**Acceptance:** Running the command produces a report with clear "pass / fail / too close to call" verdict.

### M6. Performance Feedback Loop
Weekly cron job (in addition to existing weekly report) that:
- Reads `cycles` table for the past 7 days
- For each regime seen, computes mean P&L of signals generated under that regime
- Updates `strategy_regime_performance` with live data
- If live Sharpe diverges from backtest Sharpe by > 1 std, flag a warning
- Bot message: "⚠️ Live Sharpe for `simple_momentum` in `risk_off` (0.12) diverges from backtest (0.35). Consider re-sweeping."

**Acceptance:** Weekly report contains live vs backtest Sharpe comparison table.

---

## Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| `src/trading_lab/meta/sweeper.py` | Create | Strategy sweeper engine |
| `src/trading_lab/meta/allocator.py` | Create | Capital allocator |
| `src/trading_lab/meta/ab_harness.py` | Create | A/B test harness |
| `scripts/seed_registry.py` | Create | Historical pre-seed script |
| `src/trading_lab/registry/selector.py` | Modify | Integrate allocator, confidence pause, live feedback |
| `src/trading_lab/commands/autonomous_cycle.py` | Modify | Respect pause, use allocator output |
| `src/trading_lab/cli.py` | Modify | Add `sweep-strategies`, `ab-test`, `seed-registry` commands |
| `scripts/telegram_bot_unified.py` | Modify | Add `/strategy pin`, `/strategy unpin`, `/meta status` |
| `docs/PHASE1.md` | Create | This document |
| `memory/meta_learning_log.md` | Create | Running log of sweeps, A/B results, adoptions |

---

## Success Criteria

1. `StrategySelector.select()` returns a non-default strategy for at least 3 of 5 regimes
2. Capital allocator recommends ≠ $4k per position (i.e., regime-aware sizing)
3. A/B harness can run in < 10 minutes for 2 strategies against 1 ticker
4. Telegram bot can show current best strategy + confidence + allocator status
5. `cycles` table shows `action: PAUSED` on at least one day during the week (confidence < 0.40)
6. Weekly report contains live vs backtest Sharpe comparison

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Backtests take too long (6mo × strategies × regimes) | High | Cache results in SQLite. Only re-sweep when regime changes. Use parallel processing if needed. |
| yfinance rate limits during sweeps | Medium | Add 2s sleep between requests. Use cached data where possible. |
| Live Sharpe diverges wildly from backtest | High | That's exactly what Phase 1 should detect and flag. Use rolling 30-day Sharpe, not absolute. |
| Capital allocator recommends oversized positions during bad regime | Low | Hard safety rail: max 20%/position, min 10% cash, enforced by RiskPolicy. Allocator is a recommendation, not a mandate. |
| Regime detector is wrong for extended period | Medium | Phase 0 uses multiple inputs (VIXY + breadth + rotation). Phase 1 adds rolling regime accuracy as a metric. |

---

## Dependencies

- Phase 0 complete (regime detection, strategy registry, selector working)
- `pytest` for harness testing
- `scipy.stats` for t-test in A/B harness
- `itertools` for parameter grid sweeps

---

## Estimation

| Milestone | Estimate | Blockers |
|---|---|---|
| M1 Sweeper | 2-3 hours | None |
| M2 Pre-Seed | 1 hour | M1 |
| M3 Allocator | 2 hours | M2 |
| M4 Confidence Pause | 1 hour | M3 |
| M5 A/B Harness | 2-3 hours | None |
| M6 Feedback Loop | 1-2 hours | M3, M5 |
| Bot commands | 1 hour | M3, M4 |
| Total | **~12 hours** spread across 1 week | |

---

> "Phase 0 made the agent *aware* of regime. Phase 1 makes the agent *act on it with evidence.*"
