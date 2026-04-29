# Skill: Trading Operations

## Description
Execute trading system commands safely with built-in guardrails.

## Commands

### Get Account Summary
```
python -m trading_lab.cli account-summary
```
Returns cash, total value, invested value, unrealized P&L.

### Get Positions
```
python -m trading_lab.cli positions
```
Returns all open positions with quantities and prices.

### Run Strategy Scan
```
python -m trading_lab.cli run-strategy --ticker <TICKER> --strategy <STRATEGY>
```
STRATEGY: simple_momentum, ma_crossover, mean_reversion

### Place Demo Order
```
python -m trading_lab.cli place-demo-order --ticker <TICKER> --quantity <QTY> --confirm true
```
Requires --confirm true. Only works in demo mode.

### Run Backtest
```
python -m trading_lab.cli run-backtest --ticker <TICKER> --data-source static
```

### Generate Reports
```
python -m trading_lab.cli daily-journal
python -m trading_lab.cli weekly-report --date today
python -m trading_lab.cli strategy-comparison --ticker <TICKER> --data-source static
python -m trading_lab.cli dashboard --data-source static --output <PATH>
```

## Safety Rules
- Never place orders without explicit confirmation
- Always verify demo mode before trading
- Rate limit: max 1 account summary request per 5 seconds
