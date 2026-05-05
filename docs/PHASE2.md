# Phase 2 — Self-Modifying Strategy Agent
> **Status:** SPEC — approved for build
> **Estimated Duration:** 10-14 hours focused work
> **Depends:** Phase 1 COMPLETE (all 6 milestones + gaps closed)
> **Risk Level:** Medium — touches code generation + disk writes

---

## Objective

Enable the agent to (1) **propose new strategy variants** via LLM, (2) **validate them through backtest + A/B**, (3) **adopt them automatically** if they pass statistical gates, and (4) **rollback** if live performance degrades.

This is the first phase where the agent touches its own source code.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      PHASE 2 — SELF-MODIFYING LOOP                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────────┐       │
│   │ REFLECT  │───▶│ HYPOTHESIZE  │───▶│ GENERATE CODE    │       │
│   │ (EOD)    │    │ (LLM prompt) │    │ (variant .py)    │       │
│   └──────────┘    └──────────────┘    └────────┬─────────┘       │
│                                                 │                 │
│                    ┌──────────────┐            ▼                  │
│                    │  ADOPT /     │◀───┌──────────────┐          │
│                    │  ROLLBACK      │    │   VALIDATE    │          │
│                    │  (git ops)     │    │   (backtest)  │          │
│                    └──────────────┘    └───────┬──────┘           │
│                           ▲                    │                  │
│                           │            ┌───────▼───────┐           │
│                           └────────────│   A/B HARNESS  │           │
│                                        │  (pass/fail)  │           │
│                                        └───────────────┘           │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 7 Stages (immutable sequence — no skipping)

| # | Stage | Actor | Duration | Gate |
|---|-------|-------|----------|------|
| 1 | **Trigger** | Scheduler (weekly) | Instant | New week OR strategy underperformance flag |
| 2 | **Reflect** | EOD agent reads last 7d P&L | ~30s | Grade worse than B- for current strategy |
| 3 | **Hypothesize** | LLM prompt with strategy source + metrics | 10-30s | Must return valid JSON with 3 variants |
| 4 | **Generate** | Write variant `.py` files + syntax check | ~1s per variant | `compile()` must succeed |
| 5 | **Validate** | Walk-forward backtest (126d) per variant | 2-5 min | Sharpe > baseline + 0.10 AND drawdown ≤ baseline + 2% |
| 6 | **A/B** | T-test against current strategy (same period) | 30s | p < 0.10 (two-sided) |
| 7 | **Adopt** | Git commit + swap active strategy + 48h watch | Instant | Commit hash logged; rollback on underperformance |

---

## Milestones

### M1 — Strategy Variant Generator
> **Goal:** LLM proposes 3 variants of the current strategy given its source code + performance by regime.

**Deliverables:**
- `src/trading_lab/meta/variant_generator.py` — `StrategyVariantGenerator` class
- `prompts/strategy_mutation.txt` — system prompt template
- `src/trading_lab/cli.py` — `generate-variants` command

**LLM Prompt Structure:**
```
You are a quantitative strategy researcher. Given a strategy's source code
and its Sharpe/win-rate by regime, propose THREE parameter mutations that
might improve underperforming regimes.

RULES:
- Only change numeric parameters (windows, thresholds, multipliers)
- Do NOT change the strategy class name or method signatures
- Do NOT add new data sources or indicators
- Each variant must be a valid Python class inheriting Strategy
- Return JSON: [{ "name": "...", "code": "...", "rationale": "..." }]

CURRENT STRATEGY:
{strategy_source}

PERFORMANCE BY REGIME:
{performance_table}

WEAKEST REGIME:
{weakest_regime}
```

**Validation Gate:**
- Each variant must `compile()` without error in isolated `exec()` namespace
- Must have `generate_signal(self, ticker, prices) -> Signal` method
- Must return `SignalAction` enum values

**Example Output:**
```json
{
  "variants": [
    {
      "name": "simple_momentum_fast",
      "code": "class SimpleMomentumFast(Strategy):...",
      "rationale": "Shortening lookback from 20 to 10 days improves responsiveness in risk_on regime where momentum decays faster."
    }
  ]
}
```

