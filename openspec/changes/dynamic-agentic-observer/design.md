## Context

The trading lab currently has AI-driven intelligence (Munger reflection, regime detection, parameter sweeps) but zero agency. go-trader proves that deterministic strategy execution + persistent event loop + hard risk guardrails is a working architecture. The lab needs both: mechanical execution with AI judgment on top.

Current state:
- Stop orders exist in `Trading212Client` but are never auto-placed
- Reflection Engine exists at `agentic/reflection.py` but runs only on-demand
- PortfolioManager tracks peaks in JSON but doesn't monitor them
- RiskPolicy has `stop_hit()` method but nothing calls it
- Telegram bot exists but has no alert/notification capability for watcher events

## Goals / Non-Goals

**Goals:**
- Persistent position watcher daemon (systemd-managed)
- Hard guardrails enforced at daemon level (unmodifiable by config or AI)
- Auto stop-loss placement on every entry
- Telegram alerts at drawdown thresholds (-3%, -5%, -7%)
- Portfolio kill switch at configurable drawdown limit (default 25%)
- All events persisted to SQLite
- Support three autonomy tiers: (1) alert only, (2) alert + draft orders, (3) auto-execute stops only

**Non-Goals:**
- Automated entry (every new trade still requires human confirmation)
- AI-driven exit decisions (the watcher is mechanical — judgment exits still go through Bull)
- Multi-asset or portfolio-level strategy optimization
- Replacing the existing agentic flow (Bull still makes the intelligence decisions)

## Decisions

### Decision 1: Pure Python daemon (not Go)

go-trader uses Go for its scheduler. However, the lab is already pure Python and T212 API is REST-only (no WebSocket). A Python process polling every 5 minutes uses negligible resources (~8MB idle). No need for a Go binary — the existing systemd infrastructure already works.

**Alternative considered**: Go binary. Ruled out because it adds build step and the T212 API has no streaming data, so there's no latency advantage.

### Decision 2: Hard guardrails as compile-time constants in Python

Rather than env vars or config (which could be changed), the guardrails are defined as module-level constants in the watcher module. No env var can override them. This is the Python equivalent of "compiled in."

**Alternative considered**: A separate config file. Ruled out because the entire point is that the AI cannot modify them even if told to.

### Decision 3: Watcher reads state from T212 API, not local DB

The watcher polls T212 directly rather than reading from the local SQLite log. This prevents desync between what Bull *thinks* the portfolio is and what it *actually* is. The watcher is the source of truth for position state.

### Decision 4: Kill switch places market orders sequentially with rate-limit spacing

When the kill switch fires, each position close needs a separate T212 API call (1 req/1s for positions, 50 req/min for orders). With 10 max positions, this takes ~10 seconds — acceptable for a swing trading system.

### Decision 5: Three autonomy tiers, configured via env var

| Tier | Stops | Alerts | Kill Switch |
|---|---|---|---|
| 1 (default) | None (alert only) | All thresholds | None (alert only) |
| 2 | Alert + draft stop | All thresholds | None (alert only) |
| 3 (full) | Auto-place | All thresholds | Auto-close at limit |

Tier is set via `T212_WATCHER_AUTONOMY_TIER` env var. Default is Tier 1 — always safe.

### Decision 6: Peak tracking moves from JSON to SQLite

Currently `memory/position_peaks.json` tracks peaks. The watcher needs atomic, concurrent-safe peak storage. Moving to SQLite (`watcher_state` table) also enables historical peak analysis.

## Risks / Trade-offs

- **Risk**: Config says Tier 1 but user expects Tier 3 → **Mitigation**: Log autonomy tier on every startup. Telegram sends "Watcher active (Tier 1 — alerts only)" on launch.
- **Risk**: Watcher sends too many Telegram alerts → **Mitigation**: Deduplication by threshold. A position at -3.2% across 10 polls sends exactly 1 alert.
- **Risk**: Kill switch places sells, market reverses → **Mitigation**: Kill switch is last resort at -25% portfolio. The stop-loss system handles individual positions at -7%.
- **Risk**: Watcher races with Bull placing an order simultaneously → **Mitigation**: Watcher is read-only for evaluations. Only stop/kill-switch actions write. The risk of concurrent stop + manual stop is harmless (T212 rejects duplicates).
- **Trade-off**: No WebSocket means 5-minute max resolution on drawdown detection. A -7% flash crash could pass before the watcher polls. This is acceptable because T212 exchange-side stop orders (placed on entry) handle intra-cycle protection.
