#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
source .env
export PYTHONPATH=src:$PYTHONPATH

# Run midday review
"$(pwd)/.venv/bin/python3" -m trading_lab.cli account-summary
"$(pwd)/.venv/bin/python3" -m trading_lab.cli positions

# Notify
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=✅ Midday review complete — check logs for details" || true

exit 0
