# VPS Deployment Guide — Sid Trading Lab

Deploy your trading lab to a cloud server for 24/7 operation.
Runs the Telegram bot as a systemd daemon. Secured with Tailscale VPN.

---

## What you'll get

- A cloud server running Bull 24/7
- Telegram bot alive even when your laptop is off
- Private VPN: only your devices can access the server
- All strategy scans and journals generated on-schedule

---

## Prerequisites

| Thing | How to get it |
|---|---|
| Hetzner account | [hetzner.com/cloud](https://hetzner.com/cloud) — €4/mo for CPX11 |
| Tailscale account | [tailscale.com](https://tailscale.com) — free tier, up to 100 devices |
| Tailscale on your laptop | `brew install --cask tailscale` then sign in |
| GitHub repo access | Push your lab to a private GitHub repo |
| T212 DEMO API key | Already in your `.env` file |

---

## Step 1: Create the Hetzner server

Go to Hetzner Cloud Console → Create Server.

```
Location:     Helsinki or Frankfurt (low latency to T212 servers)
Image:        Ubuntu 24.04
Type:         CPX11 (2 vCPU, 2 GB RAM, 40 GB disk) — €4/mo
SSH key:      Upload your ~/.ssh/id_ed25519.pub
```

Click **Create & Buy Now**. Wait 30 seconds.

---

## Step 2: Install Tailscale on the server

SSH in:
```bash
ssh root@<YOUR-SERVER-IP>
```

Install Tailscale:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

Copy the auth URL that appears and open it in your browser. Sign in.

Verify your server appears in the [Tailscale admin console](https://login.tailscale.com/admin/machines).

Copy the server's **Tailscale IP** (looks like `100.x.x.x`).

---

## Step 3: Lock the firewall to Tailscale-only

In Hetzner Console → Firewalls → Create Firewall.

Add ONE rule:
```
Direction:  Inbound
Protocol:   UDP
Port:       41641
Source:     0.0.0.0/0
```

Apply this firewall to your server.

Now disconnect and try to SSH using the public IP — it will fail. Good.
SSH using the Tailscale IP instead:

```bash
ssh root@<TAILSCALE-IP>
```

Your server is now invisible to the internet. Only your Tailscale devices can reach it.

---

## Step 4: Clone the trading lab

```bash
# Create a deploy user (don't run as root)
useradd -m -s /bin/bash ubuntu
usermod -aG sudo ubuntu

# Switch to deploy user
su - ubuntu

# Clone your repo (use your actual repo URL)
git clone git@github.com:amonkarsidhant/TradingLab.git /opt/sid-trading-lab
cd /opt/sid-trading-lab
```

---

## Step 5: Set up Python

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-venv python3-pip -y

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

---

## Step 6: Configure secrets

```bash
cp .env.example .env
nano .env
```

Paste your T212 DEMO API key and Telegram bot token:

```
T212_API_KEY=your-demo-key
T212_API_SECRET=your-demo-secret
TELEGRAM_BOT_TOKEN=your-bot-token
```

**Important**: 
- Use your DEMO key, not LIVE
- Set `T212_ENV=demo`
- Set `ORDER_PLACEMENT_ENABLED=true` and `DEMO_ORDER_CONFIRM=I_ACCEPT_DEMO_ORDER_TEST` only when ready for demo orders

---

## Step 7: Install and start the daemon

```bash
sudo bash scripts/setup_systemd.sh
```

This creates a systemd service that:
- Starts the bot automatically on boot
- Restarts it if it crashes
- Logs to `logs/telegram_bot.log`
- Runs with security hardening (can't modify system files)

---

## Step 8: Verify

Check the service:
```bash
sudo systemctl status bull-telegram-bot
```

You should see `active (running)`.

Open Telegram and message your bot:
```
/start
/status
/summary
```

If you get responses, you're live.

---

## Daily operations

| Task | Command |
|---|---|
| Check bot status | `sudo systemctl status bull-telegram-bot` |
| View logs | `sudo journalctl -u bull-telegram-bot -f` |
| Restart bot | `sudo systemctl restart bull-telegram-bot` |
| Update code | `cd /opt/sid-trading-lab && git pull && sudo systemctl restart bull-telegram-bot` |
| Check MemPalace | SSH in, `source .venv/bin/activate && mempalace status` |

---

## Running a scan from VPS

```bash
cd /opt/sid-trading-lab
source .venv/bin/activate

# Single ticker
python -m trading_lab.cli run-strategy --ticker AAPL_US_EQ --strategy simple_momentum --data-source chained --dry-run

# Full watchlist scan
python -m trading_lab.cli param-sweep --ticker AAPL_US_EQ --data-source yfinance --output docs/reports/sweep.md
```

Or trigger these from your Telegram bot with `/scan`.

---

## Auto-scans with cron

To run a scan every hour during market hours:

```bash
crontab -e
```

Add:
```
# Pre-market scan at 6 AM EST (10:00 UTC)
0 10 * * 1-5 cd /opt/sid-trading-lab && .venv/bin/python -m trading_lab.cli run-strategy --ticker SPY_US_EQ --strategy simple_momentum --data-source chained --dry-run >> logs/scheduled_scan.log 2>&1

# Midday scan at 12 PM EST (16:00 UTC)
0 16 * * 1-5 cd /opt/sid-trading-lab && .venv/bin/python -m trading_lab.cli daily-journal --output docs/journal/$(date +%Y-%m-%d).md >> logs/scheduled_scan.log 2>&1
```

---

## Estimated costs

| Service | Monthly |
|---|---|
| Hetzner CPX11 | ~€4 |
| Tailscale | Free |
| T212 DEMO account | Free |
| Kimi K2.6 (optional LLM) | $19/mo |
| **Total (without LLM)** | **~€4/mo** |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot not starting | `sudo journalctl -u bull-telegram-bot -n 50` to see errors |
| T212 401 errors | Check you're using DEMO keys, not LIVE |
| Tailscale can't connect | Run `tailscale status` on server — should show connected |
| Out of memory | Add swap: `sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` |

---

## Next level

- Add Tailscale Funnel to expose a dashboard publicly (without opening ports)
- Set up Prometheus + Grafana for monitoring (in `docs/next-level-architecture.md`)
- Run multiple bots for different strategy variants on the same VPS
