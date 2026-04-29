#!/bin/bash
# Setup script for Trading Lab Dashboard Server on macOS

set -e

REPO="/Users/sidhantamonkar/Documents/Projects/sid-trading-lab"
PLIST_NAME="com.sidtradinglab.dashboard.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "=== Trading Lab Dashboard Server Setup ==="
echo ""

# 1. Install LaunchAgent
echo "Installing LaunchAgent..."
mkdir -p "$LAUNCH_AGENTS"
cp "$REPO/scripts/$PLIST_NAME" "$LAUNCH_AGENTS/"
launchctl load "$LAUNCH_AGENTS/$PLIST_NAME" 2>/dev/null || launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENTS/$PLIST_NAME"

echo ""
echo "=== Done ==="
echo "URL:     http://localhost:8080"
echo "Start:   launchctl start $PLIST_NAME"
echo "Stop:    launchctl stop $PLIST_NAME"
echo "Logs:    tail -f $REPO/logs/dashboard_server.log"
echo "Unload:  launchctl unload $LAUNCH_AGENTS/$PLIST_NAME"
echo ""
echo "The dashboard auto-regenerates every 5 minutes."
echo "Open http://localhost:8080 in your browser."
