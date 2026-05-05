"""
DailyJournal — reads from SQLite and renders a markdown summary report.

Reads two tables written by SnapshotLogger:
  snapshots — timestamped API response blobs
  signals   — every strategy signal with risk/approval outcome
  cycles    — autonomous cycle log (Phase 0 regime attribution)

No network calls. No credentials. No Trading 212 API usage.
All timestamps in the database are UTC ISO strings.
"""
import sqlite3
from collections import Counter
from datetime import datetime, timezone


class DailyJournal:
    """Generate a markdown report for one calendar day from the local SQLite DB."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def generate(self, report_date: str) -> str:
        """Return a markdown report string for the given date (YYYY-MM-DD)."""
        snapshots = self._fetch_snapshots(report_date)
        signals = self._fetch_signals(report_date)
        cycles = self._fetch_cycles(report_date)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _render(report_date, generated_at, self.db_path, snapshots, signals, cycles)

    def _fetch_snapshots(self, report_date: str) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM snapshots WHERE date(created_at) = ?",
                    (report_date,),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def _fetch_signals(self, report_date: str) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM signals WHERE date(created_at) = ?",
                    (report_date,),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def _fetch_cycles(self, report_date: str) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM cycles WHERE date(timestamp) = ?",
                    (report_date,),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []


# ── Rendering ─────────────────────────────────────────────────────────────────

def _render(
    report_date: str,
    generated_at: str,
    db_path: str,
    snapshots: list[dict],
    signals: list[dict],
    cycles: list[dict],
) -> str:
    lines: list[str] = []

    # ── Header ─────────────────────────────────────────────────────────────────
    lines += [
        f"# Daily Journal — {report_date}",
        "",
        f"Generated: {generated_at}  ",
        f"Database: {db_path}",
        "",
        "---",
        "",
    ]

    # ── Regime Summary (Phase 0) ──────────────────────────────────────────────
    if cycles:
        lines.append("## Regime & Strategy Summary")
        lines.append("")
        # Most recent cycle of the day
        latest = max(cycles, key=lambda c: c.get("timestamp", ""))
        regime = latest.get("regime", "unknown")
        conf = latest.get("confidence", 0.0)
        strategy = latest.get("strategy", "unknown")
        total_signals = sum(c.get("signals_count", 0) for c in cycles)

        lines.append(f"- **Regime:** {regime} (confidence: {conf:.2f})")
        lines.append(f"- **Strategy:** {strategy}")
        lines.append(f"- **Autonomous cycles:** {len(cycles)}")
        lines.append(f"- **Total signals scanned:** {total_signals}")

        # Regime transitions
        if len(cycles) > 1:
            regimes = [c.get("regime", "?") for c in sorted(cycles, key=lambda c: c.get("timestamp", ""))]
            if len(set(regimes)) > 1:
                lines.append(f"- **Regime transitions:** {' → '.join(regimes)}")
        lines.append("")
        lines += ["---", ""]

    # ── Snapshots ──────────────────────────────────────────────────────────────
    lines.append("## Account Snapshots")
    lines.append("")

    if not snapshots:
        lines.append("No snapshots recorded for this date.")
        lines.append("")
        lines.append("> Run `account-summary --save-snapshot` or `positions --save-snapshot` to record data.")
    else:
        snapshot_types = ", ".join(sorted(set(s["snapshot_type"] for s in snapshots)))
        lines.append(f"- Total: {len(snapshots)}")
        lines.append(f"- Types: {snapshot_types}")

    lines += ["", "---", ""]

    # ── Signals ────────────────────────────────────────────────────────────────
    lines.append("## Strategy Signals")
    lines.append("")

    if not signals:
        lines.append("No signals recorded for this date.")
        lines.append("")
        lines.append("> Run `run-strategy --dry-run` to generate and journal signals.")
    else:
        buy_count = sum(1 for s in signals if s["action"] == "BUY")
        sell_count = sum(1 for s in signals if s["action"] == "SELL")
        hold_count = sum(1 for s in signals if s["action"] == "HOLD")
        approved_count = sum(1 for s in signals if s["approved"])
        rejected_count = len(signals) - approved_count
        dry_run_count = sum(1 for s in signals if s["dry_run"])
        live_count = len(signals) - dry_run_count

        # Regime-aware signal breakdown
        regime_signals = {}
        for s in signals:
            reg = s.get("regime") or "unknown"
            regime_signals[reg] = regime_signals.get(reg, 0) + 1

        lines += [
            f"- Total signals: {len(signals)}",
            f"- By action: BUY: {buy_count}, SELL: {sell_count}, HOLD: {hold_count}",
            f"- Approved: {approved_count}, Rejected: {rejected_count}",
            f"- Dry-run: {dry_run_count}, Live: {live_count}",
        ]
        if regime_signals:
            lines.append("- By regime: " + ", ".join(f"{k}: {v}" for k, v in sorted(regime_signals.items())))
        lines.append("")

        # Signal details table
        lines.append("### Signal details")
        lines.append("")
        has_regime = any(s.get("regime") for s in signals)
        if has_regime:
            lines.append("| Time (UTC) | Ticker | Action | Confidence | Regime | Approved | Reason |")
            lines.append("|---|---|---|---|---|---|---|")
        else:
            lines.append("| Time (UTC) | Ticker | Action | Confidence | Approved | Reason |")
            lines.append("|---|---|---|---|---|---|")
        for s in signals:
            time_str = s["created_at"][11:16]  # HH:MM slice from ISO string
            approved_str = "Yes" if s["approved"] else "No"
            reason = s["reason"]
            if len(reason) > 55:
                reason = reason[:52] + "..."
            reg = s.get("regime") or "-"
            if has_regime:
                lines.append(
                    f"| {time_str} | {s['ticker']} | {s['action']} "
                    f"| {s['confidence']:.2f} | {reg} | {approved_str} | {reason} |"
                )
            else:
                lines.append(
                    f"| {time_str} | {s['ticker']} | {s['action']} "
                    f"| {s['confidence']:.2f} | {approved_str} | {reason} |"
                )
        lines.append("")

        # Top reasons
        lines.append("### Top signal reasons")
        lines.append("")
        reason_counts = Counter(s["reason"] for s in signals)
        for i, (reason, count) in enumerate(reason_counts.most_common(3), start=1):
            suffix = f" ({count}x)" if count > 1 else ""
            lines.append(f"{i}. {reason}{suffix}")
        lines.append("")

    lines += ["---", ""]

    # ── Review questions ───────────────────────────────────────────────────────
    lines += [
        "## Review questions",
        "",
        "- Did any signals today align with your own market view?",
        "- Were any signals rejected that you would have approved manually?",
        "- Should the strategy parameters (lookback, threshold) be adjusted?",
        "- Is the CSV price data current and from a reliable source?",
        "- What would you have done differently today?",
        "- Should this strategy continue, change, or be retired?",
        "",
        "---",
        "",
        "*No live trades were placed. All signals are from the demo environment.*",
        "",
    ]

    return "\n".join(lines)
