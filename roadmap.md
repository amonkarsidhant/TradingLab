# Sid Trading Lab — Autonomous Self-Improving Trading Agent
> Project: sid-trading-lab | Environment: Trading 212 DEMO
> Host: Macbook Air M4 (local) + Azure VPS `eduforengineers` (20.26.196.26)
> Status: **Phase 1 active (meta-learning)** — Phase 0 complete

---

## Vision

Build a **closed-loop trading agent that observes, reflects, hypothesizes, validates, and modifies its own behavior without daily human intervention** — operating within the hard constraints of a demo retail brokerage (T212 REST API, no short, no options, no leverage, max 10 positions).

This is not AGI. It is a **bounded-domain recursively self-improving agent** that:
1. Detects market regime in real time
2. Selects the best strategy for that regime
3. Executes within rigid safety rails
4. Grades every decision against outcome
5. Generates and validates strategy variants
6. Auto-adopts variants that pass statistical gates
7. Logs every cycle to git for audit and rollback

---

## Architecture — The Ouroboros Loop

```
  MARKET DATA          JOURNAL / GRADE       STRATEGY VARIANT
     │                      │                    GENERATOR
     ▼                      ▼                       │
 +--------+           +---------+            +────▼──────+
 │PERCEIVE│──────────▶│ REFLECT │───────────▶│HYPOTHESIZE│
 +--------+           +---------+            +───────────+
     ▲                      │                    │
     │                      │                    ▼
 +───┴────+          +──────▼───────+     +───────────────+
 │POSITION│          │  REGIME      │     │ A/B BACKTEST  │
 │WATCHER │          │  DETECTION   │     │    HARNESS    │
 +--------+          +──────┬───────+     +───────┬───────+
                            │                    │
                            ▼                    ▼
                      +─────────────+       +───────────+
                      │AUTO-SELECT  │◀──────│ VALIDATE  │
                      │  STRATEGY   │       │  / GATE   │
                      +──────┬──────+       +───────────+
                             │
                             ▼
                      +─────────────+
                      │   EXECUTE   │
                      │  (T212)     │
                      +─────────────+
                             │
                             └──────────────────────────────┐
                                    (loop repeats)          │
```

### 7 Immutable Stages

| # | Stage | Input | Output | Current State |
|---|-------|-------|--------|---------------|
| 1 | **Perceive** | Price, news, earnings, sentiment, macro | Clean feature vectors + regime flags | ✅ Live: VIXY + SPY breadth + XLY/XLP rotation |
| 2 | **Decide** | Regime + strategy registry + capital | Signal + position size + route | ✅ Live: StrategySelector with 60% confidence fallback |
| 3 | **Execute** | Order spec + safety checklist | Fill confirmation + slippage log | T212 REST + basic safety rules |
| 4 | **Observe** | Tick-level fills + portfolio delta | Realized P&L, drawdown, Sharpe | Position watcher + SQLite round-trip tracker |
| 5 | **Reflect** | Trade log + regime at entry | Grade (A-F), attribution, not-to-do list | ✅ Daily/Weekly reports now regime-aware |
| 6 | **Hypothesize** | Grade trends + strategy Sharpe by regime | Proposed parameter/strategy variant | Manual strategy comparison (monthly) |
| 7 | **Validate** | Strategy variant + 6m walk-forward | Pass/fail on Sharpe + drawdown gates | Basic backtest engine (single-run) |

---

## Phase Map

### ✅ Phase 0 — Autonomous Regime-Aware Execution Loop (COMPLETE)
**Goal:** The agent runs 24/7 with no manual intervention. It detects regime, picks the right strategy, scans, and auto-trades within demo safety rails.

**Status (2026-05-05):**
- [x] VIX proxy (VIXY ETF) + breadth (% SPY above 50MA) + sector rotation (XLY/XLP ratio) live ingestion
- [x] Regime classifier maps `(vix_level, breadth, trend)` → `regime_id`
- [x] Strategy performance registry tracks Sharpe/win-rate per regime
- [x] Auto-strategy selector chooses highest-Sharpe strategy for current regime
- [x] Unified scheduler+bot runs hourly: detect → select → scan → trade → log
- [x] Regime state + decision logged to SQLite every cycle (`cycles` table)
- [x] `round_trips` table has `regime` column; `signals` table has `regime` column
- [x] EOD reflection reads regime-aware metrics (daily journal + weekly report)
- [x] Signal→RoundTrip bridge propagates regime through the entire pipeline

