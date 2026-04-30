#!/bin/bash
# Setup script for Bull Position Watcher on Linux (systemd)
# Run with: sudo bash scripts/setup-watcher.sh

set -e

SERVICE_NAME="bull-watcher"
REPO="/opt/sid-trading-lab"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    REPO="$REPO_ROOT"
fi

echo "=== Bull Position Watcher — Systemd Setup ==="
echo "Repo: $REPO"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > "$SERVICE_FILE" << SERVICE_EOF
[Unit]
Description=Bull Position Watcher — Sid Trading Lab
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
ExecStart=$REPO/.venv/bin/python -m trading_lab.watcher
Restart=always
RestartSec=10
StandardOutput=append:$REPO/logs/watcher.log
StandardError=append:$REPO/logs/watcher.log
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$REPO/logs $REPO/memory $REPO/trading_lab.sqlite3

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
echo "Start:   sudo systemctl start $SERVICE_NAME"
echo "Stop:    sudo systemctl stop $SERVICE_NAME"
echo "Status:  sudo systemctl status $SERVICE_NAME"
echo "Logs:    tail -f $REPO/logs/watcher.log"
