# VPS Deployment Guide — Sid Trading Lab

**One-shot deploy doc. Give this entire file to your VPS Hermes agent.**

---

## 0. Prerequisites (must have before starting)

| Requirement | Value |
|-------------|-------|
| OS | Ubuntu 22.04+ (Debian-based) or any Linux with systemd |
| Python | 3.11+ installed system-wide |
| Git | Installed + SSH key to GitHub |
| Domain (optional) | For Telegram webhook mode (recommended for VPS) |
| Firewall | Ports 22 (SSH), 443 (webhook if used) |
| Secrets | `T212_API_KEY`, `T212_ENV=demo`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

---

## 1. Clone & Setup

```bash
# 1.1 Clone
cd /opt
git clone git@github.com:amonkarsidhant/TradingLab.git sid-trading-lab
cd sid-trading-lab

# 1.2 Create venv
python3 -m venv .venv
source .venv/bin/activate

# 1.3 Install deps
pip install --upgrade pip
pip install -r requirements.txt

# 1.4 Create .env
cat > .env << 'EOF'
T212_API_KEY=your_key_here
T212_ENV=demo
T212_ALLOW_LIVE=false
ORDER_PLACEMENT_ENABLED=true
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_numeric_chat_id_here
AUTO_APPROVE=false
EOF
chmod 600 .env

# 1.5 Create directories
mkdir -p logs data/market data/orders
```

---

## 2. Test Core CLI (validate before daemonizing)

```bash
# Test imports
PYTHONPATH=src python -m trading_lab.cli --help

# Test connection to T212 demo
PYTHONPATH=src python -m trading_lab.cli account-summary

# Test scan (should run without crash)
PYTHONPATH=src python -m trading_lab.cli scan-rank

# Only proceed if all 3 pass. If scan crashes, stop and debug engine.py first.
```

---

## 3. Deploy Telegram Bot (systemd service)

```bash
sudo tee /etc/systemd/system/sid-telegram-bot.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab Telegram Bot
After=network.target

[Service]
Type=simple
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 scripts/telegram_bot_unified.py
Restart=always
RestartSec=5
StandardOutput=append:/opt/sid-trading-lab/logs/bot.stdout.log
StandardError=append:/opt/sid-trading-lab/logs/bot.stderr.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sid-telegram-bot
sudo systemctl start sid-telegram-bot
```

**Validate:**
```bash
sudo systemctl status sid-telegram-bot
sudo journalctl -u sid-telegram-bot -f
```

Look for: `HTTP/1.1 200 OK` on `getUpdates` in logs.

---

## 4. Deploy Scheduled Routines (systemd timers)

Instead of macOS launchd, use systemd timers on Linux.

### 4.1 Pre-market (06:00 UTC)
```bash
sudo tee /etc/systemd/system/sid-premarket.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab — Pre-market Scan

[Service]
Type=oneshot
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli scan-rank
EOF

sudo tee /etc/systemd/system/sid-premarket.timer > /dev/null << 'EOF'
[Unit]
Description=Run premarket scan daily at 06:00 UTC

[Timer]
OnCalendar=*-*-* 06:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 4.2 Market Open (09:30 UTC)
```bash
sudo tee /etc/systemd/system/sid-marketopen.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab — Market Open Scan

[Service]
Type=oneshot
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli scan-rank
EOF

sudo tee /etc/systemd/system/sid-marketopen.timer > /dev/null << 'EOF'
[Unit]
Description=Run market-open scan daily at 09:30 UTC

[Timer]
OnCalendar=Mon..Fri 09:30:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 4.3 Midday (12:00 UTC)
```bash
sudo tee /etc/systemd/system/sid-midday.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab — Midday Review

[Service]
Type=oneshot
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli account-summary
EOF

sudo tee /etc/systemd/system/sid-midday.timer > /dev/null << 'EOF'
[Unit]
Description=Run midday review daily at 12:00 UTC

[Timer]
OnCalendar=Mon..Fri 12:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 4.4 Market Close (16:00 UTC)
```bash
sudo tee /etc/systemd/system/sid-marketclose.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab — Market Close Journal

[Service]
Type=oneshot
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli daily-journal
EOF

sudo tee /etc/systemd/system/sid-marketclose.timer > /dev/null << 'EOF'
[Unit]
Description=Run market-close journal daily at 16:00 UTC

[Timer]
OnCalendar=Mon..Fri 16:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 4.5 Weekly (Friday 17:00 UTC)
```bash
sudo tee /etc/systemd/system/sid-weekly.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab — Weekly Report

[Service]
Type=oneshot
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli weekly-report --date today
EOF

sudo tee /etc/systemd/system/sid-weekly.timer > /dev/null << 'EOF'
[Unit]
Description=Run weekly report Friday at 17:00 UTC

[Timer]
OnCalendar=Fri 17:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 4.6 Enable all timers
```bash
sudo systemctl daemon-reload
sudo systemctl enable sid-premarket.timer
sudo systemctl enable sid-marketopen.timer
sudo systemctl enable sid-midday.timer
sudo systemctl enable sid-marketclose.timer
sudo systemctl enable sid-weekly.timer
sudo systemctl start sid-premarket.timer
sudo systemctl start sid-marketopen.timer
sudo systemctl start sid-midday.timer
sudo systemctl start sid-marketclose.timer
sudo systemctl start sid-weekly.timer