**Proof it works:** VPS running 5+ days, Telegram alerts hourly, SQLite shows regime transitions, reports show daily regime log + strategy performance by regime.

**Duration:** ~1 day focused build sprint (May 5, 2026)

---

### ✅ Phase 1 — Meta-Learning Engine (COMPLETE)
**Goal:** The agent learns *which strategy to use*, not just running all 3. Capital allocation shifts from fixed 20%/position to strategy-weighted.

**Status (2026-05-05):**
- [x] M1: Strategy sweeper — walk-forward backtest per regime window (`sweeper.py`)
- [x] M2: Seed registry — historical backtest to pre-seed performance table (`seed_registry.py`)
- [x] M3: Capital allocator — Sharpe-weighted position sizing with hard safety rails (`allocator.py`)
- [x] M4: Confidence-based pause — `PAUSE_THRESHOLD=0.40` halts entries when regime confidence low (`selector.PAUSE`)
- [x] M5: A/B harness — statistical comparison with numpy-only Welch t-test (`ab_harness.py`)
- [x] M6: Performance feedback loop — live vs backtest divergence alerts (`performance_feedback.py`)
- [x] Gap 1: HistoricalRegimeDetector for sweeper (not live detection)
- [x] Gap 2: Full breadth computation (45 tickers, batched download)
- [x] Gap 3: Weekly seed-registry cron (launchd local + systemd VPS)
- [x] Gap 4: A/B result persistence to SQLite (`ab_results` table)

**Proof it works:**
- VPS runs `seed_registry.py --days 90` → 5 strategies × 1 regime = 5 results written
- A/B test on SPY: `simple_momentum vs mean_reversion` → `fail` persisted to `ab_results`
- `StrategySweeper` detects `risk_off` window from historical data, backtests correctly

**Duration:** ~1 day (May 5-6, 2026)

---

### ✅ Phase 2 — Self-Modifying Agent (COMPLETE)
**Goal:** The agent generates strategy variants, validates them, and adopts the best one — with rollback if live performance degrades.

**Milestones:**
| # | Milestone | File | Status |
|---|-----------|------|--------|
| M1 | Strategy Variant Generator | `meta/variant_generator.py` | ✅ |
| M2 | Syntax Sandbox | `meta/sandbox.py` | ✅ |
| M3 | Variant Validator | `meta/variant_validator.py` | ✅ |
| M4 | Adoption Manager | `meta/adoption_manager.py` | ✅ |
| M5 | Watchdog | `meta/watchdog.py` | ✅ |
| M6 | Change Log | `meta/change_log.py` | ✅ |

**CLI:** `generate-variants`, `sandbox-test`, `validate-variant`, `adopt-variant`, `rollback-strategy`, `watchdog-check`, `strategy-history`

**Duration:** ~6h focused build sprint (May 5, 2026)

---

### ✅ Phase 3 — Alpha Discovery & Multi-Agent Simulation (COMPLETE)
**Goal:** The agent discovers novel alpha via LLM, engineers quantitative features, trains a lightweight neural signal, then runs multi-agent simulations to find the winner.

**Milestones:**
| # | Milestone | File | Status |
|---|-----------|------|--------|
| M1 | Alpha Discovery Engine | `alpha/discovery.py` | ✅ |
| M2 | Feature Engineering | `alpha/features.py` | ✅ |
| M3 | Neural Signal | `alpha/neural_signal.py` | ✅ |
| M4 | Multi-Agent Simulation | `alpha/simulation.py` | ✅ |
| M5 | Simulation Analytics | `alpha/analytics.py` | ✅ |
| M6 | Integration with Phase 2 | `alpha/integration.py` | ✅ |

**CLI:** `discover-alpha`, `engineer-features`, `neural-signal`, `run-simulation`, `sim-leaderboard`

**Database:** `simulations`, `simulation_agent_results` tables

---

### Phase 4 — Production Hardening (PLANNED)
**Goal:** Security audit, stress testing, paper trading bridge, documentation.

---

## Constraints (Immutable)

