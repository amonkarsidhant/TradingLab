## ADDED Requirements

### Requirement: Kill switch closes all positions
_See specs/hard-guardrails.md for requirement — this spec covers the Telegram notification integration._

#### Scenario: Kill switch alerts via Telegram
- **WHEN** kill switch fires
- **THEN** the watcher SHALL send: "🚨 KILL SWITCH FIRED — portfolio drawdown at X%. All positions closing."

#### Scenario: Reset command
- **WHEN** a user sends /reset via Telegram
- **THEN** the watcher SHALL clear the kill switch flag and resume monitoring

### Requirement: Drawdown alerts via Telegram
The watcher SHALL send Telegram messages at configurable drawdown thresholds.

#### Scenario: -3% alert
- **WHEN** position drawdown first crosses -3%
- **THEN** send: "⚠️ AAPL -3.1% from peak — check thesis"

#### Scenario: -5% alert
- **WHEN** position drawdown first crosses -5%
- **THEN** send: "🔶 AAPL -5.2% — decision needed"

#### Scenario: -7% alert + auto-stop (Tier 3)
- **WHEN** position drawdown crosses -7% and tier >= 3
- **THEN** place stop AND send: "🛑 AAPL -7.0% — stop placed"

#### Scenario: Alert deduplication
- **WHEN** a position stays at same threshold across polls
- **THEN** no duplicate alert SHALL be sent
