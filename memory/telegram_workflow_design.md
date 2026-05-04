━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Telegram Bot — Optimal Workflow Design
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. What "best" means
━━━━━━━━━━━━━━
• Zero stale processes (single polling loop)
• Instant replies (no 5s latency)
• Every command available at a tap (no typing)
• Never lose a message (chunking, retries)
• Failures are loud (throttled alerts)

2. Recommended Architecture
━━━━━━━━━━━━━━━━━━━━━━
┌─────────────────────────────────────┐
│  python-telegram-bot Application      │
│  (one process, one polling loop)      │
│                                      │
│  ├─ CommandHandlers   (/buy, /sell)   │
│  ├─ ConversationHandler (confirm)     │
│  ├─ JobQueue (5 cron jobs)           │
│  └─ CallbackQueryHandler (buttons)   │
└─────────────────────────────────────┘

3. Key Upgrades from Current State
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Switch to PTB JobQueue (not APScheduler)
• Same event loop as bot — no threading conflicts
• Jobs survive bot restarts if persistence enabled
• Built-in misfire_grace_time

Fix ConversationHandler warning
• Add per_chat=True, per_user=True to avoid state leaks

Use Application.run_polling()
• Cleaner lifecycle: run_polling(post_init=..., post_shutdown=...)
• Handles signal termination

Persist state on disk
• SQLite or PicklePersistence for chat/job state

4. Command Hierarchy (set in @BotFather)
━━━━━━━━━━━━━━━━━━━━━━━━━
🗂 Trading
   /status     — Portfolio snapshot
   /positions  — Open positions
   /buy        — Buy (or AUTO)
   /sell       — Sell (or AUTO)
   /scan       — Run Jarvis scan

📊 Reports
   /journal    — Daily journal
   /weekly     — Weekly report
   /dashboard  — HTML chart (file)

📅 Scheduler
   /jobs       — List cron jobs
   /run        — Run a job now
   /logs       — Tail job log

⚙️ System
   /watcher    — Position watcher
   /reset      — Kill switch reset
   /help       — Help menu

5. Confirmation Flow (Buy Example)
━━━━━━━━━━━━━━━━━
User: /buy AAPL 1
Bot:  📥 Buy Preview
      Ticker: AAPL  Qty: 1
      Est. Cost: €178.45
      [✅ Confirm]  [❌ Cancel]

User taps ✅
Bot edits message → "✅ Buy Executed"

If AUTO_APPROVE=true:
Bot skips preview and replies instantly:
"✅ Buy Executed (AUTO)"

6. Menu Button (persistent)
━━━━━━━━━━━━━━━━━━━━━━━━
Set a Menu button that opens /help
BotFather → /setcommands → paste command list
→ Users see a keyboard with all commands, no typing needed

7. Inline Keyboard Patterns
━━━━━━━━━━━━━━━━━━━━━━━━
Use for:
• Order confirm/cancel
• Report navigation (Next / Prev)
• Strategy selection (Simple / MA / Reversion)
• Timeframe filters (1D / 1W / 1M)

Do NOT use for:
• Frequent updates (rate limits)
• Long text (use reply instead)

8. Failure Handling
━━━━━━━━━━━━━━━━━━
Retry: 3 attempts with exponential backoff
Alert: Telegram on 1st failure, every 10th, hourly
Log: Timestamp + exit code + stderr tail

9. Anti-Patterns to Avoid
━━━━━━━━━━━━━━━━━━━━━━
❌ Multiple bot instances (conflict errors)
❌ Markdown for dynamic output (backtick crashes)
❌ Long messages without chunking (>4096 chars)
❌ Unescaped <angle> brackets in HTML mode
❌ Polling without KeepAlive (dies silently)

10. Launchd Checklist
━━━━━━━━━━━━━━━━━━━━
✅ One plist: com.sidtradinglab.unifiedbot
✅ KeepAlive on crash
✅ StdOut/StdErr to logs/
✅ PYTHONPATH set in plist
✅ .venv/bin/python3 as interpreter
✅ .env loaded before bot starts
