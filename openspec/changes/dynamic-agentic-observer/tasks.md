## 1. Config & State Infrastructure

- [x] 1.1 Add watcher env vars to `config.py` (WATCHER_ENABLED, WATCHER_INTERVAL, WATCHER_AUTONOMY_TIER)
- [x] 1.2 Add `watcher_events` and `watcher_state` tables to SQLite schema
- [x] 1.3 Add `watcher_state` property to `SnapshotLogger` for peak persistence
- [x] 1.4 Add watcher settings to `.env.example`

## 2. Hard Guardrails Module

- [x] 2.1 Create `src/trading_lab/watcher/guardrails.py` with unmodifiable constants
- [x] 2.2 Implement `GuardrailEnforcer` class
- [x] 2.3 Write unit tests for every guardrail condition

## 3. Autonomy Tier System

- [x] 3.1 Create `src/trading_lab/watcher/tiers.py` with `AutonomyTier` enum
- [x] 3.2 Implement action routing that checks tier before executing

## 4. Watcher Event Loop

- [x] 4.1 Create `src/trading_lab/watcher/loop.py` — main watcher loop
- [x] 4.2 Implement position fetch on each tick
- [x] 4.3 Implement per-position evaluation
- [x] 4.4 Implement 429 backoff with exponential retry

## 5. Telegram Alert Integration

- [x] 5.1 Add `watcher_alert()` method to Telegram bot
- [x] 5.2 Implement threshold deduplication
- [x] 5.3 Implement Tier 1 alerts
- [x] 5.4 Implement Tier 2/3 stop placement
- [x] 5.5 Add `/reset` Telegram command

## 6. Auto Stop-Loss on Entry (Engine Integration)

- [x] 6.1 Modify `ExecutionEngine.handle_signal()` to auto-place stop after non-dry-run BUY fills
- [x] 6.2 Ensure stop is placed at `entry_price * (1 - guardrails.STOP_PCT)` with `GOOD_TILL_CANCEL`
- [x] 6.3 Log stop order ID to the signal result and SQLite

## 7. Kill Switch

- [x] 7.1 Create `src/trading_lab/watcher/kill_switch.py` with portfolio drawdown tracker
- [x] 7.2 Implement `evaluate_portfolio_drawdown(state)`
- [x] 7.3 Implement `fire_kill_switch(broker, positions)`
- [x] 7.4 Persist kill-switch state to SQLite

## 8. Peak Tracking Migration

- [x] 8.1 Move peak tracking from `memory/position_peaks.json` to `watcher_state` SQLite table
- [x] 8.2 Update `PortfolioManager.state()` to read/write peaks from SQLite instead of JSON
- [x] 8.3 Add migration step

## 9. Systemd Daemon

- [x] 9.1 Create `scripts/bull-watcher.service` systemd unit file
- [x] 9.2 Create `scripts/setup-watcher.sh` installer
- [x] 9.3 Add watcher entry point

## 10. Watcher CLI Commands

- [x] 10.1 Add `python -m trading_lab.cli watcher-status` command
- [x] 10.2 Add `python -m trading_lab.cli watcher-log` command

## 11. MCP Tools

- [x] 11.1 Add `get_watcher_status` MCP tool
- [x] 11.2 Add `get_watcher_events` MCP tool

## 12. Deterministic Strategy Integration

- [x] 12.1 Create `src/trading_lab/watcher/strategies.py`
- [x] 12.2 Log agreement/disagreement to `watcher_events`

## 13. Testing & Verification

- [x] 13.1 Write unit tests for `GuardrailEnforcer`
- [x] 13.2 Write unit tests for autonomy tier routing
- [x] 13.3 Write unit tests for kill-switch logic
- [x] 13.4 Write unit tests for peak-to-SQLite migration
- [x] 13.5 Run full test suite and fix any regressions
