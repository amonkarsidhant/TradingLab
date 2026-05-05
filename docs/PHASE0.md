# Phase 0 — Autonomous Regime-Aware Execution Loop
> Target: The agent runs 24/7 with zero manual intervention.
> Proof: 5 days of autonomous operation, >1 regime transition, every trade Telegram-alerted.

---

## What Phase 0 Actually Builds

Instead of the bot running `scan-rank` blindly every hour, it will:

1. **Detect regime** — compute VIX proxy + market breadth + trend
2. **Select strategy** — query which strategy has best Sharpe *in that regime*
3. **Run one scan** — only the selected strategy (not all 3)
4. **Execute safely** — same safety rules, but fully auto (no confirm button in demo)
5. **Log everything** — SQLite gets `regime_id`, `strategy_id`, `confidence` per cycle

---

## Current State

| Component | File | Status |
|-----------|------|--------|
| Unified bot + scheduler | `scripts/telegram_scheduler.py` | Runs 5 cron jobs via APScheduler, Telegram alerts |
| Strategies | `src/trading_lab/strategies/` | Momentum, MeanReversion, EarningsGap (hardcoded) |
| Safety rules | `src/trading_lab/safety_rules.py` | Max 10 pos, 20%/pos, 10% cash, -7% stop |
| Backtest engine | `src/trading_lab/backtest/engine.py` | Single-run backtest with round-trip tracking |
| Position watcher | `src/trading_lab/watcher/` | Monitors open positions, trailing stops |
| SQLite journal | `round_trips.sqlite3` | P&L, fills, timestamps — but no regime column |
| Memory files | `memory/trade_log.md`, `memory/strategy.md` | Manual markdown updated after trades |

---

## New Code (Files to Create)

### 1. Regime Detector
**File:** `src/trading_lab/regime/detector.py`

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class Regime(Enum):
    RISK_ON     = "risk_on"      # Low VIX, strong breadth, uptrend
    RISK_OFF    = "risk_off"     # High VIX, weak breadth, downtrend
    NEUTRAL     = "neutral"      # Mixed signals
    VOLATILE    = "volatile"     # Spiking VIX, churning breadth
    TRENDING    = "trending"     # Low VIX, strong directional breadth

@dataclass(frozen=True)
class RegimeState:
    regime: Regime
    vix_proxy: float          # VIXY close or 30d realized vol
    breadth_pct: float        # % of SPY constituents above 50MA
    sector_rotation: float    # XLY / XLP ratio
    trend_score: float        # SPY price vs 20EMA vs 50SMA
    confidence: float         # 0.0 - 1.0 (how clear the signal is)
    timestamp: str            # ISO8601

class RegimeDetector:
    def detect(self) -> RegimeState:
        # 1. Fetch VIXY (VIX proxy) via yfinance
        # 2. Compute % of SPY tickers above 50MA via helpers
        # 3. Fetch XLY and XLP, compute ratio
        # 4. Compare SPY vs 20EMA and 50SMA
        # 5. Map (vix, breadth, trend) -> Regime
        # 6. Compute confidence = 1 - (entropy of softmax over regime scores)
        ...
```

**Helper:** `src/trading_lab/data/vix_proxy.py` — fetch `VIXY` close from yfinance.
**Helper:** `src/trading_lab/data/breadth.py` — compute breadth for a universe (SPY constituents from Wikipedia + yfinance). Cache daily.
**Helper:** `src/trading_lab/data/sector_rotation.py` — fetch `XLY` / `XLP` via yfinance.

### 2. Strategy Performance Registry
**File:** `src/trading_lab/registry/performance.py`

SQLite table `strategy_regime_performance`:
```sql
CREATE TABLE strategy_regime_performance (
    id INTEGER PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    regime TEXT NOT NULL,
    sharpe REAL,
    win_rate REAL,
    avg_hold_days REAL,
    trade_count INTEGER,
    updated_at TEXT
);
```

```python
class StrategyPerformanceRegistry:
    def record(self, strategy_id: str, regime: Regime, pnl_series: list[float]):
        # Compute Sharpe, win rate, avg hold time
        # Upsert into SQLite
        ...

    def best_for_regime(self, regime: Regime, min_trades: int = 5) -> Optional[str]:
        # SELECT strategy_id from strategy_regime_performance
        # WHERE regime = ? AND trade_count >= ?
        # ORDER BY sharpe DESC LIMIT 1
        ...

    def all_for_regime(self, regime: Regime) -> list[dict]:
        # Return ranked list for logging / Telegram
        ...
```

### 3. Auto Selector
**File:** `src/trading_lab/strategy_selector.py`

```python
class StrategySelector:
    def __init__(self, registry: StrategyPerformanceRegistry, fallback: str = "momentum"):
        self.registry = registry
        self.fallback = fallback

    def select(self, regime: RegimeState) -> str:
        best = self.registry.best_for_regime(regime.regime)
        if best and regime.confidence > 0.6:
            return best
        return self.fallback  # Default if not enough data or low confidence
