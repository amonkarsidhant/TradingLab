# Sid Trading Lab — Next-Level Architecture

## 1. Current architecture (April 2026)

```
┌──────────────────────────────────────────────────────────┐
│                     CLI (typer)                           │
│  account-summary | positions | fetch-instruments         │
│  run-strategy | daily-journal                            │
└──────────┬───────────────────────────────┬───────────────┘
           │                               │
           ▼                               ▼
┌──────────────────┐              ┌──────────────────┐
│  ExecutionEngine │              │  DailyJournal     │
│  signal → risk   │              │  (reports)        │
│  → broker        │              └──────────────────┘
└──┬───────┬───────┘
   │       │
   ▼       ▼
┌──────┐ ┌──────────────────────────────────────────┐
│ Risk │ │  SnapshotLogger (SQLite)                  │
│Policy│ │  snapshots + signals tables               │
└──────┘ └──────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────┐
│  Trading212Client (REST wrapper)                 │
│  Basic auth, demo-only, dry_run=True default     │
└──────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────┐    ┌──────────────────────────┐
│  MarketData      │    │  Strategies              │
│  Provider        │    │  SimpleMomentum only     │
│  (Protocol)      │    │  return Signal objects   │
│  Static + CSV    │    │  never call broker       │
└──────────────────┘    └──────────────────────────┘
```

### What exists today

| Layer | What | Status |
|---|---|---|
| Config | `Settings` dataclass with env-var safety locks | Complete |
| Broker | `Trading212Client` — read-only API + dry-run orders | Complete |
| Risk | `RiskPolicy` — blocks HOLD, low confidence, oversized qty | Complete |
| Engine | `ExecutionEngine` — signal → risk → broker | Complete |
| Strategies | `SimpleMomentumStrategy` — 1 concrete strategy | Complete |
| Market data | `MarketDataProvider` protocol, `StaticMarketDataProvider`, `CsvMarketDataProvider` | v1 |
| Logging | `SnapshotLogger` — snapshots + signals tables in SQLite | Complete |
| Reporting | `DailyJournal` — markdown report from SQLite log | v1 |
| CLI | 5 commands via typer | Complete |
| Tests | 67 tests, 8 test modules | Complete |
| Safety | `DEMO_ORDER_CONFIRM` + `T212_CONFIRM_LIVE` confirm strings | Complete |

## 2. Lessons from sibling projects

### 2a. FinceptTerminal (Fincept-Corporation)

**What it is**: An open-source Bloomberg-terminal alternative — Python + C++/Qt6 desktop app with 37 AI agents, 100+ data connectors, 16 broker integrations. ~17,500 GitHub stars. AGPL-3.0.

**What we can adopt**:

- **SQLite for local caching** — FinceptTerminal uses SQLite extensively for instrument metadata and market data caching. We already use SQLite for logging; extending it for instrument and price caching is natural.
- **Agent personas as analysis lenses** — Their 37 AI agents each embody a specific investment philosophy (Buffett, Graham, Lynch). This is the same pattern we want: agents that look at the same data through different frameworks.
- **Node editor for workflow visualisation** — Signals that the future is visual workflow composition. Not urgent for us, but worth tracking.

**What we should avoid**:

- **C++/Qt6 desktop UI** — Over-engineered for a one-person lab. A CLI + markdown reports is the right UX for us.
- **16 broker integrations** — We have one broker (T212). Premature abstraction. Add brokers only when needed.
- **AI agents calling trading APIs directly** — Their design appears to blur the agent/broker boundary. Our rule (strategies return Signals, engine decides) is safer.

### 2b. Kronos (two unrelated projects)

**Kronos CLI** (`backtesting-org/kronos`): A Go-based low-code trading framework. Plugin architecture with per-strategy process isolation, Unix socket IPC, TUI.

- **Process isolation is overkill for a one-person lab** but the idea of one strategy = one hermetic unit is good. Our strategies are already isolated classes that only return Signals.
- **Hot-reload of strategies** is a nice-to-have for iteration speed.

**Kronos foundation model** (`shiyu-coder/Kronos`): A Tsinghua University K-line prediction model trained on 45+ exchanges, accepted at AAAI 2026.

- **Interesting as a future price-forecasting component**, but requires a GPU. Track for Phase 5+, not Phase 1–4.
- The **hierarchical tokenizer** concept (quantizing OHLCV into discrete tokens) is elegant — a price representation we could use when we add ML forecasting much later.