**Safety:**
- Variants written to `variants/` dir (gitignored in production, tracked in dev)
- NEVER overwrite `strategies/` originals
- File naming: `{original_name}_{variant_name}_{timestamp}.py`

---

### M2 — Syntax Sandbox
> **Goal:** Ensure generated code is syntactically valid and safe before disk write.

**Deliverables:**
- `src/trading_lab/meta/sandbox.py` — `SyntaxSandbox` class
- Methods: `validate(source_code) -> bool`, `test_call(source_code, prices) -> Signal`
- `src/trading_lab/cli.py` — `sandbox-test` command

**Checks (in order):**
1. `compile(source, '<variant>', 'exec')` — SyntaxError → reject
2. `ast.parse(source)` — check for forbidden imports (`os`, `subprocess`, `open`, `eval`, `exec`)
3. Instantiate in isolated namespace — check `hasattr(obj, 'generate_signal')`
4. Test call with synthetic prices `[100.0] * 30` — must return `Signal` object
5. Check `Signal.action` is valid `SignalAction` enum

**Forbidden Patterns (auto-reject):**
```python
import os, sys, subprocess, pathlib  # any filesystem/network
open("...", "...")                   # file I/O
eval("...")                          # code injection
exec("...")                          # code injection
requests.get/post                    # network calls
```

**Output:**
```python
@dataclass
class SandboxResult:
    valid: bool
    error: str | None
    test_signal: Signal | None
    forbidden_imports: list[str]
```

---

### M3 — A/B Backtest Harness for Variants
> **Goal:** Compare current strategy against each variant. Reuses Phase 1 A/B harness but adds variant-specific logic.

**Deliverables:**
- `src/trading_lab/meta/variant_validator.py` — `VariantValidator` class
- `src/trading_lab/cli.py` — `validate-variant` command

**Process:**
1. Load current strategy + N variants (from `variants/` dir)
2. For each variant:
   a. Run backtest on 126-day walk-forward (same regime windows as Phase 1 sweeper)
   b. Run A/B harness: current vs variant
   c. Check composite gate (see below)
3. Rank variants by composite score
4. Return adoption recommendation

**Composite Gate (ALL must pass):**
```python
SHARPE_DIFF_MIN = 0.10        # variant Sharpe > baseline + 0.10
DRAWDOWN_TOLERANCE = 2.0      # variant max_dd ≤ baseline + 2.0%
WIN_RATE_MIN = 0.50           # variant win_rate > 50%
MIN_TRADES = 5                # at least 5 trades for statistical validity
P_VALUE_MAX = 0.10            # p < 0.10 from Welch t-test
```

**Composite Score:**
```python
score = (sharpe_diff * 2.0) + (win_rate_diff * 1.0) - (dd_delta * 0.5)
# Highest score wins. Negative score = reject all.
```

**Output:**
```python
@dataclass
class VariantValidationResult:
    variant_name: str
    baseline_name: str
    passes: bool
    sharpe_diff: float
    win_rate_diff: float
    dd_delta: float
    p_value: float | None
    composite_score: float
    reason: str
```

---

### M4 — Adoption Gate + Git Integration
> **Goal:** Auto-commit adopted variants, enable rollback, log every change.

**Deliverables:**
- `src/trading_lab/meta/adoption_manager.py` — `AdoptionManager` class
- `src/trading_lab/cli.py` — `adopt-variant`, `rollback-strategy` commands
- Git hooks: auto-commit on adopt, tag on rollback point

**Adoption Flow:**
```python
1. variant_validation_result.passes == True
2. Copy variants/{variant}.py → src/trading_lab/strategies/{variant}.py
3. Register in strategy registry (list_strategies() now includes variant)
4. Git commit: f"feat(strategy): auto-adopt {variant_name} (sharpe={sharpe:.2f})"
5. Tag baseline before swap: f"pre-adopt-{variant_name}-{timestamp}"
6. Update active strategy in SQLite: UPDATE cycles SET strategy='{variant}' WHERE ...
7. Log to strategy_change_log table (see M6)
```

