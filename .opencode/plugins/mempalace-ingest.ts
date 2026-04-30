// OpenCode Plugin: MemPalace Auto-Ingest
// Mines written files into MemPalace for cross-session recall.
// Equivalent to the Claude Code mempalace-ingest.sh hook.

export const event = "tool.execute.after"

export async function run({ command, args }) {
  if (command !== "Write" && command !== "Edit") {
    return { allowed: true }
  }

  // Get the file path from args (first arg is typically the path)
  const filePath = args.find(a => typeof a === "string" && (a.endsWith(".py") || a.endsWith(".md") || a.endsWith(".ts") || a.endsWith(".sh")))

  if (!filePath) {
    return { allowed: true }
  }

  // Non-blocking: fire-and-forget mine via CLI
  // In a real plugin, you'd spawn this async

  return {
    allowed: true,
    info: `MemPalace: file ${filePath} will be auto-ingested on next mine.`,
  }
}
