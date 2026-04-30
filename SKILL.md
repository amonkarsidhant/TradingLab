---
name: trading-lab
description: "Trading 212 demo trading bot with Munger-style reflection, auto stop-loss, take-profit, position monitoring, and objective entry scoring."
version: 1.0.0
author: Sid Trading Lab
license: MIT
metadata:
  hermes:
    tags: [Trading, Finance, T212, Stocks, Investing, Risk-Management, Automation]
    category: finance
    related_skills: []
    config:
      T212_ENV: demo
      T212_WATCHER_ENABLED: "false"
      T212_WATCHER_AUTONOMY_TIER: "1"
---

# Trading Lab — Bull

AI-powered swing trading assistant for Trading 212 DEMO environment. No real money at risk.

## Quick Start

### Prerequisites
- Trading 212 DEMO account with API key + secret
- Python 3.10+

### Setup
```bash
git clone https://github.com/amonkarsidhant/TradingLab.git
cd TradingLab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
# Edit .env: add T212_API_KEY and T212_API_SECRET (DEMO credentials only)
```

### Verify
```bash
python -m trading_lab.cli account-summary
```

## MCP Server

The lab exposes its full toolset via MCP (stdio transport).

### Register in Hermes

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  trading-lab:
    command: "/path/to/TradingLab/.venv/bin/python"
    args: ["-m", "trading_lab.mcp_server"]
    env:
      PYTHONPATH: "/path/to/TradingLab/src"
    timeout: 60
```

Tools are prefixed with `mcp_trading-lab_*`.

### Available MCP Tools

| Tool | Description |
|---|---|
| `get_account_summary` | T212 account balance, cash, P&L |
| `get_positions` | Open positions with P&L and drawdown |
| `run_strategy` | Generate BUY/SELL/HOLD signal |
| `run_backtest` | Walk-forward backtest with metrics |
| `run_param_sweep` | Test all parameter combinations |
| `run_reflection` | Munger-style portfolio introspection |
| `place_demo_order` | Market order (requires confirm=true) |
| `place_stop_order` | Stop-loss order (requires confirm=true) |
| `place_limit_order` | Limit order (requires confirm=true) |
| `lookup_ticker` | Search instruments by name/symbol |
| `get_pending_orders` | List active stop/limit orders |
| `cancel_pending_order` | Cancel order by ID |
| `get_recent_signals` | Strategy signal history |

## Commands

```bash
# Account
python -m trading_lab.cli account-summary
python -m trading_lab.cli positions
python -m trading_lab.cli pending-orders

# Scanning
python -m trading_lab.cli scan-rank --tickers "AAPL,MSFT,NVDA,GOOGL,AMZN,JNJ,KO"
python -m trading_lab.cli lookup-ticker "Apple"

# Strategy evaluation
python -m trading_lab.cli strategy-factsheet --strategy simple_momentum --ticker AAPL
python -m trading_lab.cli param-sweep --strategy simple_momentum --ticker AAPL --data-source static

# Portfolio management
python -m trading_lab.cli reflect
python -m trading_lab.cli allocate

# Orders
python -m trading_lab.cli place-stop-order --ticker AAPL_US_EQ --quantity -1 --stop-price 250 --dry-run
python -m trading_lab.cli place-limit-order --ticker AAPL_US_EQ --quantity 1 --limit-price 260 --dry-run
```

## Safety Rules

- DEMO environment ONLY. No real money.
- All orders require explicit `--confirm true` flag or `confirm=true` in MCP
- Max 10 positions
- Max 20% of portfolio per position
- Min 10% cash reserve
- Automatic stop-loss at -7% from entry on every buy
- Automatic take-profit limit at +15% for 50% of position
- No options, no leverage, no short selling, no crypto, no penny stocks

## Strategy Metadata

| Strategy | Category | Regime | Parameters |
|---|---|---|---|
| simple_momentum | momentum | bull_trending | lookback=5, threshold_pct=1.0 |
| ma_crossover | trend | bull_trending | fast=10, slow=30 |
| mean_reversion | mean_reversion | ranging_calm | period=14, oversold=30, overbought=70 |
| sentiment | sentiment | any | fear_threshold=20, greed_threshold=80 |
