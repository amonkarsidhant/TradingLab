# Slash Command: /risk
Run a full risk assessment on current portfolio.

## Steps
1. Read current positions:
   ```
   source .venv/bin/activate && python -m trading_lab.cli positions
   ```
2. Read account summary:
   ```
   source .venv/bin/activate && python -m trading_lab.cli account-summary
   ```
3. Check all positions against risk rules:
   - Max 10 positions (current count vs limit)
   - Max 20% per position (each position % of portfolio)
   - 10% minimum cash reserve
   - All stops set at -7% from peak
   - Position check: any at -7% loss from entry
4. Flag violations clearly
5. Suggest corrective actions (trim, cut, rebalance)
6. Generate risk report to `docs/reports/risk-check-$(date +%Y-%m-%d).md`
