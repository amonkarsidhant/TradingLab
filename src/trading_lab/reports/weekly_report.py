"""
WeeklyReport — aggregates one trading week (Mon-Fri) into a markdown summary.

Reads from the same SQLite tables as DailyJournal:
  snapshots — timestamped API response blobs
  signals   — every strategy signal with risk/approval outcome
  cycles    — autonomous cycle log
  strategy_regime_performance — Phase 0 meta-learner
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
        cycles = self._fetch_cycles(monday, friday)
        strategy_perf = self._fetch_strategy_perf()
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _render(
            week_start=monday.strftime("%Y-%m-%d"),
            week_end=friday.strftime("%Y-%m-%d"),
            generated_at=generated_at,
            db_path=self.db_path,
            snapshots=snapshots,
            signals=signals,
            cycles=cycles,
            strategy_perf=strategy_perf,
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

    def _fetch_cycles(self, from_date, to_date) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM cycles WHERE date(timestamp) >= ? AND date(timestamp) <= ?",
                    (from_date.strftime("%Y-%m-%d"), to_date.strftime("%Y-%m-%d")),
                ).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []

    def _fetch_strategy_perf(self) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM strategy_regime_performance ORDER BY regime, sharpe DESC"
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
    cycles: list[dict],
    strategy_perf: list[dict],
) -> str:
    lines: list[str] = []

    # -- Header --
    lines += [
        f"# Weekly Report — {week_start} to {week_end}",
        "",
        f"Generated: {generated_at}  ",
        f"Database: {db_path}",
        "",
        "---",
        "",
    ]

    # -- Regime Summary (Phase 0) --
    if cycles:
        lines.append("## Regime Summary")
        lines.append("")
        regimes = [c.get("regime", "?") for c in sorted(cycles, key=lambda c: c.get("timestamp", ""))]
        confidences = [c.get("confidence", 0.0) for c in cycles]
        strategies = [c.get("strategy", "?") for c in cycles]
        signals_scanned = sum(c.get("signals_count", 0) for c in cycles)

        lines.append(f"- **Autonomous cycles this week:** {len(cycles)}")
        lines.append(f"- **Regimes observed:** {', '.join(sorted(set(regimes)))}")
        if confidences:
            lines.append(f"- **Avg regime confidence:** {sum(confidences)/len(confidences):.2f}")
        lines.append(f"- **Signals scanned:** {signals_scanned}")
        if len(set(strategies)) > 1:
            lines.append(f"- **Strategies selected:** {', '.join(sorted(set(strategies)))}")
        else:
            lines.append(f"- **Strategy selected:** {strategies[0]}")

        # Daily regime table
        lines.append("")
        lines.append("### Daily Regime Log")
        lines.append("")
        lines.append("| Day | Regime | Confidence | Strategy | Signals |")
        lines.append("|---|---|---|---|---|")
        day_regime_map: dict[str, dict] = {}
        for c in cycles:
            day = c.get("timestamp", "")[:10]
            day_regime_map[day] = c
        for day in sorted(day_regime_map):
            c = day_regime_map[day]
            lines.append(
                f"| {day} | {c.get('regime','?')} | {c.get('confidence',0):.2f} "
                f"| {c.get('strategy','?')} | {c.get('signals_count',0)} |"
            )
        lines.append("")
        lines += ["---", ""]

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

        # Regime-aware breakdown
        regime_signals = {}
        for s in signals:
            reg = s.get("regime") or "unknown"
            regime_signals[reg] = regime_signals.get(reg, 0) + 1

        lines += [
            f"- Signals: BUY {buy_count} / SELL {sell_count} / HOLD {hold_count}",
            f"- Approved: {approved_count}, Rejected: {len(signals) - approved_count}",
            f"- Dry-run: {dry_run_count}, Live: {len(signals) - dry_run_count}",
        ]
        if regime_signals:
            lines.append("- By regime: " + ", ".join(f"{k}: {v}" for k, v in sorted(regime_signals.items())))
    lines += ["", "---", ""]

    # -- Strategy Performance (Phase 0) --
    if strategy_perf:
        lines.append("## Strategy Performance by Regime")
        lines.append("")
        lines.append("| Strategy | Regime | Sharpe | Win Rate | Trades | Avg Hold (days) |")
        lines.append("|---|---|---|---|---|---|")
        for sp in strategy_perf:
            lines.append(
                f"| {sp.get('strategy_id','?')} | {sp.get('regime','?')} "
                f"| {sp.get('sharpe','-')} | {(sp.get('win_rate') or 0)*100:.1f}% "
                f"| {sp.get('trade_count',0)} | {sp.get('avg_hold_days','-')}".rstrip(" |") + " |"
            )
        lines.append("")
        lines += ["---", ""]

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
        "- Which regime produced the best signals? Should we weight it more?",
        "",
        "---",
        "",
        "*No live trades were placed. All data is from the demo environment.*",
        "*Generated by Sid Trading Lab weekly report v1.*",
        "",
    ]

    return "\n".join(lines)
