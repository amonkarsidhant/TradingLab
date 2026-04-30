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

## Claude MCP Server (AI Co-pilot)

Connect Claude Desktop directly to your trading lab. This gives Claude tools
to read your account, run strategies, backtest, and place demo orders — all
through natural language prompts.

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install -e .

# 2. Install the MCP server into Claude Desktop
bash scripts/install_mcp.sh

# 3. Restart Claude Desktop
# You should see a hammer icon with 8 trading tools
```

### Available tools

| Tool | What it does |
|---|---|
| `get_account_summary` | Read your T212 demo account (cash, equity, P&L) |
| `get_positions` | List all open positions |
| `run_strategy` | Generate a BUY/SELL/HOLD signal for any ticker |
| `run_backtest` | Run a full walk-forward backtest with metrics |
| `place_demo_order` | Place an order on T212 demo (requires `confirm=true`) |
| `get_recent_signals` | Read your signal journal from SQLite |
| `get_daily_journal` | Generate today's activity report |
| `compare_strategies` | Side-by-side backtest of all 3 strategies |

### Example prompts

```
"Check my demo account balance"
"Run a backtest on NVDA with simple_momentum"
"Compare all strategies on AAPL"
"Place a demo order for 5 shares of AMD"  -- Claude will ask you to confirm
```

### Safety

- `place_demo_order` requires `confirm=true` — Claude cannot place orders without your explicit approval
- All orders go to T212 demo environment only
- `ORDER_PLACEMENT_ENABLED=false` in `.env` blocks all orders
- The MCP server enforces the same safety locks as the CLI

## Strategy comparison

```bash
# Side-by-side metrics for all registered strategies
python -m trading_lab.cli strategy-comparison --data-source static

# With custom capital and ticker
python -m trading_lab.cli strategy-comparison \
  --ticker AAPL_US_EQ \
  --data-source csv \
  --prices-file data/market/prices/AAPL_US_EQ.csv \
  --capital 5000 \
  --output docs/reports/strategy-comparison.md
```

The report covers:

- **Comparison table** — all strategies side-by-side: return, CAGR, Sharpe, max DD, win rate, profit factor, trades, wins, losses
- **Per-strategy details** — full metrics breakdown plus equity sparkline per strategy
- **Journaled signal counts** — what you actually recorded in the DB vs what the backtest shows
- **Interpretation guide** — how to read profit factor, win rate vs return, and strategy fit

**Options**

| Option | Default | Description |
|---|---|---|
| `--ticker` | AAPL_US_EQ | Ticker symbol |
| `--data-source` | static | static, csv, yfinance, or chained |
| `--capital` | 10000 | Initial capital for backtests |
| `--output` | stdout | Write markdown report to file path |

## Strategy Factsheet

Generate a comprehensive research-grade evaluation of any strategy with benchmark comparison, cost sensitivity, and parameter stability analysis.

```bash
# Generate a factsheet for simple_momentum on AAPL
python -m trading_lab.cli strategy-factsheet --strategy simple_momentum --ticker AAPL_US_EQ

# Write to file
python -m trading_lab.cli strategy-factsheet --strategy ma_crossover --ticker AAPL_US_EQ --output docs/factsheets/ma-crossover-apl.md
```

The factsheet includes:

- **Strategy metadata** — category, hypothesis, expected market regime, failure modes, parameters
- **Backtest metrics** — total return, CAGR, Sharpe, max drawdown, win rate, profit factor
- **Benchmark comparison** — strategy return vs buy-and-hold
- **Cost sensitivity** — 4 scenarios from ideal (0/0) to high (1%/0.5%)
- **Parameter stability** — sweep over parameter grid with mean/std/CV and best combo
- **Verdict** — research / watch / reject based on Sharpe, drawdown, trade count, stability

**Options**

| Option | Default | Description |
|---|---|---|
| `--strategy` | simple_momentum | Strategy to evaluate |
| `--ticker` | AAPL_US_EQ | Ticker symbol |
| `--capital` | 10000 | Initial capital for backtests |
| `--output` | stdout | Write markdown report to file path |

## Dashboard

```bash
# Generate a self-contained static HTML dashboard
python -m trading_lab.cli dashboard --data-source static

# Write to file and open in browser
python -m trading_lab.cli dashboard \
  --ticker AAPL_US_EQ \
  --data-source yfinance \
  --output docs/dashboard.html
open docs/dashboard.html
```

The dashboard is a single HTML file — no server, no CDN, no external dependencies.
It renders:

- **Strategy performance table** — color-coded returns for all strategies
- **Equity curves** — Canvas-based multi-line chart comparing all strategies
- **Signal heatmap** — calendar grid showing signal activity per day per strategy
- **Recent signals** — latest 30 signals with time, ticker, action, confidence, reason
- **Account snapshot** — latest account summary from the SQLite log

**Options**

| Option | Default | Description |
|---|---|---|
| `--ticker` | AAPL_US_EQ | Ticker symbol |
| `--data-source` | static | static, csv, yfinance, or chained |
| `--prices-file` | (auto) | Path to CSV price file |
| `--output` | stdout | Write HTML dashboard to file path |

## Weekly report

```bash
# Weekly summary for the current week (Mon-Fri)
python -m trading_lab.cli weekly-report

# Report for a specific week (any date in that week)
python -m trading_lab.cli weekly-report --date 2026-04-29

# Write to file
python -m trading_lab.cli weekly-report \
  --date 2026-04-29 \
  --output docs/reports/weekly-2026-04-27.md
```

The report aggregates one trading week into:

- **Executive summary** — total signals, snapshots, approval rates
- **Daily breakdown** — per-strategy signal counts across Mon-Fri
- **Signal activity by strategy** — BUY/SELL/HOLD breakdown with average confidence
- **Ticker activity** — which tickers were most active that week
- **Snapshots recorded** — what API data was captured

**Options**

| Option | Default | Description |
|---|---|---|
| `--date` | today (UTC) | Any date in the target week (YYYY-MM-DD) |
| `--output` | stdout | Write markdown report to file path
