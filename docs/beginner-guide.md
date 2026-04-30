# Sid Trading Lab — Beginner's Guide

> You don't need to be a programmer or a trader. You just need to follow along.

---

## What is this thing?

A computer program that helps you **practice trading stocks on a fake-money account**.

It connects to **Trading 212** (a real stock broker) but only in **DEMO mode** — meaning you can buy and sell with Monopoly money. No real cash is ever at risk.

The program can:
- Show your account balance and positions
- Scan stocks and tell you "BUY", "SELL", or "HOLD"
- Test strategies against historical data
- Place demo orders (fake buys/sells)
- Generate daily journals and weekly reports

---

## What you need before starting

| Thing | How to get it |
|---|---|
| **Trading 212 DEMO account** | Download the Trading 212 app → create account → switch to DEMO mode |
| **T212 API key & secret** | Inside the app: Settings → API → generate a key pair |
| **Python 3.10+** | Already on your Mac. Open Terminal and type `python3 --version` to check |
| **Terminal app** | Built into your Mac. Press Cmd+Space, type "Terminal", hit Enter |

---

## One-time setup (5 minutes)

### Step 1: Open Terminal

Press `Cmd + Space`, type `Terminal`, press Enter.

### Step 2: Go to the trading lab folder

```bash
cd ~/Documents/Projects/sid-trading-lab
```

### Step 3: Activate the virtual environment

```bash
source .venv/bin/activate
```

You'll see `(.venv)` appear at the start of your prompt. That means you're in.

### Step 4: Create your secret file

```bash
cp .env.example .env
```

### Step 5: Edit the secret file

```bash
nano .env
```

Find these two lines and paste your API key and secret:

```
T212_API_KEY=paste-your-api-key-here
T212_API_SECRET=paste-your-api-secret-here
```

Press `Ctrl+O` to save, `Enter`, then `Ctrl+X` to exit.

> **IMPORTANT**: Never share this `.env` file with anyone. It contains your keys.

### Step 6: Verify it works

```bash
python -m trading_lab.cli account-summary
```

If you see numbers (cash, total value, etc.) — you're connected. If you see an error, check your API keys.

---

## Daily usage

### Every time you open Terminal

```bash
cd ~/Documents/Projects/sid-trading-lab
source .venv/bin/activate
```

Now pick what you want to do from the commands below.

---

## All commands — what they do and when to use them

### Check your account

**Command:**
```bash
python -m trading_lab.cli account-summary
```

**What it shows:** How much cash you have, how much is invested, total value, profit/loss.

**When to use:** Start of every session. Quick health check.

---

### See your positions

**Command:**
```bash
python -m trading_lab.cli positions
```

**What it shows:** Every stock you currently hold — ticker, quantity, current price, profit/loss.

**When to use:** Before buying or selling anything.

---

### Scan a stock for signals

**Command:**
```bash
python -m trading_lab.cli run-strategy --ticker AAPL_US_EQ --strategy simple_momentum --dry-run
```

**What it does:** Runs the momentum strategy on Apple. Tells you BUY, SELL, or HOLD.

**Change the ticker:** Replace `AAPL_US_EQ` with any T212 ticker (e.g., `TSLA_US_EQ`, `NVDA_US_EQ`).

**Change the strategy:**
- `simple_momentum` — "is the price going up?"
- `ma_crossover` — "is the short-term trend crossing above the long-term?"
- `mean_reversion` — "is the stock oversold or overbought?"

**When to use:** Any time you're curious about a stock.

---

### Find a stock's T212 ticker

**Command:**
```bash
python -m trading_lab.cli lookup-ticker "Apple"
```

**What it shows:** The exact ticker Trading 212 uses for "Apple" (which is `AAPL_US_EQ`).

**When to use:** Before running any strategy or placing an order — you need the T212 ticker, not the regular symbol.

---

### Run a backtest (test a strategy on old data)

**Command:**
```bash
python -m trading_lab.cli backtest --ticker AAPL_US_EQ --data-source static
```

**What it does:** Pretends to trade Apple over the last year using your strategy. Shows you how much money you would have made or lost.

**What the report tells you:**
- **Total return** — how much money you'd have made (%)
- **Win rate** — what % of trades were profitable
- **Max drawdown** — biggest drop from a peak (worst-case scenario)
- **Sharpe ratio** — higher = better returns for the risk you took

**When to use:** Before trusting a strategy. If the backtest looks bad, don't use that strategy.

---

### Generate today's journal

**Command:**
```bash
python -m trading_lab.cli daily-journal
```

**What it does:** Creates a summary report of everything that happened today — signals generated, snapshots taken, trades attempted.

**Save it to a file:**
```bash
python -m trading_lab.cli daily-journal --output docs/journal/today.md
```

**When to use:** End of every trading day.

---

### Weekly report

**Command:**
```bash
python -m trading_lab.cli weekly-report
```

**What it does:** Summarizes the entire week's activity.

**Save to file:**
```bash
python -m trading_lab.cli weekly-report --output docs/reports/weekly.md
```

**When to use:** Friday afternoon.

---