**Rollback Flow:**
```python
if live_sharpe < baseline_sharpe_after_48h:
    1. Git checkout pre-adopt tag
    2. Git commit: f"revert(strategy): roll back {variant_name} (live_sharpe degraded)"
    3. Remove from strategy registry
    4. Log rollback to strategy_change_log
    5. Telegram alert: "🔄 Strategy rolled back: {variant_name}"
```

**Safety:**
- NEVER auto-rollback during market hours (09:30-16:00 ET)
- Rollback only executes at market close (16:00 ET) or premarket (06:00 ET)
- Max 1 adoption per week (hard limit to prevent churn)
- Require 48h of live data before rollback decision (prevents noise-driven reversion)

---

### M5 — Performance Watchdog (48h Observation)
> **Goal:** Monitor live P&L after strategy adoption and trigger rollback if degraded.

**Deliverables:**
- `src/trading_lab/meta/watchdog.py` — `AdoptionWatchdog` class
- `src/trading_lab/cli.py` — `watchdog-check` command
- launchd/systemd timer: every 6 hours after adoption

**Logic:**
```python
48h_after_adoption:
    live_pnl = query_round_trips(strategy=variant_name, since=adoption_time)
    expected_pnl = query_backtest_expected(strategy=variant_name, regime=current_regime)
    
    if live_pnl.sharpe < expected_pnl.sharpe - 0.20:
        trigger_rollback(variant_name, reason="sharpe_degraded")
    elif live_pnl.max_drawdown > expected_pnl.max_drawdown + 3.0:
        trigger_rollback(variant_name, reason="drawdown_exceeded")
```

**States:**
- `observing` (0-48h) — no action, just log
- `confirmed` (48h+) — live matches expectation, clear to keep
- `rollback` (triggered) — revert to baseline

---

### M6 — Strategy Change Log
> **Goal:** Immutable audit trail of every strategy mutation.

**Deliverables:**
- SQLite table: `strategy_change_log`
- `src/trading_lab/meta/change_log.py` — `ChangeLog` class

**Schema:**
```sql
CREATE TABLE strategy_change_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    strategy_id     TEXT    NOT NULL,
    action          TEXT    NOT NULL,  -- 'adopt', 'rollback', 'manual_update'
    reason          TEXT    NOT NULL,
    baseline_hash   TEXT,               -- git commit hash before change
    variant_hash    TEXT,               -- git commit hash after change
    performance_before REAL,            -- Sharpe before adoption
    performance_after  REAL,            -- Sharpe after adoption (or at rollback)
    regime_at_change TEXT,
    llm_prompt      TEXT,               -- full prompt that generated variant
    llm_response    TEXT,               -- raw LLM response
    composite_score REAL,
    p_value         REAL,
    adopted_by      TEXT DEFAULT 'auto' -- 'auto' or user name
);
```

**Query Interface:**
```python
ChangeLog().list_changes(strategy_id="", since="", limit=50)
ChangeLog().get_latest_change(strategy_id="simple_momentum")
ChangeLog().success_rate()  # % of adoptions that weren't rolled back
```

---

## CLI Commands

| Command | Purpose | Phase |
|---------|---------|-------|
| `generate-variants` | LLM generates N variants from current strategy source | M1 |
| `sandbox-test --file variant.py` | Syntax + safety validation | M2 |
| `validate-variant --variant variant_name` | Full backtest + A/B vs current | M3 |
| `adopt-variant --variant variant_name` | Git commit + swap active strategy | M4 |
| `rollback-strategy --to baseline` | Git revert + remove from registry | M4 |
| `watchdog-check` | Check 48h observation window | M5 |
| `strategy-history [--strategy X]` | Show full mutation audit trail | M6 |

---

## Integration with Phase 1

### Reuses (no rebuild)
- `StrategySweeper` — walk-forward backtests
- `ABHarness` — statistical comparison
- `HistoricalRegimeDetector` — regime labels for backtest periods
- `StrategyPerformanceRegistry` — read/write registry
- `CapitalAllocator` — position sizing (unchanged)

### New Connections
```
variant_generator.py ──▶ prompts/strategy_mutation.txt
       │
       ▼
sandbox.py ──▶ compile() + ast.parse()
       │
       ▼
variant_validator.py ──▶ StrategySweeper + ABHarness
       │
       ▼
adoption_manager.py ──▶ git commit + registry update
       │
       ▼
watchdog.py ──▶ round_trips query + rollback trigger
       │
       ▼
change_log.py ──▶ strategy_change_log table
```

