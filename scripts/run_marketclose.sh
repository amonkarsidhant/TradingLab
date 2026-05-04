#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
source .env
export PYTHONPATH=src:$PYTHONPATH

# Run end-of-day journal
"$(pwd)/.venv/bin/python3" -m trading_lab.cli daily-journal

# Notify
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=✅ Market close routine complete — check logs for details" || true

exit 0