### Compare all 3 strategies on one stock

**Command:**
```bash
python -m trading_lab.cli strategy-comparison --ticker AAPL_US_EQ --data-source static
```

**What it does:** Runs all three strategies through a backtest and shows them side-by-side.

**When to use:** Deciding which strategy to trust. Pick the one with the best numbers.

---

### Multi-agent review (AI analyzes a signal)

**Command:**
```bash
python -m trading_lab.cli review-signal --ticker AAPL_US_EQ --data-source static
```

**What it does:** Five AI agents analyze the signal:
1. Technical Analyst — reads the charts
2. Fundamentals Analyst — checks the big picture
3. Bull Researcher — makes the case FOR buying
4. Bear Researcher — makes the case AGAINST buying
5. Risk Reviewer — checks if the trade is safe

**Requires:** An API key for Claude or OpenAI (set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`).

**When to use:** Before making a big decision. Let the AI argue with itself first.

---

### Generate a dashboard

**Command:**
```bash
python -m trading_lab.cli dashboard --output docs/dashboard.html
```

Then open `docs/dashboard.html` in your browser. It shows charts, signals, and account status — all in one page.

**When to use:** Weekly review. Share with friends.

---

## Placing orders (fake money buys/sells)

### Safety first — read this

Orders only work if you've turned them ON in your `.env` file:

```
ORDER_PLACEMENT_ENABLED=true
DEMO_ORDER_CONFIRM=I_ACCEPT_DEMO_ORDER_TEST
```

Until you set both of those, ALL orders will be rejected. This is deliberate — the tool protects you from accidents.

### Market order (basic buy/sell)

```bash
python -m trading_lab.cli run-strategy --ticker AAPL_US_EQ --strategy simple_momentum --dry-run false
```

Setting `--dry-run false` actually places the order. Without it, it just tells you what it WOULD do.

### Stop order (automatic sell if price drops too far)

```bash
python -m trading_lab.cli place-stop-order --ticker AAPL_US_EQ --quantity -1 --stop-price 250 --dry-run false
```

This says: "If Apple drops to €250, sell 1 share automatically."

**Why use this:** Bull's rule is "cut losers at -7%". A stop order does that for you while you sleep.

### Limit order (buy only if cheap enough)

```bash
python -m trading_lab.cli place-limit-order --ticker AAPL_US_EQ --quantity 1 --limit-price 260 --dry-run false
```

This says: "Buy 1 Apple share, but only if the price drops to €260 or less."

### Cancel an order

```bash
python -m trading_lab.cli cancel-order 123456789
```

Replace `123456789` with the actual order ID.

---

## The strategy (what Bull believes)

Bull is a **swing trader** — holds for days or weeks, not minutes.

**Rules Bull never breaks:**
1. Max 10 positions at a time
2. No more than 20% of portfolio in one stock
3. Always keep 10% in cash
4. Cut any stock that drops 7% from its peak — no hoping
5. No crypto, no penny stocks, no options, no borrowing money
6. Never trade in LIVE mode — DEMO only until you know what you're doing

---

## Quick reference card

```
cd ~/Documents/Projects/sid-trading-lab     # go to the lab
source .venv/bin/activate                    # turn it on

python -m trading_lab.cli account-summary    # how much money?
python -m trading_lab.cli positions          # what do I own?
python -m trading_lab.cli lookup-ticker "Tesla"   # find ticker
python -m trading_lab.cli run-strategy --ticker TSLA_US_EQ --strategy simple_momentum --dry-run   # what should I do?
python -m trading_lab.cli backtest --ticker AAPL_US_EQ --data-source static    # would this work?
python -m trading_lab.cli daily-journal       # today's summary
python -m trading_lab.cli weekly-report       # this week's summary
python -m trading_lab.cli dashboard --output docs/dashboard.html   # pretty charts
```

---

## Common problems and fixes

| Problem | Fix |
|---|---|
| `RuntimeError: Missing T212 credentials` | You didn't put your API keys in `.env`. Go do step 5 of setup. |
| `HTTP Error 401` | Your API key or secret is wrong. Check for extra spaces in `.env`. |
| `HTTP Error 401` (again) | You might be using a LIVE key in DEMO mode or vice versa. Keys are environment-specific. |
| `Order placement is disabled` | You need `ORDER_PLACEMENT_ENABLED=true` AND `DEMO_ORDER_CONFIRM=I_ACCEPT_DEMO_ORDER_TEST` in `.env`. |
| `Ticker not found` | Use `lookup-ticker "Company Name"` first. T212 uses weird tickers like `AAPL_US_EQ` not just `AAPL`. |
| Strategy says HOLD for everything | `yfinance` sometimes returns too little data. Try `--data-source static` for testing. |

---

## Next steps (when you're comfortable)

1. Run `/scan` from inside Claude Code or OpenCode to scan your whole watchlist at once
2. Set up the Telegram bot (see `scripts/setup_telegram_bot.sh`) to get alerts on your phone
3. Read `docs/30_day_sprint.md` for the structured 30-day training plan
4. Read `docs/risk-policy.md` if you want to understand WHY the rules exist