---

## Safety Architecture

### Layer 1 — Sandbox (code generation)
- `ast.parse` forbids dangerous imports
- `compile()` + `exec()` in isolated dict (no access to `__builtins__` except safe subset)
- File write restricted to `variants/` directory

### Layer 2 — Backtest Gate (validation)
- Must pass composite gate before adoption
- Minimum 126-day walk-forward (not cherry-picked period)
- A/B t-test prevents luck-based adoption

### Layer 3 — 48h Observation (live)
- Live performance must match backtest expectation ±20%
- Rollback only at market close / premarket (no intra-day panic)
- Max 1 adoption per week prevents churn

### Layer 4 — Git Safety
- Every adoption is a commit (reversible)
- Pre-adoption tag creates immutable rollback point
- `git log` is the ultimate audit trail

### Layer 5 — Human Override
- `--manual` flag skips LLM generation (human writes variant)
- `--force` flag bypasses 48h observation (use with caution)
- Telegram alerts on every adoption/rollback with full reasoning

---

## Error Handling

| Error | Mitigation |
|-------|------------|
| LLM returns invalid JSON | Retry 3× with temperature boost; else skip week |
| Generated code fails sandbox | Log to change_log with `action='rejected'` |
| Backtest crashes on variant | Exclude variant from A/B; log error |
| Git commit fails (dirty tree) | Auto-stash + retry; alert if persistent |
| VPS disk full during seed | Check before run; alert at 90% usage |
| Rollback fails (git conflict) | Alert human; enter manual mode |

---

## Testing Strategy

### Unit Tests (local)
- `test_variant_generator.py` — mock LLM response, verify variant code compiles
- `test_sandbox.py` — forbidden imports rejected, valid code passes
- `test_adoption_manager.py` — mock git repo, verify commit + tag + rollback

### Integration Tests (VPS)
- Full flow with `simple_momentum` → `simple_momentum_fast` variant
- Verify variant appears in `list_strategies()` after adoption
- Verify rollback restores original within 48h
- Verify `strategy_change_log` has 2 entries (adopt + rollback)

### Load Test
- Run `generate-variants` loop 10× — ensure no duplicate names
- Run `validate-variant` on all 5 strategies → should complete < 5 min on VPS

---

## Deliverables Checklist

- [ ] `src/trading_lab/meta/variant_generator.py` (M1)
- [ ] `prompts/strategy_mutation.txt` (M1)
- [ ] `src/trading_lab/meta/sandbox.py` (M2)
- [ ] `src/trading_lab/meta/variant_validator.py` (M3)
- [ ] `src/trading_lab/meta/adoption_manager.py` (M4)
- [ ] `src/trading_lab/meta/watchdog.py` (M5)
- [ ] `src/trading_lab/meta/change_log.py` (M6)
- [ ] 6 CLI commands registered in `cli.py`
- [ ] `strategy_change_log` table in SQLite schema
- [ ] launchd/systemd timer for weekly generation
- [ ] VPS end-to-end test: generate → sandbox → validate → adopt → watchdog → rollback
- [ ] Telegram alerts on adoption/rollback

---

## Open Questions

1. **LLM Provider:** Which model for strategy generation? Claude-Sonnet (best code), DeepSeek-R1 (cheaper), or local llama.cpp? Suggest Claude-Sonnet for quality, DeepSeek for cost.
2. **Variant Storage:** Keep `variants/` in git (audit trail) or `.gitignore` (clean repo)? Suggest commit with `[auto-generated]` tag in message.
3. **Rollback Criteria:** Sharpe degradation of 0.20 enough? Too sensitive? Suggest calibrating from first 10 adoptions.
4. **Human Approval:** Require explicit `--confirm` before adoption, or fully autonomous? Suggest `--auto-adopt` flag (default false for first 4 weeks).

---

> "The agent should be able to explain every mutation it makes — not just what changed, but why the backtest suggested it would help, and what regime it was targeting."