### 2c. TradingAgents (TauricResearch)

**What it is**: A multi-agent LLM trading framework built on LangGraph, modelling a trading firm hierarchy. ~54,000 GitHub stars.

**Architecture**: 4 tiers — Analyst Team (fundamentals, sentiment, news, technical) → Researcher Team (bullish/bearish debate) → Trader Agent → Risk Management + Portfolio Manager.

**What we can adopt**:

- **Adversarial debate as quality control** — The bullish/bearish researcher pair is the standout pattern. Two agents forced to argue opposite sides before any signal is generated. This directly maps to our Multi-Agent Review phase.
- **Hierarchical specialisation** — Splitting analysis into fundamentals, sentiment, news, and technical channels is proven. We don't need 4 analyst agents yet, but the pattern is validated.
- **Decision log with performance tracking** — TradingAgents stores completed decisions, computes realised returns vs SPY, and injects lessons into future prompts. This is our signal journaling + shadow account combined.
- **Provider abstraction for LLMs** — TradingAgents supports 10+ LLM backends. We should ensure our agent layer is provider-agnostic from day one.

**What we should avoid**:

- **LangGraph dependency** — Powerful but adds significant complexity. For a one-person lab, a simple sequential pipeline (analyze → debate → decide → risk-check) is sufficient.
- **LLMs making final trade decisions** — In TradingAgents, the Trader Agent determines timing, direction, and sizing. In our system, the LLM advises, but the human reviews. The risk layer should be deterministic, not LLM-based.
- **Non-deterministic outputs accepted as normal** — TradingAgents explicitly warns about non-determinism. For us, strategy logic must be deterministic and reproducible. LLMs can advise on strategy selection, but execution must be repeatable.

### 2d. Vibe-Trading (HKUDS)

**What it is**: An AI-powered multi-agent finance workspace. ReAct agent loop + 71 skills + 27 tools + DAG-based swarm orchestration + React frontend. ~2,350 GitHub stars.

**What we can adopt**:

- **Self-evolving skills as a concept** — Agents can create, patch, and delete their own workflows stored as SKILL.md files. For us, this translates to: agents that can propose strategy parameter adjustments based on backtest results.
- **Universal data fallback** — Vibe-Trading chains through yfinance, OKX, and AKShare so the system works with zero API keys. Our market data layer should follow the same pattern: free tier first, paid providers as opt-in.
- **Shadow accounting** — This is the most innovative feature: extracting strategy rules from broker journals, backtesting the extracted rules, and producing an 8-section report measuring rule violations, early exits, missed signals, and counterfactual trades. This is exactly what we want from our Shadow Account phase.
- **Multi-platform export** — Vibe-Trading exports to TradingView Pine Script, TDX, and MT5. For us, markdown reports and CSV exports are sufficient for now, but the pattern of strategy-as-portable-artifact is correct.
- **Tool-calling reliability as model selection criterion** — Their explicit tiering of LLMs by tool-use reliability rather than raw intelligence is pragmatic. Cheap models that hallucinate answers instead of calling tools are worse than expensive models that use them correctly.

**What we should avoid**:

- **React frontend** — Unnecessary for a one-person lab. CLI + markdown reports + optionally a static HTML dashboard is the right UX.
- **71 skills** — Massive surface area. We need 5–10 focused capabilities, not a kitchen sink.
- **MCP server** — Vibe-Trading exposes 22 tools via MCP for Claude Desktop integration. This is interesting long-term but adds complexity we don't need yet.
- **Docker as default** — Local venv + pip is simpler for a single-machine lab. Docker makes sense only when we add scheduled/cron execution.

## 3. Target architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     HUMAN OPERATOR                               │
│          reviews every signal, approves every action             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLI + DAILY JOURNAL                           │
│  run-strategy | backtest | daily-journal | shadow-report        │
│  multi-agent-review | dashboard                                  │
└──────────┬──────────────────────────────┬───────────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────┐            ┌─────────────────────────────────┐
│  ExecutionEngine │            │  Reporting Layer                │
│  (unchanged)     │            │  DailyJournal | BacktestReport  │
│  signal→risk→    │            │  ShadowReport | DashboardJSON   │
│  broker          │            └─────────────────────────────────┘
└──┬───────┬───────┘
   │       │
   ▼       ▼
