# Slash Command: /reflect
Run the Munger Reflection Engine — constant portfolio introspection.

## Steps
1. Read current portfolio state from T212
2. Detect market regime (SPY price data)
3. Critique each position (circle of competence, drawdown risk, concentration)
4. Check not-to-do list violations
5. Generate grade (A-F)
6. Write reflection to `docs/reflections/YYYY-MM-DD.md`
7. Log to MemPalace
