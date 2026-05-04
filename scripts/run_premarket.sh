#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
source .env
export PYTHONPATH=src:$PYTHONPATH

# Run pre-market scan
"$(pwd)/.venv/bin/python3" -m trading_lab.cli scan-rank
EXIT_CODE=$?

# Notify via Telegram
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=✅ Pre-market scan complete — check logs for details" || true

exit $EXIT_CODE
