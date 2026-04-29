# Trading 212 Agent Skills — Analysis

**Repo:** https://github.com/trading212-labs/agent-skills
**Analysed by:** Claude Code (CTO agent)
**Date:** 2026-04-29
**Status:** Read-only study. Nothing installed. Nothing integrated yet.

---

## 1. What the repo provides

`agent-skills` is a TypeScript plugin that wraps the Trading 212 REST API in a
skills/tool format compatible with AI coding assistants (Claude Code, Cursor,
OpenAI Codex CLI, and others). The plugin itself is thin — `index.ts` contains
only a registration shim (`api.logger?.info?.(...)`) — and all real content lives
in a single 43 KB documentation file:

```
plugins/trading212-api/skills/trading212-api/SKILL.md
```

That file is what gets injected into the AI agent's context. It contains:

- Authentication details
- A complete endpoint reference (15 endpoints)
- Request/response schemas
- curl examples
- Rate limits per endpoint
- Pagination patterns
- Error codes and handling
- Safety guidance

The plugin does **not** contain any order-execution code itself. It is purely a
documentation/schema layer that tells the AI how to call the real T212 REST API.

---

## 2. What Trading 212 capabilities it exposes

All capabilities are against the Trading 212 REST API v0. The plugin supports
both `demo.trading212.com` and `live.trading212.com` base URLs.

Accounts supported: Invest, Stocks ISA.

### Complete endpoint list

| HTTP Method | Path | Operation |
|---|---|---|
| GET | `/api/v0/equity/account/summary` | Account balance, cash, invested value |
| GET | `/api/v0/equity/positions` | All open positions with P&L |
| GET | `/api/v0/equity/metadata/instruments` | Full instrument catalogue |
| GET | `/api/v0/equity/metadata/exchanges` | Exchange schedules and trading hours |
| GET | `/api/v0/equity/orders` | List pending (open) orders |
| GET | `/api/v0/equity/orders/{id}` | Single order by ID |
| GET | `/api/v0/equity/history/orders` | Historical order records (paginated) |
| GET | `/api/v0/equity/history/dividends` | Dividend history (paginated) |
| GET | `/api/v0/equity/history/transactions` | Account transactions (paginated) |
| POST | `/api/v0/equity/history/exports` | Request CSV export |
| GET | `/api/v0/equity/history/exports` | Poll CSV export status |
| **POST** | **`/api/v0/equity/orders/market`** | **Place market order** |
| **POST** | **`/api/v0/equity/orders/limit`** | **Place limit order** |
| **POST** | **`/api/v0/equity/orders/stop`** | **Place stop order** |
| **POST** | **`/api/v0/equity/orders/stop_limit`** | **Place stop-limit order** |
| **DELETE** | **`/api/v0/equity/orders/{id}`** | **Cancel order** |

---

## 3. Read-only capabilities

These endpoints retrieve data. They do not move money or modify positions.

| Endpoint | What it returns | Rate limit |
|---|---|---|
| GET `/account/summary` | Cash, invested, P&L totals | 1 req/5s |
| GET `/positions` | All open positions | 1 req/1s |
| GET `/metadata/instruments` | All tradable tickers + metadata | 1 req/50s |
| GET `/metadata/exchanges` | Trading hours by exchange | 1 req/30s |
| GET `/orders` | Pending orders | 1 req/5s |
| GET `/orders/{id}` | Single order | 1 req/1s |
| GET `/history/orders` | Past orders (paginated) | 50 req/min |
| GET `/history/dividends` | Dividends received | 50 req/min |
| GET `/history/transactions` | Cash transactions | 50 req/min |
| GET `/history/exports` | Poll export status | 1 req/min |

**These are safe to call in demo and are the right starting point for Sid Trading Lab.**

---

## 4. Capabilities that can place, cancel, or modify orders

These endpoints cause **financial effects** if pointed at a live account.

| Endpoint | Effect | Parameters |
|---|---|---|
| POST `/orders/market` | Immediate fill at market price | `ticker`, `quantity` (positive=buy, negative=sell), `extendedHours` |
| POST `/orders/limit` | Resting limit order | `ticker`, `quantity`, `limitPrice`, `timeValidity` |
| POST `/orders/stop` | Stop (trigger) order | `ticker`, `quantity`, `stopPrice`, `timeValidity` |
| POST `/orders/stop_limit` | Stop-limit combination | `ticker`, `quantity`, `stopPrice`, `limitPrice`, `timeValidity` |
| DELETE `/orders/{id}` | Cancel a pending order | `id` (path param) |
| POST `/history/exports` | Generates a CSV export | `dataIncluded`, `timeFrom`, `timeTo` — no financial effect, but generates account data exports |

**Key design note:** The API uses a signed `quantity` field. Positive = buy,
negative = sell. There is no separate `side` parameter. This is a footgun: a
sign error in quantity code would flip the direction of a trade.

---

## 5. Security risks

### 5a. The plugin puts AI in the order path

