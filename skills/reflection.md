# Skill: Reflection — Munger-Style Portfolio Introspection
Activated when user asks about reflection, munger, critique, introspection, or grading.

## Core Method
Run Munger Reflection Engine:
```
source .venv/bin/activate && python -m trading_lab.cli reflect
```

## What it does
1. Detects current market regime (bull/bear/ranging/volatile)
2. Critiques every position against:
   - Circle of Competence (do we understand the thesis?)
   - Drawdown danger (-5%+ from peak)
   - Concentration risk (sector overweight)
   - P&L reality check
3. Generates a grade (A-F)
4. Checks the Not-To-Do list for violations

## When to reflect
- Market close daily
- Before opening any new position
- After any position drops -5%
- Weekly review

## Output format
The report includes regime, position-by-position critique, concentration flags, and the not-to-do list. Use it to challenge assumptions and avoid stupid mistakes.
