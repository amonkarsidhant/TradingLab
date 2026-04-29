# Claude Code Instructions — Sid Trading Lab

You are assisting with a local trading system.

## Non-negotiable safety rules

1. Do not enable live trading.
2. Do not write code that bypasses live-trading locks.
3. Do not store API keys, secrets, or account data in Git.
4. Default all execution to Trading 212 demo mode.
5. Any order placement function must require:
   - demo environment, or
   - explicit multi-step live confirmation, which should remain disabled during the first 30 days.
6. Prefer readable, boring, testable Python over clever abstractions.
7. Every strategy must expose:
   - assumptions
   - entry condition
   - exit condition
   - stop-loss concept
   - position sizing logic
   - risk notes
8. Every strategy change must include or update tests.
9. When making changes, update docs/journal or docs/decision-log.md where relevant.

## Coding style

- Use Python 3.10+.
- Keep API code separate from strategy code.
- Never call broker/order functions directly from strategy classes.
- Strategies return `Signal` objects only.
- Execution engines decide what to do with signals.
- Add dry-run mode to all commands that might trade.

## Suggested workflow

1. Inspect current files.
2. Run tests.
3. Make the smallest change.
4. Add tests.
5. Run tests again.
6. Summarize the diff and risks.
