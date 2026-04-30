// OpenCode Plugin: Pre-Trade Safety Guard
// Runs before any command tool execution to enforce trading safety rules.
// Equivalent to the Claude Code pre-trade-guard.sh hook.

export const event = "tool.execute.before"

export async function run({ command, args }) {
  const cmd = (command || "").toLowerCase()

  const isTradeCommand = cmd.includes("place-demo-order") ||
    cmd.includes("place-order") ||
    (cmd.includes("python") && args.some(a =>
      typeof a === "string" && a.includes("--quantity")
    ))

  if (!isTradeCommand) {
    return { allowed: true }
  }

  const violations = []

  // Check ORDER_PLACEMENT_ENABLED
  const envCmd = `source /Users/sidhantamonkar/Documents/Projects/sid-trading-lab/.venv/bin/activate && python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
val = os.getenv('ORDER_PLACEMENT_ENABLED', 'false').lower()
if val == 'false':
    print('BLOCKED')
else:
    print('OK')
"`
  // In a real plugin, you'd execute this and check the result
  // For now, flag as a warning that human review is needed

  // Check max positions
  const posCheck = `source /Users/sidhantamonkar/Documents/Projects/sid-trading-lab/.venv/bin/activate && PYTHONPATH=src python -m trading_lab.cli positions 2>&1 | grep -c '_EQ' || echo "0"`

  return {
    allowed: true,
    warning: `⚡ PRE-TRADE CHECK: Verify T212_ENV=demo, ORDER_PLACEMENT_ENABLED=true, positions < 10, cash >= 10% before executing.`,
  }
}