# Verify
timersctl list-timers --all
```

---

## 5. Deploy Watcher Daemon (position monitor + kill switch)

```bash
sudo tee /etc/systemd/system/sid-watcher.service > /dev/null << 'EOF'
[Unit]
Description=Sid Trading Lab — Position Watcher Daemon
After=network.target

[Service]
Type=simple
User=trading
Group=trading
WorkingDirectory=/opt/sid-trading-lab
Environment=PYTHONPATH=/opt/sid-trading-lab/src
EnvironmentFile=/opt/sid-trading-lab/.env
ExecStart=/opt/sid-trading-lab/.venv/bin/python3 -c "from trading_lab.watcher.loop import PositionWatcher; from trading_lab.config import get_settings; w = PositionWatcher(get_settings()); w.start()"
Restart=always
RestartSec=10
StandardOutput=append:/opt/sid-trading-lab/logs/watcher.stdout.log
StandardError=append:/opt/sid-trading-lab/logs/watcher.stderr.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sid-watcher
sudo systemctl start sid-watcher
```

---

## 6. File Permissions & Security

```bash
# Create dedicated user (recommended)
sudo useradd -r -s /bin/false trading || true
sudo chown -R trading:trading /opt/sid-trading-lab
sudo chmod 700 /opt/sid-trading-lab/.env

# Log rotation (prevent disk fill)
sudo tee /etc/logrotate.d/sid-trading-lab > /dev/null << 'EOF'
/opt/sid-trading-lab/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 trading trading
}
EOF

# Optional: restrict .env from group/other
chmod 600 /opt/sid-trading-lab/.env
```

---

## 7. Validation Checklist

Run these before declaring done:

```bash
# 7.1 Bot is polling Telegram
sudo systemctl is-active sid-telegram-bot

# 7.2 All timers registered
systemctl list-timers | grep sid-

# 7.3 Watcher is running
sudo systemctl is-active sid-watcher

# 7.4 Manual scan works
sudo -u trading bash -c 'cd /opt/sid-trading-lab && source .venv/bin/activate && PYTHONPATH=src python -m trading_lab.cli scan-rank'

# 7.5 Telegram bot responds
# Open Telegram, message your bot /status
# Should reply with positions, cash, job status

# 7.6 Disk space check
df -h /opt
```

---

## 8. Daily Ops Commands (for Hermes agent)

```bash
# View all service status
systemctl status sid-telegram-bot sid-watcher

# View recent job logs
sudo journalctl -u sid-premarket --since today
sudo journalctl -u sid-marketopen --since today

# Restart any service
sudo systemctl restart sid-telegram-bot
sudo systemctl restart sid-watcher

# Trigger a job manually
sudo systemctl start sid-premarket
sudo systemctl start sid-marketclose

# Check portfolio
PYTHONPATH=src .venv/bin/python3 -m trading_lab.cli account-summary

# Reset kill switch
PYTHONPATH=src .venv/bin/python3 -c "from trading_lab.watcher.kill_switch import KillSwitch; from trading_lab.logger import SnapshotLogger; from trading_lab.config import get_settings; ks = KillSwitch(SnapshotLogger(get_settings().db_path)); ks.load_state(); ks.reset() if ks.is_fired() else print('Not fired')"
```

---

## 9. Known Gotchas & Fixes

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: trading_lab` | PYTHONPATH not set | Always export PYTHONPATH=src before any python command |
| `Conflict: terminated by other getUpdates` | Two bot instances running | Kill old PIDs, only run via systemd |
| `Forbidden: bots can't send messages to bots` | Chat ID wrong | Get your personal chat ID via @userinfobot |
| `AttributeError: 'NoneType' has no 'entry_date'` | Backtest engine bug on empty data | Run with `--data-source static` or check data/ folder |
| Logs grow forever | No rotation | logrotate config above handles this |
| `TypeError: datetime.time() needs argument` | `datetime` module shadowed | Fixed in unified bot; use latest from repo |

---

## 10. Architecture on VPS

```
VPS
├── sid-telegram-bot.service    (always-on, polling Telegram)
├── sid-watcher.service         (always-on, monitors positions)
├── sid-premarket.timer         (06:00 UTC, triggers .service)
├── sid-marketopen.timer        (09:30 UTC)
├── sid-midday.timer            (12:00 UTC)
├── sid-marketclose.timer       (16:00 UTC)
├── sid-weekly.timer            (Fri 17:00 UTC)
└── logrotate                   (daily, keeps 14 days)
```

---

## End. Hand this file to your VPS Hermes agent verbatim.
