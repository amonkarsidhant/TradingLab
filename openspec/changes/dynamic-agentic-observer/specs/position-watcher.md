## ADDED Requirements

### Requirement: Position Watcher polls T212 continuously
The system SHALL run a persistent event loop that polls T212 positions every configurable interval (default 5 minutes) during market hours (Mon-Fri, 9:30-16:00 ET).

#### Scenario: Watcher polls positions on schedule
- **WHEN** the watcher is active and the poll interval elapses
- **THEN** it fetches all open positions via the T212 API and evaluates each against configured thresholds

#### Scenario: Watcher respects market hours
- **WHEN** the current time is outside market hours (weekend or pre/post-market)
- **THEN** the watcher SHALL skip polling and log "outside market hours"

#### Scenario: Watcher handles API rate limits
- **WHEN** the T212 API returns a 429
- **THEN** the watcher SHALL back off exponentially (min 30s, max 300s) and retry

### Requirement: Hard guardrails enforced at daemon level
The watcher SHALL enforce a set of non-negotiable guardrails that cannot be modified by config, env vars, or AI instructions. These guardrails are compiled into the watcher binary.

#### Scenario: Guardrails block position count violation
- **WHEN** a trade signal would result in more than 10 open positions
- **THEN** the watcher SHALL reject the signal and log "GUARDRAIL: max positions (10)"

#### Scenario: Guardrails block per-position allocation
- **WHEN** a trade signal would allocate more than 20% of portfolio to one position
- **THEN** the watcher SHALL reject the signal and log "GUARDRAIL: max allocation (20%)"

#### Scenario: Guardrails block cash reserve violation
- **WHEN** a trade signal would reduce cash below 10% of portfolio
- **THEN** the watcher SHALL reject the signal and log "GUARDRAIL: min cash (10%)"

### Requirement: Automatic stop-loss placement
The watcher SHALL automatically place a GOOD_TILL_CANCEL stop-loss order on T212 for every new entry. The stop SHALL be at entry_price * (1 - stop_loss_pct) where stop_loss_pct defaults to 0.07 (7%).

#### Scenario: Stop placed on new entry
- **WHEN** a new BUY order fills
- **THEN** the watcher SHALL place a stop order at 7% below entry price

#### Scenario: Stop is checked on every poll
- **WHEN** the watcher polls positions
- **THEN** it SHALL verify each position has an active stop order
- **WHEN** no stop exists on a held position
- **THEN** the watcher SHALL place one

### Requirement: Drawdown threshold alerts via Telegram
The watcher SHALL send Telegram alerts at configurable drawdown thresholds: default -3% (yellow), -5% (orange), -7% (red — requires stop).

#### Scenario: -3% alert sent
- **WHEN** a position's drawdown from peak first crosses -3%
- **THEN** the watcher SHALL send a Telegram message: "⚠️ MSFT -3.2% from peak — check thesis"

#### Scenario: -7% triggers auto-stop if missing
- **WHEN** a position's drawdown from peak crosses -7%
- **THEN** the watcher SHALL place a market stop order at -7% if none exists AND notify Telegram: "🛑 MSFT -7.1% — stop placed"

#### Scenario: Alert deduplication
- **WHEN** a position remains at -3% across multiple poll cycles
- **THEN** the watcher SHALL NOT send duplicate alerts for the same threshold crossing

### Requirement: Kill switch closes all positions
The watcher SHALL implement a portfolio-level kill switch that closes all positions when total portfolio drawdown exceeds a configurable limit (default: 25%).

#### Scenario: Kill switch triggers
- **WHEN** portfolio drawdown from peak exceeds kill_switch_pct
- **THEN** the watcher SHALL place SELL orders for every open position AND notify Telegram AND log to SQLite

#### Scenario: Kill switch requires manual reset
- **WHEN** the kill switch has fired
- **THEN** the watcher SHALL NOT resume trading until a human sends /reset via Telegram

### Requirement: Event audit persisted to SQLite
All watcher decisions (polls, alerts, stop placements, kill switch triggers) SHALL be persisted to a `watcher_events` SQLite table.

#### Scenario: Event logged
- **WHEN** the watcher evaluates a position
- **THEN** it SHALL insert a row with ticker, drawdown_pct, action_taken (none/alert/stop-placed/kill-switch), timestamp

---

## MODIFIED Requirements

### Requirement: Engine places stops on entry
_Modified from existing `engine.py` auto-stop behavior_

#### Scenario: Auto-stop on live entry
- **WHEN** the execution engine places a non-dry-run market BUY
- **THEN** it SHALL place a stop order at entry_price * (1 - trailing_stop_pct)
- **THEN** it SHALL log the stop_order_id to SQLite

#### Scenario: Auto-stop skipped for dry-run
- **WHEN** the execution engine processes a dry-run signal
- **THEN** no stop SHALL be placed

### Requirement: Config supports watcher settings
_Modified from existing `config.py`_

#### Scenario: Watcher env vars loaded
- **WHEN** settings are loaded
- **THEN** `T212_WATCHER_INTERVAL` (default 300), `T212_WATCHER_ENABLED` (default false), `T212_WATCHER_AUTONOMY_TIER` (default 1) SHALL be parsed