┌──────┐ ┌──────────────────────────────────────────────────────┐
│ Risk │ │  SnapshotLogger (SQLite)                              │
│Policy│ │  + shadow_accounts table                             │
│      │ │  + backtest_runs table                               │
└──────┘ └──────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Broker Abstraction (unchanged)                                  │
│  Trading212Client — demo-only, dry_run=True default              │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Market Data Layer v2                                            │
│  MarketDataProvider protocol + OHLCV fetcher + local cache        │
│  Sources: yfinance (free) → CSV → future paid providers           │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Strategy Layer                                                  │
│  SimpleMomentum | MovingAverageCrossover | MeanReversion         │
│  All return Signal objects. Never call broker.                   │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Backtest Engine v1                                              │
│  Walk-forward backtest | signal-level metrics                   │
│  equity curve | drawdown | Sharpe | win rate                     │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Multi-Agent Review v1                                           │
│  Analyst → Bull/Bear Debate → Risk Reviewer → Summary            │
│  Provider-agnostic (Anthropic, OpenAI, Ollama, OpenRouter)       │
└──────────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Shadow Account v1                                               │
│  Tracks what would have happened vs what did happen              │
│  Measures: signal drift, missed entries, early exits             │
└──────────────────────────────────────────────────────────────────┘
```

### Key architectural invariants

1. **Strategies never call brokers.** They receive prices, return Signals.
2. **Agents advise, risk layer decides.** The deterministic risk policy is the final gate before any broker call.
3. **Every signal is logged.** SQLite is the system of record.
4. **Every decision is reviewable.** Daily journal, backtest reports, shadow reports — all point back to the log.
5. **The human is the final decision-maker.** No autonomous order execution, ever.
6. **Demo-first, always.** Live trading requires multiple confirm strings and explicit human approval.

## 4. Phased roadmap

### Phase 1: Foundation (COMPLETE)

| Block | Item | Commit |
|---|---|---|
| — | Repo Hygiene Fix Pack 1 | `58e3d86` |
| 1 | Config safety tests | `d6d14d3` |
| 2 | Auth header + tests | `efd64f8` |
| 3 | Demo connectivity verification | `26cdb9a` |
| 4 | SQLite snapshot logging | `0d3a3d8` |
| 5 | Signal journaling | `0d3a3d8` |
| 6 | Snapshot flags on CLI commands | `0d3a3d8` |
| 7 | Engine safety tests | `0d3a3d8` |

### Phase 2: Data & safety hardening (COMPLETE)

| Block | Item | Commit |
|---|---|---|
| — | Market Data Layer v1 (protocol, static, CSV) | `92edf92` |
| — | Personal Trading Journal v1 | `16932f4` |
| — | Safety Hardening Pack 2 (DEMO_ORDER_CONFIRM) | `b1ce93d` |

### Phase 3: OHLCV & strategies (NEXT)

| # | Deliverable | Details |
|---|---|---|
| 3.1 | OHLCV Market Data v2 | yfinance integration, OHLCV DataFrame format, local SQLite price cache, auto-fallback to CSV, `--source yfinance` CLI flag |
| 3.2 | MovingAverageCrossover strategy | SMA fast/slow crossover, configurable periods, tests with static data |
| 3.3 | MeanReversion strategy | Bollinger Bands or RSI-based, configurable thresholds, tests |
| 3.4 | Strategy registry | Auto-discovery of strategies, `list-strategies` CLI command |

### Phase 4: Backtest engine

| # | Deliverable | Details |
|---|---|---|
| 4.1 | BacktestEngine v1 | Walk-forward backtest, signal-level P&L tracking, equity curve generation, drawdown calculation |
| 4.2 | Metrics | Sharpe ratio, win rate, max drawdown, profit factor, total return |
| 4.3 | Backtest report | Markdown report with metrics table + equity curve as ASCII/CSV |
| 4.4 | CLI: `backtest` command | `--strategy`, `--ticker`, `--from`/`--to`, `--output` |

### Phase 5: Multi-agent review

| # | Deliverable | Details |
|---|---|---|
| 5.1 | Agent framework | Provider-agnostic agent runner (Anthropic, OpenAI, Ollama, OpenRouter), prompt templates, structured output parsing |
| 5.2 | Analyst agents | Technical analyst + fundamentals/sentiment analyst (2 agents minimum) |
| 5.3 | Bull/Bear debate | Adversarial researcher pair, structured debate format, consensus/split output |
| 5.4 | Risk reviewer agent | Reviews signal against risk policy, flags concerns, suggests position size adjustments |
| 5.5 | CLI: `review-signal` command | Takes a signal, runs agent pipeline, prints review |
| 5.6 | Agent review journaling | All agent outputs logged to SQLite for audit trail |

### Phase 6: Shadow account

| # | Deliverable | Details |
|---|---|---|
| 6.1 | ShadowAccount | Tracks virtual portfolio that strictly follows strategy signals, compares against actual T212 positions |
| 6.2 | Drift metrics | Signal adherence %, missed entry count, early exit count, overtrading score |
| 6.3 | Shadow report | Markdown report comparing shadow vs actual, behavioural gap analysis |
| 6.4 | CLI: `shadow-report` command | `--strategy`, `--from`/`--to`, `--output` |

### Phase 7: Dashboard & reports

| # | Deliverable | Details |
|---|---|---|
| 7.1 | Static HTML dashboard | Single-file HTML with embedded JSON data, equity curves, signal calendar heatmap, strategy comparison table. No server needed — open in browser. |
| 7.2 | Weekly summary report | Aggregated journal covering a full trading week |
| 7.3 | Strategy comparison | Side-by-side metrics for all active strategies |

## 5. What we will NOT build (yet)

| Item | Why not |
|---|---|
| **Live trading** | 30-day sprint rule. Must complete demo validation, backtesting, shadow accounting, and multi-agent review first. Even then, requires explicit human approval. |
| **Autonomous order execution** | Violates the core principle: AI suggests, human decides. This is non-negotiable. |
| **HFT / sub-second trading** | Wrong domain. This is a research and strategy lab, not a low-latency execution system. |
| **Complex ML forecasting** | Kronos-level foundation models require GPUs and massive datasets. Simple technical indicators + agent review is the right complexity for now. ML forecasting can be revisited in Phase 8+. |
| **Large GUI / desktop app** | CLI + markdown reports + static HTML dashboard is the right UX for a one-person lab. FinceptTerminal-level Qt6 desktop app is over-engineered for our needs. |
| **Multi-broker support** | We have one broker (T212). Abstract only when a second broker is needed. |
| **Real-time WebSocket streaming** | Daily/weekly decision cadence, not tick-by-tick. Batch processing is sufficient. |
| **Docker / Kubernetes deployment** | Single-machine lab. Local venv is simpler and faster to iterate on. |

## 6. Design principles

1. **Demo-first.** All execution targets the Trading 212 demo environment. Live trading requires multiple explicit confirm strings and human approval.

2. **Evidence-first.** No strategy is deployed — even in demo — without backtest results, documented assumptions, entry/exit conditions, stop-loss concept, position sizing logic, and risk notes.

3. **Strategies never call brokers.** Strategies receive price data, return `Signal` objects. Only the `ExecutionEngine` calls the broker, and only after the risk policy approves.

4. **Agents advise, risk layer decides.** LLM agents can analyze, debate, and recommend. The deterministic `RiskPolicy` is the final gate. No LLM output directly becomes a broker call.

5. **Every signal is logged.** The `SnapshotLogger` records every signal with its approval decision, dry-run status, and rationale. The SQLite database is the system of record.

6. **Every decision is reviewable.** Daily journals, backtest reports, shadow reports, and agent review transcripts all point back to the log. Any decision can be reconstructed and questioned.

7. **No secrets in Git.** API keys, secrets, and credentials live in `.env` (gitignored). `.env.example` shows the structure without values. SSH keys in the repo directory are gitignored.

8. **No live order without explicit human approval.** Live trading requires `T212_ALLOW_LIVE=true`, `T212_CONFIRM_LIVE=I_ACCEPT_REAL_MONEY_RISK`, and explicit human approval per order. This is enforced in code, not just in documentation.

9. **Readable, boring, testable Python.** No clever abstractions. No metaprogramming. No framework for its own sake. A function is better than a class. A class is better than a hierarchy. Three similar lines is better than a premature abstraction.

10. **The human is the edge.** The system's purpose is to produce structured, evidence-backed information for a human to review. It does not replace human judgment — it sharpens it.
