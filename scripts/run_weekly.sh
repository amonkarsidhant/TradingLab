#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
source .env
export PYTHONPATH=src:$PYTHONPATH

# Run weekly reports
"$(pwd)/.venv/bin/python3" -m trading_lab.cli weekly-report --date today
"$(pwd)/.venv/bin/python3" -m trading_lab.cli strategy-comparison --ticker SPY --data-source static
"$(pwd)/.venv/bin/python3" -m trading_lab.cli agent-reviews --week current

# Notify
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=✅ Weekly review complete — check logs for details" || true

exit 0
