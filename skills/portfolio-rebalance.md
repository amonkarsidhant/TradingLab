# Skill: Portfolio Rebalancing
Activated when user asks about rebalancing, position management, or portfolio allocation.

## Rebalancing Workflow
1. Read current positions and account summary
2. Calculate each position as % of total portfolio value
3. Check against thresholds:
   - Over 20%: trim to 15%
   - 15-20%: monitor, consider trimming
   - Under 10%: consider whether to add or exit
4. Check sector concentration (all tech = high risk)
5. Check cash reserve (must be >= 10%)

## Diversification Targets
- Maximum 50% in any single sector
- Minimum 3 sectors represented
- Target mix: 40% tech, 30% value/defensive, 20% growth, 10% cash

## Rebalance Frequency
- Full review: weekly (Friday)
- Quick check: daily at market close
- Emergency: if any position hits -7% or +15%

## Execution
- Sell weakest performers first (lowest momentum, highest loss)
- Trim overweight positions before adding new
- Place demo orders only with explicit confirmation
