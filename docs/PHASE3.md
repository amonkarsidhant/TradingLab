# Phase 3 — Alpha Discovery & Multi-Agent Simulation
> **Status:** BUILD — in progress
> **Estimated Duration:** 12-16 hours focused work
> **Depends:** Phase 1 COMPLETE + Phase 2 COMPLETE
>
## Overview
Phase 3 moves beyond parameter mutation into **novel alpha generation**.
The LLM reads market data (news, earnings transcripts, macro summaries)
and proposes entirely new feature ideas. An auto-engineering pipeline
turns these into quantifiable indicators. A lightweight neural network
tests whether the features have predictive power. Finally, a multi-agent
simulation pits the neural-augmented strategy against existing strategies
on historical data, extracting the winner for Phase 2 adoption.

---

## Milestones

### M1 — Alpha Discovery Engine
**Goal:** LLM reads external data (news, earnings, macro) and proposes
alpha hypotheses — new feature concepts + target regime.

**Files:**
- `src/trading_lab/alpha/discovery.py` — `AlphaDiscoveryEngine`
- `src/trading_lab/alpha/hypothesis.py` — `AlphaHypothesis` dataclass
- `prompts/alpha_discovery.txt` — system prompt template

**How it works:**
1. Fetch recent headlines (yfinance news, RSS, or placeholder)
2. Fetch earnings calendar for watchlist
3. Fetch macro indicators (VIX level, yield curve, Fed dates)
4. LLM prompt: "Given this context, what 3 quantifiable features
   might predict outperformance in the next 2-4 weeks?"
5. Output: list of `AlphaHypothesis` objects with:
   - feature_name, description, suggested_formula, target_regime, confidence

**Safety:**
- No code generation in M1 — only natural language hypotheses
- Confidence scores are LLM-estimated; not used for position sizing

---

### M2 — Feature Engineering Pipeline
**Goal:** Auto-compute indicator combinations from OHLCV + volume.

**Files:**
- `src/trading_lab/alpha/features.py` — `FeatureEngine`
- `src/trading_lab/alpha/feature_set.py` — `FeatureSet` dataclass

**Built-in features (always available):**
| Feature | Formula |
|---|---|
| rsi_14 | RSI(14) |
| rsi_14_x_vol_ma_20 | RSI(14) × Volume MA(20) |
| atr_14_pct | ATR(14) / Close |
| atr_rank_20 | ATR percentile over 20 days |
| price_vs_sma_20 | (Close - SMA20) / SMA20 |
| price_vs_sma_50 | (Close - SMA50) / SMA50 |
| volume_zscore_20 | (Volume - VolMean20) / VolStd20 |
| momentum_5d | (Close - Close[5]) / Close[5] |
| momentum_20d | (Close - Close[20]) / Close[20] |
| bb_width | (UpperBB - LowerBB) / SMA20 |

**From LLM hypotheses:**
- Parse `suggested_formula` into Python expression
- Compile via `eval()` with safe namespace (numpy + pandas functions)
- Compute on historical window
- Store in `FeatureSet` (dict[str, np.ndarray] per ticker)

---

### M3 — Lightweight Neural Signal
**Goal:** MLP classifier on engineered features → BUY/SELL/HOLD probability.

**Files:**
- `src/trading_lab/alpha/neural_signal.py` — `NeuralSignalModel`

**Architecture:**
```
Input: 10 engineered features (normalized)
Hidden: [32, 16] with ReLU
Output: 3-class softmax (BUY=0, HOLD=1, SELL=2)
Loss: CrossEntropy on next-day direction (label = sign of t+1 return)
Training: 500 epochs, Adam, lr=0.001, batch_size=64
Inference: probability > 0.6 → signal with confidence = prob
```

**Constraints:**
- Max 10k parameters (tiny, fast to train)
- Pure numpy implementation (no torch/tf dependency)
- Training time < 5 seconds per ticker per regime window

---

### M4 — Multi-Agent Simulation
**Goal:** Run N strategies simultaneously on same historical data,
tracking equity curves, signals, and collisions.

**Files:**
- `src/trading_lab/alpha/simulation.py` — `MultiAgentSimulation`
- `src/trading_lab/alpha/agent_state.py` — `AgentState` dataclass

**How it works:**
1. Load all registered strategies + 1 neural-augmented strategy
2. For each day in lookback window:
   a. Each agent generates signal for each ticker
   b. Simulation engine resolves conflicts (2+ agents BUY same ticker)
   c. Allocate position proportionally to agent confidence
   d. Track equity curve per agent
3. After window ends: compute Sharpe, max drawdown, win rate per agent