```

### 4. Hourly Cycle Integration
**File:** Modify `src/trading_lab/scheduler/hourly_cycle.py` (or inline in `telegram_scheduler.py`)

```python
async def hourly_cycle():
    regime = regime_detector.detect()
    strategy_name = selector.select(regime)

    # Build the scan command for just this strategy
    cmd = f"python -m trading_lab.cli scan-rank --strategy {strategy_name}"

    # Run it
    output = await run_subprocess(cmd)

    # Parse output for signals (reuse existing scan logic)
    signals = parse_signals(output)

    # Safety + execute
    for sig in signals:
        if safety_check(sig):
            if auto_approve:
                await place_order(sig)
            else:
                await telegram_notify(f"PROPOSED: {sig}")

    # Log cycle
    db.execute(
        "INSERT INTO cycles (timestamp, regime, confidence, strategy, signals_count, executed) VALUES (?, ?, ?, ?, ?, ?)",
        (iso_now(), regime.regime.value, regime.confidence, strategy_name, len(signals), executed_count)
    )

    # Telegram summary
    await telegram_notify(build_cycle_summary(regime, strategy_name, signals))
```

### 5. Schema Migration
**File:** `src/trading_lab/db/migrations/002_add_regime.sql`

```sql
ALTER TABLE round_trips ADD COLUMN regime TEXT;
ALTER TABLE round_trips ADD COLUMN strategy_used TEXT;

CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    regime TEXT NOT NULL,
    confidence REAL NOT NULL,
    strategy TEXT NOT NULL,
    signals_count INTEGER,
    executed_count INTEGER,
    pnl_after_cycle REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_regime_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    regime TEXT NOT NULL,
    sharpe REAL,
    win_rate REAL,
    avg_hold_days REAL,
    trade_count INTEGER DEFAULT 0,
    updated_at TEXT
);
```

---

## Files to Modify (Existing)

| File | Change |
|------|--------|
| `src/trading_lab/cli.py` | Add new command: `detect-regime` (prints human-readable regime state) |
| `src/trading_lab/cli.py` | Add new command: `strategy-rank-by-regime --regime X` |
| `scripts/telegram_scheduler.py` | Replace generic `scan-rank` job with `hourly_cycle()` call |
| `src/trading_lab/backtest/engine.py` | Inject regime tag into backtest result so registry can attribute by regime |
| `memory/strategy.md` | Add regime-aware strategy selection as an operating principle |

---

## Commit Sequence

```
feat(regime): add RegimeDetector with VIX proxy, breadth, sector rotation
feat(registry): add strategy_regime_performance table and registry
feat(selector): add StrategySelector with fallback logic
feat(bot): wire hourly_cycle() into telegram scheduler with regime logging
chore(db): add migration 002 for regime columns and cycles table
feat(cli): add detect-regime and strategy-rank-by-regime commands
docs(memory): update strategy.md with regime-aware selection
```

Each commit is &lt; 200 lines, reviewable, and can be rolled back independently.

---

## Verification Checklist

| # | Test | How |
|---|------|-----|
| 1 | `python -m trading_lab.cli detect-regime` prints regime, confidence, 4 metrics | Run locally |
| 2 | `python -m trading_lab.cli strategy-rank-by-regime --regime volatile` returns ranked list | Run locally with seeded data |
| 3 | Simulator runs 5 days without crash | Let unified bot run; check `logs/scheduler.log` |
| 4 | SQLite `cycles` table has > 1 regime transition | Query: `SELECT DISTINCT regime FROM cycles WHERE date > date('now', '-5 days')` |
| 5 | Telegram receives hourly summary with emoji regime header | Check Telegram chat |
| 6 | VPS `git log` shows Phase 0 commits | `git log --oneline -10` on VPS |

---

## Scope Limit (What Phase 0 Does NOT Do)

- **Does NOT** self-modify strategies (Phase 2)
- **Does NOT** run A/B backtests (Phase 2)
- **Does NOT** generate novel strategies from LLM (Phase 3)
- **Does NOT** change position sizing by regime (Phase 1)
- **Does NOT** paper-trade before adopting (Phase 2 gate)
- **Does NOT** use real-time websocket data (not available on T212)

Phase 0 is strictly: **detect → select → scan → execute → log → alert**.

---

## Hard Constraints (Immutable)

- `T212_ENV=demo` always
- Max 10 positions, 20% per position, 10% cash minimum
- No short, no options, no leverage
- Cut losers at -7% trailing stop
- If regime confidence < 60%, fall back to default strategy (no risky bets on ambiguous signals)

---

## References

- `roadmap.md` — full project vision and phase map
- `skills/risk-management.md` — stop logic, sizing rules
- `skills/trading.md` — order placement, T212 API
- `references/go-trader-phase2-patterns.md` — concentration guard, tiered stops (useful for Phase 1)
- `references/memory-update-workflow.md` — how to update memory files after changes
