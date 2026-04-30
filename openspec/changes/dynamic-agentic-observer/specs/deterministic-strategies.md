## ADDED Requirements

### Requirement: Deterministic strategies run alongside AI strategies
The system SHALL support running deterministic indicator-based strategies (SMA crossover, RSI, momentum, Bollinger) as a parallel track to the AI-discretionary system. These SHALL use the existing strategy registry and backtest infrastructure.

#### Scenario: Deterministic strategy runs independently
- **WHEN** a deterministic strategy is configured
- **THEN** it SHALL run its own signal generation cycle independent of Bull's analysis

#### Scenario: Results cross-referenced
- **WHEN** both a deterministic and an AI strategy generate signals
- **THEN** the watcher SHALL note agreement/disagreement in the event log

### Requirement: Strategy results compared against AI
Deterministic strategy signals SHALL be logged alongside AI signals for comparison.

#### Scenario: Agreement flagged
- **WHEN** deterministic and AI strategies agree on direction
- **THEN** the event SHALL note "CONSENSUS: both strategies agree"

#### Scenario: Disagreement flagged
- **WHEN** deterministic and AI strategies disagree
- **THEN** the event SHALL note "DIVERGENCE: deterministic=<action>, AI=<action> — review thesis"
