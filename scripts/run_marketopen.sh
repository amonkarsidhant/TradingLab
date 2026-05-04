#!/bin/bash
cd /Users/sidhantamonkar/Documents/Projects/sid-trading-lab || exit 1
source .env
export PYTHONPATH=src:$PYTHONPATH

# Run market-open scans
/Users/sidhantamonkar/Documents/Projects/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli scan-rank
EXIT_CODE=$?
/Users/sidhantamonkar/Documents/Projects/sid-trading-lab/.venv/bin/python3 -m trading_lab.cli account-summary

# Notify
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${TELEGRAM_CHAT_ID}" \
    -d "text=✅ Market open routine complete — check logs for details" || true

exit $EXIT_CODE
