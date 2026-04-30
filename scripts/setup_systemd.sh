#!/bin/bash
# Setup script for Bull Telegram Bot on Linux (systemd)
# Run with: sudo bash scripts/setup_systemd.sh

set -e

SERVICE_NAME="bull-telegram-bot"
REPO="/opt/sid-trading-lab"
VENV="$REPO/.venv"

echo "=== Bull Telegram Bot — Systemd Setup ==="
echo ""

# Detect repo path if running from inside it
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    REPO="$REPO_ROOT"
    VENV="$REPO/.venv"
fi

echo "Repo: $REPO"
echo ""

# Check .env
if ! grep -q "TELEGRAM_BOT_TOKEN=" "$REPO/.env" 2>/dev/null || grep -q "TELEGRAM_BOT_TOKEN=$" "$REPO/.env" 2>/dev/null; then
    echo "WARNING: TELEGRAM_BOT_TOKEN not set in .env"
    echo "Edit $REPO/.env and set your bot token first."
    read -p "Press Enter to continue anyway..."
fi

# Write the systemd service file
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Creating systemd service: $SERVICE_FILE"

cat > "$SERVICE_FILE" << SERVICE_EOF
[Unit]
Description=Bull Telegram Bot — Sid Trading Lab
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO/src
ExecStart=$VENV/bin/python $REPO/src/trading_lab/telegram_bot.py
Restart=always
RestartSec=10
StandardOutput=append:$REPO/logs/telegram_bot.log
StandardError=append:$REPO/logs/telegram_bot.log

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$REPO/logs $REPO/memory $REPO/trading_lab.sqlite3
ReadOnlyPaths=$REPO/.env $REPO/.venv $REPO/src

[Install]
WantedBy=multi-user.target
SERVICE_EOF

mkdir -p "$REPO/logs"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

sleep 2
systemctl status "$SERVICE_NAME" --no-pager || true

echo ""
echo "=== Done ==="
echo "Start:        sudo systemctl start $SERVICE_NAME"
echo "Stop:         sudo systemctl stop $SERVICE_NAME"
echo "Restart:      sudo systemctl restart $SERVICE_NAME"
echo "Status:       sudo systemctl status $SERVICE_NAME"
echo "Logs:         sudo journalctl -u $SERVICE_NAME -f"
echo "File logs:    tail -f $REPO/logs/telegram_bot.log"
echo "Disable:      sudo systemctl disable $SERVICE_NAME"

