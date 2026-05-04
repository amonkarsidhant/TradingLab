#!/bin/bash
# Setup script for Bull Telegram Bot on macOS

set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_NAME="com.sidtradinglab.telegrambot.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "=== Bull Telegram Bot Setup ==="
echo ""

# 1. Check token
if ! grep -q "TELEGRAM_BOT_TOKEN=" "$REPO/.env" 2>/dev/null || grep -q "TELEGRAM_BOT_TOKEN=$" "$REPO/.env" 2>/dev/null; then
    echo "WARNING: TELEGRAM_BOT_TOKEN not set in .env"
    echo "1. Talk to @BotFather on Telegram and create a bot."
    echo "2. Add TELEGRAM_BOT_TOKEN=<your-token> to .env"
    echo ""
    read -p "Press Enter to continue anyway..."
fi

# 2. Install LaunchAgent
echo "Installing LaunchAgent..."
mkdir -p "$LAUNCH_AGENTS"
cp "$REPO/scripts/$PLIST_NAME" "$LAUNCH_AGENTS/"
launchctl load "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENTS/$PLIST_NAME"

echo ""
echo "=== Done ==="
echo "Start:   launchctl start $PLIST_NAME"
echo "Stop:    launchctl stop $PLIST_NAME"
echo "Logs:    tail -f $REPO/logs/telegram_bot.log"
echo "Unload:  launchctl unload $LAUNCH_AGENTS/$PLIST_NAME"
