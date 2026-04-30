## ADDED Requirements

### Requirement: Hard guardrails enforced at daemon level
The watcher SHALL enforce non-negotiable guardrails defined as module-level constants. These guardrails SHALL NOT be overridable by env vars, config files, or AI instructions.

#### Scenario: Max positions enforced
- **WHEN** a signal would result in more than 10 positions
- **THEN** the watcher SHALL reject it and log

#### Scenario: Max allocation enforced
- **WHEN** a signal would allocate >20% to one position
- **THEN** the watcher SHALL reject it and log

#### Scenario: Min cash enforced
- **WHEN** a signal would reduce cash below 10%
- **THEN** the watcher SHALL reject it and log

### Requirement: Config supports watcher settings
The system SHALL read watcher settings from environment variables.

#### Scenario: Watcher interval loaded
- **WHEN** settings are loaded
- **THEN** T212_WATCHER_INTERVAL (default 300) SHALL be parsed

#### Scenario: Watcher enabled flag
- **WHEN** settings are loaded
- **THEN** T212_WATCHER_ENABLED (default false) SHALL be parsed

#### Scenario: Autonomy tier loaded
- **WHEN** settings are loaded
- **THEN** T212_WATCHER_AUTONOMY_TIER (default 1) SHALL be parsed

### Requirement: Kill switch closes all positions
The watcher SHALL implement a portfolio-level kill switch.

#### Scenario: Kill switch triggers at limit
- **WHEN** portfolio drawdown exceeds kill_switch_pct (default 25%)
- **THEN** the watcher SHALL place market SELL orders for every position

#### Scenario: Kill switch requires manual reset
- **WHEN** kill switch fires
- **THEN** trading SHALL NOT resume until /reset via Telegram

### Requirement: Event audit persisted to SQLite
All watcher decisions SHALL be logged to a `watcher_events` SQLite table.

#### Scenario: Event row inserted
- **WHEN** watcher evaluates a position or takes action
- **THEN** a row SHALL be inserted with ticker, drawdown_pct, action, timestamp
