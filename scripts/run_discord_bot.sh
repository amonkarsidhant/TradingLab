#!/usr/bin/env bash
# Bull Discord Bot launcher
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${PROJECT_DIR}/.venv/bin/python"
BOT="${PROJECT_DIR}/src/trading_lab/discord_bot.py"

# Export all .env variables
set -a
source "${PROJECT_DIR}/.env"
set +a

# Sanity check
if [ ! -f "$BOT" ]; then
    echo "ERROR: Bot script not found at $BOT"
    exit 1
fi

echo "🚀 Starting Bull Discord Bot..."
echo "   Project: $PROJECT_DIR"
echo "   Token: ${DISCORD_BOT_TOKEN:0:10}..."

exec "$VENV" -u "$BOT"