This is the fundamental risk. The plugin is designed to let an AI agent place
orders on behalf of the user, with no mandatory confirmation step. A
misinterpreted instruction, hallucinated ticker, or prompt-injection attack
could cause real trades.

### 5b. Authentication details

The SKILL.md documents authentication as:

```
Authorization: Basic <base64(API_KEY:API_SECRET)>
```

**Risk:** The current `trading_lab` code follows this same pattern (key:secret
Basic auth). However, the real Trading 212 REST API uses a **single API key**
sent directly in the `Authorization` header — not Basic auth. If the real API
uses `Authorization: <api_key>` (not Base64-encoded), the current auth
implementation is wrong and will return 401. This must be verified against the
official T212 API docs before any live connectivity test.

### 5c. DEMO and LIVE keys are not interchangeable

The API key is environment-specific. If `T212_ENV=live` were ever set alongside
a DEMO key, all requests would fail (401), not silently succeed. This is
actually protective, but the error message could confuse a user into thinking
the fix is to switch to a LIVE key.

### 5d. MiFID II compliance note

The plugin's README explicitly states: _"MiFID II prohibits algorithmic trading
use."_ Automated order placement via AI agents may be legally restricted for EU
users. This is a legal risk, not just a technical one. Sid Trading Lab's
demo-only policy avoids this during the learning phase.

### 5e. Signed quantities as a footgun

Negative quantity = sell. Any code that constructs the `quantity` field must
be reviewed carefully. A bug (e.g., applying `abs()` incorrectly, or
mishandling SELL signals) would reverse the trade direction.

### 5f. Rate limits vary widely

The instruments endpoint allows only 1 request per 50 seconds. Calling it in a
loop (e.g., a strategy that re-fetches instruments on every tick) would hit
rate limits hard.

---

## 6. How Sid Trading Lab should safely learn from it

1. **Use SKILL.md as an API reference only.** It is the most complete
   description of the T212 REST API endpoints available. Read it. Do not
   install or run the plugin.

2. **Do not use the plugin with Claude Code's `/plugin` command.** The plugin
   is designed for autonomous AI order placement. Sid Trading Lab must never
   put an AI in the order execution path.

3. **Verify the auth format.** Before any real API calls, check whether T212
   uses `Authorization: <api_key>` or `Authorization: Basic <base64(key:secret)>`.
   Fix `brokers/trading212.py` accordingly.

4. **Only integrate read-only endpoints first.** The safe sequence is:
   account summary → positions → instruments. No order endpoints until
   paper-trading phase is reviewed manually.

5. **Never pass API keys to a model.** Credentials live in `.env` only.
   Never paste them into chat, never log them, never include them in commit
   context.

---

## 7. What we should integrate later (and when)

| Capability | When | Condition |
|---|---|---|
| GET account summary | Phase 1 (now) | Demo key added to `.env` |
| GET positions | Phase 1 (now) | Demo key added to `.env` |
| GET instruments | Phase 1 (now) | Demo key, respect 1 req/50s limit |
| GET history/orders | Phase 2 | After snapshot logging is built |
| GET history/dividends | Phase 2 | After snapshot logging is built |
| GET history/transactions | Phase 2 | After snapshot logging is built |
| GET exchanges (trading hours) | Phase 3 | When strategy timing matters |
| POST orders/market (demo only) | Phase 4 | After: manual review of all signals, ORDER_PLACEMENT_ENABLED review, explicit human confirmation step |
| DELETE orders/{id} (demo only) | Phase 4 | Alongside order placement |
| Limit/stop/stop_limit orders | Phase 5+ | After market orders are stable and reviewed |
| POST history/exports | Optional | Only for audit/reporting |
| **Any live endpoint** | **Never in 30-day sprint** | **Blocked by T212_ALLOW_LIVE=false** |

---

## 8. What we should avoid

| Item | Reason |
|---|---|
| Installing the plugin via `/plugin marketplace add` | Puts AI in the live order path |
| Using the plugin for autonomous order execution | Against safety rules, potential MiFID II issue |
| Pointing `T212_ENV=live` at any point during the sprint | Core safety rule |
| Re-fetching instruments per tick | 1 req/50s rate limit; cache instead |
| Signing quantity incorrectly (SELL = negative) | Flips trade direction silently |
| Using the SKILL.md auth format without verifying against official T212 docs | Auth may be wrong; verify before first real call |
| Sharing demo API key in Git, logs, or chat | Keys grant account access even in demo |
| Letting an AI model decide final trade actions | Against risk-policy.md; AI suggests, human decides |

---

## Summary verdict

The `agent-skills` repo is a useful reference for the T212 REST API surface. Its
SKILL.md is the most comprehensive endpoint documentation available. However, the
plugin as a whole is designed for **AI-autonomous order placement**, which is
exactly what Sid Trading Lab must not do.

**Safe to use:** SKILL.md as a reference document.
**Unsafe to use:** The plugin itself for any live or demo order execution.
**Priority fix for Sid Trading Lab:** Verify and correct the authentication
header format before the first real API call.
