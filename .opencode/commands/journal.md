# Slash Command: /journal
Generate or append to the daily trading journal.

## Steps
1. Generate today's automated journal report:
   ```
   source .venv/bin/activate && python -m trading_lab.cli daily-journal --output docs/journal/$(date +%Y-%m-%d).md
   ```
2. Read the generated report
3. Append manual reflection covering:
   - What was tested today
   - Any signals generated and whether you agreed
   - Risk events or concerns
   - Lessons learned
   - Strategy assessment: continue / change / retire
4. Log entry to MemPalace: `mempalace diary_write`
5. Update `memory/trade_log.md` if positions changed
