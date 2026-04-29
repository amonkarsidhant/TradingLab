# Prompt for Claude Code

You are working in the `sid-trading-lab` repo.

Goal: build a safe 30-day trading system using Trading 212 demo mode only.

Start by:
1. Reading README.md and CLAUDE.md.
2. Running `pytest`.
3. Reviewing safety locks in `src/trading_lab/config.py` and `src/trading_lab/brokers/trading212.py`.
4. Improving only one thing at a time.

First task:
- Add a command that fetches the list of tradable instruments from Trading 212 demo API and saves it to `data/instruments.json`.
- Do not place orders.
- Add tests where possible.
- Update README.md with the command.
