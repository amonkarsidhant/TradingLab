---
name: bull-trading-lab
description: "Trading 212 demo trading lab — portfolio management, strategy backtesting, Munger reflection, position monitoring, and automated stop/take-profit placement."
version: 1.0.0
author: Sid Trading Lab
license: MIT
metadata:
  hermes:
    tags: [Trading, Finance, Stocks, T212, Demo, Backtesting, Portfolio, Risk-Management]
    category: Trading
    related_skills: []
---

# Bull Trading Lab

Swing trading research lab for Trading 212 DEMO. AI-assisted strategy execution with hard safety guardrails.

## Prerequisites

- Trading 212 DEMO account with API key
- Python 3.10+
- Clone: `git clone https://github.com/amonkarsidhant/TradingLab.git`

## Quick Start

```bash
cd TradingLab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env
# Edit .env — set T212_API_KEY and T212_API_SECRET
```

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `T212_ENV` | `demo` | demo or live |
| `T212_API_KEY` | — | DEMO API key |
| `T212_API_SECRET` | — | DEMO API secret |
| `ORDER_PLACEMENT_ENABLED` | `false` | Master order switch |
| `DEMO_ORDER_CONFIRM` | — | Must be `I_ACCEPT_DEMO_ORDER_TEST` |
| `T212_WATCHER_ENABLED` | `false` | Enable position watcher daemon |
| `T212_WATCHER_AUTONOMY_TIER` | `1` | 1=alerts, 2=alerts+draft, 3=auto-stops |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token for alerts |

### MCP Server (for Hermes Agent)

Add to Hermes config (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  bull-trading-lab:
    command: "python3"
    args: ["-m", "trading_lab.mcp_server"]
    env:
      PYTHONPATH: "/path/to/TradingLab/src"
```

Or run directly:
```bash
cd /path/to/TradingLab
source .venv/bin/activate
python -m trading_lab.mcp_server
```

## Core Commands

```bash
# Account & positions
python -m trading_lab.cli account-summary
python -m trading_lab.cli positions

# Strategy signals
python -m trading_lab.cli run-strategy --ticker AAPL --strategy simple_momentum --data-source chained --dry-run

# Full strategy evaluation (factsheet)
python -m trading_lab.cli strategy-factsheet --strategy simple_momentum --ticker AAPL

# Parameter sweep (find best params)
python -m trading_lab.cli param-sweep --strategy simple_momentum --ticker AAPL

# Rank entry candidates by data (not AI bias)
python -m trading_lab.cli scan-rank --tickers "AAPL,MSFT,NVDA,GOOGL,KO,JNJ"

# Regime-aware cash allocation
python -m trading_lab.cli allocate

# Munger reflection (portfolio grade A-F)
python -m trading_lab.cli reflect

# Place stop order
python -m trading_lab.cli place-stop-order --ticker AAPL_US_EQ --quantity -1 --stop-price 250 --no-dry-run

# Place limit order
python -m trading_lab.cli place-limit-order --ticker AAPL_US_EQ --quantity 1 --limit-price 260 --no-dry-run

# Look up T212 ticker
python -m trading_lab.cli lookup-ticker "Apple"

# Watcher daemon (runs 24/7)
python -m trading_lab.watcher

# Daily journal
python -m trading_lab.cli daily-journal
```

## Safety Architecture

Three-layer safety:
1. **Config locks**: `ORDER_PLACEMENT_ENABLED=false` blocks ALL orders
2. **Pre-trade guard**: Checks max positions (10), cash reserve (10%), demo mode
3. **MCP confirm flag**: Every order tool requires `confirm=true` in the schema

Hard guardrails (cannot be overridden by AI or config):
- Max 10 positions
- Max 20% per position
- Min 10% cash reserve
- Stop-loss REQUIRED on every entry
- No options, no leverage, no crypto, no penny stocks

## Available MCP Tools

| Tool | What it does |
|---|---|
| `get_account_summary` | Account cash, equity, P&L |
| `get_positions` | Open positions with prices |
| `run_strategy` | BUY/SELL/HOLD signal for any ticker |
| `run_backtest` | Walk-forward backtest with metrics |
| `place_demo_order` | Market order (requires confirm=true) |
| `place_stop_order` | Stop order (requires confirm=true) |
| `place_limit_order` | Limit order (requires confirm=true) |
| `lookup_ticker` | Search instruments by name "Apple" → `AAPL_US_EQ` |
| `get_pending_orders` | Active pending orders |
| `cancel_pending_order` | Cancel by ID (requires confirm=true) |
| `run_param_sweep` | Parameter optimization sweep |
| `run_reflection` | Munger portfolio reflection with grade |
| `run_factsheet` | Full strategy evaluation with benchmark |
| `get_recent_signals` | Recent SQLite signal history |
| `get_daily_journal` | Today's activity report |
| `compare_strategies` | Side-by-side strategy comparison |

## Risk & Strategy Notes

- All positions get automatic GTC stop-loss at -7% on entry (with `auto_stop=True`)
- Take-profit limit at +15% for 50% of position (with `auto_take_profit=True`)
- Kill switch closes ALL positions at 25% portfolio drawdown
- Entry scoring ranks candidates by Sharpe, profit factor, parameter stability, and outperformance — not AI comfort
- Market regime detection adjusts position sizing and preferred strategies automatically

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing T212 credentials` | Set `T212_API_KEY` + `T212_API_SECRET` in `.env` |
| `HTTP 401` | Wrong API key or environment mismatch (LIVE vs DEMO) |
| `Order placement is disabled` | Set `ORDER_PLACEMENT_ENABLED=true` + `DEMO_ORDER_CONFIRM=I_ACCEPT_DEMO_ORDER_TEST` |
| `Ticker not found` | Use `lookup-ticker "Company Name"` first |
| Watcher not running | Enable `T212_WATCHER_ENABLED=true` + start daemon |
