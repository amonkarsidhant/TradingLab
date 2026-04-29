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

# 3. Install dependencies and package
pip install -r requirements.txt
pip install -e .

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

# Create an empty GitHub repo, then add the remote and push.
# SSH (recommended — no password prompts once key is set up):
git branch -M main
git remote add origin git@github.com:amonkarsidhant/TradingLab.git
git push -u origin main

# HTTPS alternative (will prompt for GitHub username + PAT):
# git remote add origin https://github.com/amonkarsidhant/TradingLab.git
```

## Market data

### Important: Trading 212 is not a market data source

The Trading 212 API does not expose a general OHLC / candle historical price
endpoint. It is used here only as the **broker and account API** (positions,
account summary, order placement in later phases).

### Data sources

Four sources are available:

| Source | Flag | Description |
|---|---|---|
| static | `--data-source static` | Built-in deterministic prices. Works offline with no files or keys. |
| csv | `--data-source csv` | Local CSV file with `date,close` columns. |
| yfinance | `--data-source yfinance` | Free Yahoo Finance data. Cached to local SQLite so repeated runs don't hit the network. |
| chained | `--data-source chained` | Tries yfinance → CSV → static in sequence. The first one that succeeds wins. |

The `chained` source is the recommended default for real use — it fetches live
prices when available and falls back gracefully.

### Yahoo Finance cache

Data from Yahoo Finance is stored in a local SQLite file
(`./trading_lab_cache.sqlite3` by default) so each ticker is fetched from the
network at most once per day. The cache is checked before every API call.

### Local CSV price file format

```text
data/market/prices/{ticker}.csv
```

Columns (required): `date`, `close`

```csv
date,close
2026-04-20,100.0
2026-04-21,101.2
2026-04-22,102.1
```

The `data/` directory is gitignored. Create the file manually on your machine.

```bash
mkdir -p data/market/prices
cat > data/market/prices/AAPL_US_EQ.csv << 'EOF'
date,close
2026-04-15,169.50
2026-04-16,171.20
2026-04-17,172.80
2026-04-20,174.10
2026-04-21,175.60
2026-04-22,177.00
EOF
```

### Strategies

```bash
# List all available strategies
python -m trading_lab.cli list-strategies
```

Three strategies are available:

| Name | Logic | Key parameters |
|---|---|---|
| `simple_momentum` | Price % change over lookback window | `--lookback` (default 5) |
| `ma_crossover` | Fast SMA crossing above/below slow SMA | `--fast` (10), `--slow` (30) |
| `mean_reversion` | RSI crossing oversold/overbought thresholds | `--rsi-period` (14), `--oversold` (30), `--overbought` (70) |

### Running a strategy

```bash
# Offline mode — deterministic sample prices (no files or network needed)
python -m trading_lab.cli run-strategy --data-source static --dry-run

# Yahoo Finance — live prices with local cache
python -m trading_lab.cli run-strategy \
  --data-source yfinance \
  --ticker AAPL \
  --dry-run

# Chained — yfinance with automatic fallback
python -m trading_lab.cli run-strategy \
  --data-source chained \
  --ticker AAPL \
  --dry-run

# CSV mode — loads prices from local file
python -m trading_lab.cli run-strategy \
  --data-source csv \
  --ticker AAPL_US_EQ \
  --dry-run

# CSV mode with explicit file path
python -m trading_lab.cli run-strategy \
  --data-source csv \
  --ticker AAPL_US_EQ \
  --prices-file data/market/prices/AAPL_US_EQ.csv \
  --lookback 5 \
  --dry-run

# MA crossover with custom periods
python -m trading_lab.cli run-strategy \
  --strategy ma_crossover \
  --fast 5 --slow 20 \
  --data-source static \
  --dry-run

# Mean reversion with custom RSI thresholds
python -m trading_lab.cli run-strategy \
  --strategy mean_reversion \
  --rsi-period 14 --oversold 25 --overbought 75 \
  --data-source static \
  --dry-run
```

## Backtesting

```bash
# Walk-forward backtest with markdown report
python -m trading_lab.cli backtest --strategy simple_momentum --data-source static

# Backtest with CSV data and a specific output file
python -m trading_lab.cli backtest \
  --strategy ma_crossover \
  --data-source csv \
  --ticker AAPL_US_EQ \
  --output docs/backtests/ma-crossover-AAPL.md

# Backtest with custom capital amount
python -m trading_lab.cli backtest \
  --strategy mean_reversion \
  --data-source static \
  --capital 5000
