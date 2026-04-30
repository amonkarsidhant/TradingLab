# Skill: Risk Management
Activated when user asks about risk, position sizing, stop losses, or portfolio safety.

## Portfolio Rules (Non-negotiable)
1. Max 10 positions total
2. Max 20% of portfolio per position
3. Minimum 10% cash reserve at all times
4. No new position exceeds 15% ideal allocation
5. Cut losers at -7% from peak price

## Stop Loss Protocol
- Trailing stop: -7% from peak price (not entry)
- Auto-adjusts upward as price rises
- Never widen a stop once set
- Hard stop at -7% — no exceptions, no hoping

## Position Sizing Formula
- Ideal position: 10-15% of portfolio value
- Risk per trade: max 20% allocation * 7% stop = 1.4% portfolio risk
- Adjust for market regime: smaller in bear/volatile

## Rebalancing Triggers
- Position > 20% of portfolio: trim to 15%
- Cash < 10%: sell weakest performer
- Any position -7%: full exit
- +15% profit: sell 50%, let rest run

## Daily Risk Check
```
python -m trading_lab.cli account-summary
python -m trading_lab.cli positions
```