**Collision rules:**
- If 2+ agents signal BUY on same ticker: split position by confidence weight
- Max 1 position per ticker per agent
- Cash reserve 10% enforced globally (not per agent)

---

### M5 — Simulation Analytics
**Goal:** Extract winner from simulation, detect convergence, generate report.

**Files:**
- `src/trading_lab/alpha/analytics.py` — `SimulationAnalytics`

**Outputs:**
| Metric | Description |
|---|---|
| leaderboard | Agents ranked by final equity |
| convergence_day | Day when top-3 agent ranking stabilizes |
| best_agent | Strategy ID of winner |
| best_sharpe | Sharpe of winner |
| alpha_over_baseline | (Winner equity - Baseline equity) / Baseline equity |

**Report:**
- Markdown table of all agents
- Equity curve plot (optional — ASCII or save to file)
- Recommendation: "Adopt [winner] if alpha > 5% and Sharpe > baseline"

---

### M6 — Integration with Meta-Learning
**Goal:** Wire simulation results into Phase 2 variant generator.

**Files:**
- `src/trading_lab/alpha/integration.py` — `AlphaIntegration`

**Flow:**
1. Run simulation → get best_agent
2. If best_agent is neural-augmented: export as `.py` strategy file
3. Run through Phase 2 sandbox + validator
4. If passes: auto-adopt via `AdoptionManager`
5. Log to `strategy_change_log` with `origin = "alpha_discovery"`

**Auto-loop (optional, cron-enabled):**
- Weekly: `discover-alpha` → `engineer-features` → `neural-signal` → `run-simulation`
- If winner beats baseline by >5%: trigger Phase 2 adoption pipeline

---

## CLI Commands

| Command | Args | Description |
|---|---|---|
| `discover-alpha` | `--strategy`, `--limit` | LLM proposes alpha hypotheses |
| `engineer-features` | `--tickers`, `--days` | Compute feature set for tickers |
| `neural-signal` | `--ticker`, `--features`, `--epochs` | Train MLP on features, output signal |
| `run-simulation` | `--agents`, `--tickers`, `--days` | Multi-agent simulation |
| `sim-leaderboard` | `--sim-id` | Show results from last simulation |

---

## Database Schema Additions

```sql
CREATE TABLE IF NOT EXISTS alpha_hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    description TEXT,
    suggested_formula TEXT,
    target_regime TEXT,
    confidence REAL,
    source TEXT  -- 'llm', 'manual', 'simulation'
);

CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    tickers TEXT NOT NULL,
    agents TEXT NOT NULL,
    lookback_days INTEGER,
    best_agent TEXT,
    best_sharpe REAL,
    baseline_sharpe REAL,
    alpha_pct REAL,
    convergence_day INTEGER,
    report_path TEXT
);

CREATE TABLE IF NOT EXISTS simulation_agent_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    final_equity REAL,
    sharpe REAL,
    max_drawdown REAL,
    win_rate REAL,
    trades INTEGER,
    rank INTEGER
);
```

---

## Safety

| Layer | Rule |
|---|---|
| LLM code | M1 produces natural language only — no code |
| Feature eval | `eval()` runs in restricted namespace (numpy + math only) |
| Neural size | Hard cap 10k parameters — no GPU needed |
| Simulation cash | 10% global reserve, enforced in engine |
| Adoption gate | Simulation winner must pass Phase 2 validator before adoption |
| Weekly limit | Max 1 auto-adoption per week (same as Phase 2) |

---

## Acceptance Criteria

- [ ] `discover-alpha` returns ≥1 hypothesis with confidence > 0.5
- [ ] `engineer-features` computes 10 features for SPY in < 5 seconds
- [ ] `neural-signal` trains in < 5 seconds, outputs probability > 0.6
- [ ] `run-simulation` runs 5 agents on 30-day window in < 30 seconds
- [ ] `sim-leaderboard` shows ranked agents with Sharpe + alpha
- [ ] Winner can be exported as `.py` and passes sandbox + validator
- [ ] Integration: full loop `discover → engineer → neural → sim → adopt` works end-to-end
- [ ] All 5 CLI commands registered in `cli.py`
- [ ] All tables created in SQLite on first run
- [ ] VPS synced, imports verified, no import errors

---

## Estimated Hours

| Milestone | Est. |
|---|---|
| M1: Alpha Discovery | 2-3h |
| M2: Feature Engineering | 2-3h |
| M3: Neural Signal | 3-4h |
| M4: Multi-Agent Sim | 3-4h |
| M5: Analytics | 1-2h |
| M6: Integration | 2h |
| **Total** | **13-18h** |
