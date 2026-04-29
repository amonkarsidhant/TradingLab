"""
WeeklyReport — aggregates one trading week (Mon-Fri) into a markdown summary.

Reads from the same SQLite tables as DailyJournal:
  snapshots — timestamped API response blobs
  signals   — every strategy signal with risk/approval outcome
"""
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone


class WeeklyReport:
    """Generate a markdown report for one trading week (Mon-Fri)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def generate(self, report_date: str = "") -> str:
        """Return a markdown report string. Uses today (UTC) if report_date is empty."""
        if not report_date:
            report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        monday, friday = _week_bounds(report_date)
        snapshots = self._fetch_snapshots(monday, friday)
        signals = self._fetch_signals(monday, friday)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _render(
            week_start=monday.strftime("%Y-%m-%d"),
            week_end=friday.strftime("%Y-%m-%d"),
            generated_at=generated_at,
            db_path=self.db_path,
            snapshots=snapshots,
            signals=signals,
        )

    def _fetch_snapshots(self, from_date, to_date) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM snapshots WHERE date(created_at) >= ? AND date(created_at) <= ?",
                    (from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d")),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def _fetch_signals(self, from_date, to_date) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM signals WHERE date(created_at) >= ? AND date(created_at) <= ?",
                    (from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d")),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []


def _week_bounds(report_date: str) -> tuple[datetime, datetime]:
    """Given any date, return the Monday and Friday datetime bounds for that week."""
    dt = datetime.strptime(report_date, "%Y-%m-%d")
    monday = dt - timedelta(days=dt.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


# -- Rendering ----------------------------------------------------------------

def _render(
    week_start: str,
    week_end: str,
    generated_at: str,
    db_path: str,
    snapshots: list[dict],
    signals: list[dict],
) -> str:
    lines: list[str] = []

    # -- Header --
    lines += [
        f"# Weekly Report -- {week_start} to {week_end}",
        "",
        f"Generated: {generated_at}  ",
        f"Database: {db_path}",
        "",
        "---",
        "",
    ]

    # -- Executive summary --
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- Total signals: {len(signals)}")
    lines.append(f"- Total snapshots: {len(snapshots)}")
    if signals:
        buy_count = sum(1 for s in signals if s["action"] == "BUY")
        sell_count = sum(1 for s in signals if s["action"] == "SELL")
        hold_count = sum(1 for s in signals if s["action"] == "HOLD")
        approved_count = sum(1 for s in signals if s["approved"])
        dry_run_count = sum(1 for s in signals if s["dry_run"])
        lines += [
            f"- Signals: BUY {buy_count} / SELL {sell_count} / HOLD {hold_count}",
            f"- Approved: {approved_count}, Rejected: {len(signals) - approved_count}",
            f"- Dry-run: {dry_run_count}, Live: {len(signals) - dry_run_count}",
        ]
    lines += ["", "---", ""]

    # -- Daily breakdown --
    lines.append("## Daily Breakdown")
    lines.append("")

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    day_counts: dict[int, list[dict]] = {i: [] for i in range(5)}
    for s in signals:
        try:
            dt = datetime.strptime(s["created_at"][:10], "%Y-%m-%d")
            dow = dt.weekday()
            if dow < 5:
                day_counts[dow].append(s)
        except (ValueError, KeyError):
            pass

    lines.append("| Strategy | Mon | Tue | Wed | Thu | Fri | Total |")
    lines.append("|---|---|---|---|---|---|---|")
    strategies_seen = sorted(set(
        s.get("strategy", "?") for s in signals
    ))
    if not strategies_seen:
        lines.append("| — | 0 | 0 | 0 | 0 | 0 | 0 |")
    else:
        for st in strategies_seen:
            day_cells = []
            total = 0
            for d in range(5):
                c = sum(1 for s in day_counts[d] if s.get("strategy") == st)
                day_cells.append(str(c))
                total += c
            lines.append(f"| {st} | {' | '.join(day_cells)} | {total} |")
    lines.append("")

    # -- Signal activity --
    lines += ["---", "", "## Signal Activity by Strategy", ""]
    if not signals:
        lines.append("No signals recorded this week.")
    else:
        lines.append("| Strategy | BUY | SELL | HOLD | Avg Confidence |")
        lines.append("|---|---|---|---|---|")
        by_strategy: dict[str, list[dict]] = {}
        for s in signals:
            by_strategy.setdefault(s.get("strategy", "?"), []).append(s)
        for st in sorted(by_strategy):
            ss = by_strategy[st]
            b = sum(1 for s in ss if s["action"] == "BUY")
            se = sum(1 for s in ss if s["action"] == "SELL")
            h = sum(1 for s in ss if s["action"] == "HOLD")
            avg_conf = sum(s.get("confidence", 0) for s in ss) / len(ss) if ss else 0
            lines.append(f"| {st} | {b} | {se} | {h} | {avg_conf:.2f} |")
    lines.append("")

    # -- Ticker activity --
    lines += ["---", "", "## Ticker Activity", ""]
    if not signals:
        lines.append("No ticker activity this week.")
    else:
        lines.append("| Ticker | Signals | BUY | SELL | HOLD |")
        lines.append("|---|---|---|---|---|")
        by_ticker: dict[str, list[dict]] = {}
        for s in signals:
            by_ticker.setdefault(s.get("ticker", "?"), []).append(s)
        for tk in sorted(by_ticker, key=lambda t: len(by_ticker[t]), reverse=True):
            ss = by_ticker[tk]
            lines.append(
                f"| {tk} | {len(ss)} | {sum(1 for s in ss if s['action'] == 'BUY')} "
                f"| {sum(1 for s in ss if s['action'] == 'SELL')} "
                f"| {sum(1 for s in ss if s['action'] == 'HOLD')} |"
            )
    lines.append("")

    # -- Snapshot summary --
    lines += ["---", "", "## Snapshots Recorded", ""]
    if not snapshots:
        lines.append("No snapshots recorded this week.")
        lines.append("")
        lines.append("> Run `account-summary --save-snapshot` or `positions --save-snapshot` to record data.")
    else:
        types = Counter(s["snapshot_type"] for s in snapshots)
        lines.append(f"- Total: {len(snapshots)}")
        for stype, count in types.most_common():
            lines.append(f"- {stype}: {count}")
    lines.append("")

    # -- Review questions --
    lines += [
        "---",
        "",
        "## Review Questions",
        "",
        "- Which day had the most signal activity and why?",
        "- Did you override any signals this week? If so, what was your reasoning?",
        "- Are there patterns in the daily breakdown (e.g. more signals on certain days)?",
        "- Did this week's signals align with your broader market thesis?",
        "- Is the strategy generating too many or too few signals for your cadence?",
        "- Should any strategy parameters be adjusted based on this week's data?",
        "",
        "---",
        "",
        "*No live trades were placed. All data is from the demo environment.*",
        "*Generated by Sid Trading Lab weekly report v1.*",
        "",
    ]

    return "\n".join(lines)
