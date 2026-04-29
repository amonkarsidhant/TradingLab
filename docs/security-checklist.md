# Security Checklist

This checklist applies at all times during the 30-day sprint and beyond.

## Credentials

- [ ] `.env` is never committed to Git (it is listed in `.gitignore`)
- [ ] API keys are demo-only; no live keys exist in this repo or environment
- [ ] `T212_API_KEY` and `T212_API_SECRET` are set only in `.env`, never hardcoded
- [ ] No API key or secret is ever pasted into a chat interface (Claude, ChatGPT, or any other)
- [ ] If an API key is ever exposed (commit, log, chat), rotate it immediately via Trading 212 Settings → API

## Live trading locks

- [ ] `T212_ENV=demo` in `.env` (never `live` during the sprint)
- [ ] `T212_ALLOW_LIVE=false` in `.env`
- [ ] `ORDER_PLACEMENT_ENABLED=false` in `.env`
- [ ] `T212_CONFIRM_LIVE` is blank in `.env`
- [ ] No code change removes or bypasses these checks in `config.py`

## Git hygiene

- [ ] `.gitignore` covers: `.env`, `.claude/`, `*.sqlite3`, SSH keys, `data/`, `*.log`
- [ ] `git status` shows no `.env` or credential files as tracked or staged
- [ ] `git log --all -- .env` returns no results
- [ ] `settings.local.json` and other Claude session files are not tracked

## Code safety

- [ ] All `market_order()` calls default to `dry_run=True`
- [ ] Strategy classes return `Signal` objects only — they do not call broker methods
- [ ] The execution engine (`engine.py`) is the only layer that calls the broker
- [ ] Every new strategy includes assumptions, entry/exit conditions, stop-loss, and position sizing

## Before any real API call

- [ ] Demo API key is added to `.env` manually (not via Claude)
- [ ] `python -m trading_lab.cli account-summary` runs without errors
- [ ] Output is inspected manually before any further automation

## Key rotation

If any key is ever exposed:

1. Go to Trading 212 app → Settings → API → Revoke the key immediately.
2. Generate a new demo key.
3. Update `.env` locally.
4. Confirm the old key is revoked (re-test the old key returns 401).
5. Document the incident in `docs/journal/`.
