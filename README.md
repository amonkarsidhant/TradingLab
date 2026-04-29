# Sid Trading Lab

A demo-first supervised trading research and strategy lab.

All execution runs against the Trading 212 demo environment. Live trading is
blocked by default and must not be enabled until the system has passed manual
review, backtests, paper-trading logs, and risk checks.

## Purpose

This is not an autonomous trading bot.

It is a disciplined research and strategy lab that helps you:

1. Understand market data and instruments.
2. Build and document simple strategies.
3. Backtest those strategies against historical data.
4. Paper trade in Trading 212 demo mode.
5. Record every decision and signal in GitHub.
6. Review signals and decisions with AI assistants.
7. Only after manual review, decide whether demo paper-trading should continue.

## Tool roles

| Tool | Role |
|---|---|
| ChatGPT / OpenAI | Sparring partner, architecture, review, risk critique, strategy explanation |
| Claude Code | Primary coding agent inside this repo |
| Ollama Pro | Local/Cloud model experiments, summarisation, offline-ish review, low-cost repeated analysis |
| GitHub | Source of truth, history, experiment log, decision journal |
| Trading 212 Demo API | Paper trading execution and account/instrument data |

## Safety rule

For the first 30 days:

```text
T212_ENV=demo
T212_ALLOW_LIVE=false
ORDER_PLACEMENT_ENABLED=false
```

Do not put live API credentials into this repo.

## Quick start on macOS

```bash
# 1. Create project
cd ~/Projects
unzip sid-trading-lab.zip
cd sid-trading-lab

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create local environment file
cp .env.example .env
# Edit .env and add your Trading 212 DEMO API key + secret only

# 5. Run tests
pytest

# 6. Check account summary in demo
python -m trading_lab.cli account-summary

# 7. List positions in demo
python -m trading_lab.cli positions

# 8. Run a local dry-run strategy
python -m trading_lab.cli run-strategy --strategy simple_momentum --ticker AAPL_US_EQ --dry-run
```

## GitHub setup

```bash
git init
git add .
git commit -m "Initial Sid Trading Lab scaffold"

# Create an empty GitHub repo named sid-trading-lab, then:
git branch -M main
git remote add origin git@github.com:<your-user>/sid-trading-lab.git
git push -u origin main
```

## Daily journal

Create one file per day under:

```text
docs/journal/day-01.md
docs/journal/day-02.md
...
```

Each day should capture:

- What I tested
- What signal was generated
- Whether I agreed with the signal
- What risk was present
- What I learned
- Whether the strategy should continue, change, or be retired