```

The report covers:

- Performance metrics (total return, CAGR, Sharpe ratio, max drawdown, win rate, profit factor)
- Trade list with entry/exit dates, prices, P&L, and return %
- Signal breakdown (BUY/SELL/HOLD counts)
- ASCII sparkline of the equity curve

**Options**

| Option | Default | Description |
|---|---|---|
| `--strategy` | simple_momentum | Strategy to backtest |
| `--ticker` | AAPL_US_EQ | Ticker symbol |
| `--data-source` | static | static, csv, yfinance, or chained |
| `--capital` | 10000 | Initial capital in account currency |
| `--output` | stdout | Write markdown report to file path |

## Multi-agent review

```bash
# Run the full review pipeline against a signal
python -m trading_lab.cli review-signal \
  --strategy simple_momentum \
  --data-source static

# Review with a specific ticker and write to file
python -m trading_lab.cli review-signal \
  --strategy ma_crossover \
  --ticker AAPL_US_EQ \
  --data-source yfinance \
  --output docs/reviews/ma-crossover-AAPL.md
```

The pipeline runs five agents in sequence:

| Agent | Role |
|---|---|
| Technical Analyst | Evaluates price action, trend, and strategy logic |
| Fundamentals Analyst | Assesses macro context and market conditions |
| Bull Researcher | Makes the strongest case for the signal |
| Bear Researcher | Makes the strongest case against the signal |
| Risk Reviewer | Evaluates position size, drawdown, and risk level |

All agent outputs are journaled to SQLite (`agent_reviews` table) for audit.

**Requires an LLM provider.** Set one of:
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- Ensure Ollama is running (uses `OLLAMA_BASE_URL`, default `http://localhost:11434`)

Override the model with `AGENT_MODEL` (e.g. `claude-sonnet-4-6`, `gpt-5.1`).

## Shadow account

The shadow account compares what a strategy *would have done* (mechanical backtest)
against what you *actually did* (journaled signals). It measures behavioral drift:
missed entries, HOLD overrides, extra signals, and overtrading.

```bash
# Compare strategy backtest against your journaled signals
python -m trading_lab.cli shadow-report \
  --strategy simple_momentum \
  --data-source static

# Filter by date range and write to file
python -m trading_lab.cli shadow-report \
  --strategy ma_crossover \
  --ticker AAPL_US_EQ \
  --data-source yfinance \
  --from-date 2026-04-01 \
  --to-date 2026-04-29 \
  --output docs/shadow/ma-crossover-AAPL.md
```

The report covers:

- **Summary table** — shadow (mechanical) vs actual (journaled) side by side
- **Drift metrics** — signal adherence, missed entries, extra signals, HOLD overrides, overtrading score
- **Behavioral gap analysis** — plain-language notes on what diverged and why
- **Interpretation guide** — how to read each metric and what to do about it

**Options**

| Option | Default | Description |
|---|---|---|
| `--strategy` | simple_momentum | Strategy to use for the shadow backtest |
| `--ticker` | AAPL_US_EQ | Ticker symbol |
| `--data-source` | static | static, csv, yfinance, or chained |
| `--from-date` | (all) | Start date filter for journaled signals (YYYY-MM-DD) |
| `--to-date` | (all) | End date filter for journaled signals (YYYY-MM-DD) |
| `--output` | stdout | Write markdown report to file path |

The shadow does not judge. It just shows what the strategy would have done.

## Daily journal

### Automatic report (generated from the SQLite log)

The `daily-journal` command reads snapshots and signals stored by the logger
and produces a structured markdown report.

```bash
# Print today's report to stdout
python -m trading_lab.cli daily-journal

# Report for a specific date
python -m trading_lab.cli daily-journal --date 2026-04-29

# Write the report to a file
python -m trading_lab.cli daily-journal \
  --date 2026-04-29 \
  --output docs/journal/generated/2026-04-29.md
```

**Options**

| Option | Default | Description |
|---|---|---|
| `--date` | today (UTC) | Date to report on, format `YYYY-MM-DD` |
| `--output` | stdout | File path to write the report to |

The report covers:

- Account snapshots recorded that day (count and types)
- Strategy signals (totals by action, approved vs rejected, dry-run vs live)
- Signal detail table (ticker, action, confidence, reason)
- Top signal reasons by frequency
- Review questions to guide your daily reflection

### Manual journal entries

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