| Constraint | Impact | Mitigation |
|---|---|---|
| T212 DEMO only | No real capital at risk ever; fills are synthetic | Acknowledge. Use as learning lab. Migrate to Alpaca/IBKR for realistic execution. |
| REST polling (no websocket) | 5-30s reaction latency, not microsecond | Accept. Swing trading doesn't need HFT. |
| No short selling | Can only learn long alpha | Acknowledge. Long-only momentum/mean-reversion only. |
| No options/derivatives | No gamma/theta/convexity strategies | Acknowledge. Pure equity alpha. |
| Max 10 positions | Limits diversification | Use regime-based concentration instead of sector spread. |
| Max 20%/position | Position sizing ceiling | Use tiered trim logic when approaching limits. |
| yfinance daily data only | No tick-level backtesting | Use polygon.io or Alpaca for tick data when ready. |
| macOS ulimit 256 (fd) | SQLite fd exhaustion at scale | NullRoundTripTracker for sweeps; only live trading persists. |

---

## Infrastructure

| Component | Local (Mac) | VPS (Azure) |
|-----------|-------------|-------------|
| Scheduler/Bot | launchd plist `com.sidtradinglab.scheduler` | systemd unit `bull-telegram-bot-unified` |
| Python | 3.11 venv at `~/.venv` | 3.11 venv at `~/TradingLab/.venv` |
| Data Ingest | yfinance + FMP (optional) | Same (pull from GitHub) |
| Execution | T212 REST API | T212 REST API |
| Notifications | Telegram bot | Telegram bot |
| Memory | SQLite + MemPalace | SQLite only (MemPalace is dev-time) |
| Code | `~/Documents/Projects/sid-trading-lab` | `~/TradingLab` (repo path on VPS) |
| Deploy | `git push` → `git pull --rebase` (VPS uses rebase to avoid merge commit noise) | `git pull origin main --rebase` |
| Access | Local shell + Hermes | SSH `sidhant@20.26.196.26` via sshpass |

---

## Multi-Model Delegation (Lean 4-Agent)

When Hermes supports multiple models or subagents, this is the target layout.

| Agent | Role | Model Profile | Tools |
|-------|------|---------------|-------|
| **Alpha** | Research, scan, backtest, rank | Reasoning-heavy (Claude-Sonnet, DeepSeek-R1, Kimi) | `web_search`, `web_extract`, `execute_code`, file ops |
| **Execution** | Safety gate, sizing, orders | Rule-bound / fast (Haiku, Flash) | T212 CLI, position checks, risk calculator |
| **Journal** | EOD summary, reflection, memory | Analytical / medium (Sonnet, Kimi) | SQLite queries, markdown writer, git commit |
| **DevOps** | Deploy, restart, fix, rotate logs | Fast / cheap (Flash, Haiku) | `terminal`, `ssh`, `systemctl`, `git` |

**Current:** Single Hermes instance (`kimi-k2.6` via `ollama-cloud`) handles all roles. Codex MCP server registered for code tasks. Claude Code v2.1.116 lacks ACP support for native subagents.

---

## Open Improvements (from strategy.md)

These are the known gaps that Phase 0-3 must close:

1. **Trailing stop upgrade** — peak-based instead of entry-based (Phase 0 partially done via watcher)
2. **Profit-taking at +15%** — auto-flag when positions hit target
3. **Position trim logic** — at 10/10, suggest trim X to add Y
4. **Earnings blocking toggle** — `EARNINGS_BLOCK_MISSING=true` to hard-block
5. **Market regime detection** — ✅ VIX proxy / SPY breadth / sector rotation implemented

---

## Log

| Date | Event |
|------|-------|
| 2026-05-04 | Memory files updated (10 open positions, NVDA stopped out, strategy v1.1). SVG diagram fixed for GitHub rendering. |
| 2026-05-05 | Phase 0 build sprint: regime detector, strategy registry, selector, autonomous cycle, hourly bot scheduler, SQLite logging. Phase 0 complete. |
| 2026-05-05 — 06 | Phase 1 build: sweeper, seed registry, allocator, confidence pause, A/B harness, performance feedback, CLI commands. Phase 1 complete + 4 gaps closed. |

---

## How to Update This Roadmap

1. Edit `roadmap.md` locally
2. `git add roadmap.md && git commit -m "docs(roadmap): update phase N milestone"`
3. `git push origin main`
4. `git pull origin main --rebase` on VPS
5. MemPalace re-mine locally (dev only): `.venv/bin/mempalace mine`

---

> "The goal is not to build AGI. The goal is to build the most sophisticated open-source retail trading agent that gets smarter every week — and never puts real money at risk."
