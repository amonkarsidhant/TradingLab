#!/bin/bash
# Install Sid Trading Lab MCP server into Claude Desktop.
# Run: bash scripts/install_mcp.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

CONFIG_DIR="$HOME/Library/Application Support/Claude"
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Virtual environment not found at $VENV_PYTHON"
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

# Ensure config directory exists
mkdir -p "$CONFIG_DIR"

# Read existing config or start fresh
if [ -f "$CONFIG_FILE" ]; then
    CONFIG=$(cat "$CONFIG_FILE")
else
    CONFIG='{}'
fi

# Use Python to merge the MCP server entry
python3 <<EOF
import json
import sys

config = json.loads("""$CONFIG""")

if "mcpServers" not in config:
    config["mcpServers"] = {}

config["mcpServers"]["sid-trading-lab"] = {
    "command": "$VENV_PYTHON",
    "args": ["-m", "trading_lab.mcp_server"],
    "env": {
        "T212_ENV": "demo",
        "T212_ALLOW_LIVE": "false",
        "ORDER_PLACEMENT_ENABLED": "false"
    }
}

with open("$CONFIG_FILE", "w") as f:
    json.dump(config, f, indent=2)

print(f"MCP server installed: $CONFIG_FILE")
print("")
print("Restart Claude Desktop to activate the Sid Trading Lab tools.")
EOF
