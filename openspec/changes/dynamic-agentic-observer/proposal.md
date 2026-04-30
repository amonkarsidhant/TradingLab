## Why

The trading lab has deep intelligence (Munger reflection, regime detection, parameter sweeps) but zero agency. No automated stop placement, no price watcher, no position monitor. Every position entered since day one remains unguarded — if any dropped -50%, the system would do nothing. The reflection engine can _tell you_ what's wrong, but only if you ask it.

Meanwhile, go-trader (richkuo/go-trader) proves that deterministic strategies + persistent event loop + hard-coded risk guardrails is a proven, working architecture for autonomous trading. The lab needs to merge both approaches: deterministic mechanical execution with AI judgment layered on top, all wrapped in an unbreakable guardrail envelope.

## What Changes

- Add a persistent watch loop daemon that polls positions every N minutes during market hours
- Implement hard guardrails compiled into the watcher (not modifiable by AI or config)
- Wire automatic stop-loss placement on every entry (GOOD_TILL_CANCEL)
- Add real-time Telegram alerts at drawdown thresholds (-3%, -5%, -7%)
- Build a lightweight deterministic strategy runner alongside the AI discretionary system
- Add exchange-level kill switch that closes all positions when portfolio drawdown exceeds limit
- Persist drawdown and trigger events to SQLite for audit

## Capabilities

### New Capabilities
- `position-watcher`: Continuous polling of T212 positions with threshold alerts and auto-stop placement
- `hard-guardrails`: AI-proof safety rules enforced at the binary/daemon level, not markdown
- `kill-switch`: Automatic position close when portfolio drawdown exceeds configured limit
- `deterministic-strategies`: Lightweight indicator-based strategy runner (parallel to AI-discretionary)
- `event-audit`: SQLite-backed log of all watcher decisions, triggers, and actions

### Modified Capabilities
- _(none — all new)_

## Impact

- New daemon: `src/trading_lab/watcher/` directory with ~500 lines of Python
- New systemd unit: `scripts/bull-watcher.service`
- Extended `config.py` with watcher settings (interval, thresholds, autonomy tier)
- Extended `risk.py` with kill-switch logic
- Extended `brokers/trading212.py` with kill-switch close methods
- New SQLite table: `watcher_events`
- Telegram bot extended with watcher alert handlers
