"""
StrategyComparison — side-by-side backtest metrics for all registered strategies.

Runs a backtest for each strategy and compares the results in a single
markdown report alongside journaled signal counts from the SQLite DB.
"""
import sqlite3
from datetime import datetime, timezone

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.backtest.report import _sparkline
from trading_lab.data.market_data import make_provider
from trading_lab.strategies import get_strategy, list_strategies


class StrategyComparison:
    """Run backtests for all strategies and produce a side-by-side comparison report."""

    def __init__(self, db_path: str, cache_db_path: str = "") -> None:
        self.db_path = db_path
        self.cache_db_path = cache_db_path

    def compare(
        self,
        ticker: str = "AAPL_US_EQ",
        data_source: str = "static",
        prices_file: str = "",
        initial_capital: float = 10_000.0,
    ) -> str:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        provider = make_provider(
            source=data_source,
            ticker=ticker,
            prices_file=prices_file,
            cache_db=self.cache_db_path,
        )
        prices = provider.get_prices(ticker=ticker, lookback=252)

        strategies_data: list[dict] = []
        for name in sorted(list_strategies()):
            try:
                kwargs = _default_kwargs(name)
                strategy = get_strategy(name, **kwargs)
                engine = BacktestEngine(strategy, initial_capital=initial_capital)
                result = engine.run(prices=prices, ticker=ticker)
                strategies_data.append({
                    "name": name,
                    "metrics": result.metrics,
                    "equity_curve": result.equity_curve,
                    "trades": result.trades,
                    "signals": result.signals,
                })
            except Exception:
                # Strategy instantiation or backtest failed — skip with note
                strategies_data.append({
                    "name": name,
                    "metrics": {},
                    "equity_curve": [],
                    "trades": [],
                    "signals": [],
                    "error": True,
                })

        journaled = self._fetch_signal_counts(ticker)
        return _render(
            ticker=ticker,
            capital=initial_capital,
            source=data_source,
            strategies_data=strategies_data,
            journaled_counts=journaled,
            generated_at=generated_at,
        )

    def _fetch_signal_counts(self, ticker: str) -> dict[str, dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT strategy, action, COUNT(*) as cnt
                       FROM signals WHERE ticker = ?
                       GROUP BY strategy, action""",
                    (ticker,),
                ).fetchall()
                result: dict[str, dict] = {}
                for row in rows:
                    r = dict(row)
                    st = r["strategy"]
                    if st not in result:
                        result[st] = {"BUY": 0, "SELL": 0, "HOLD": 0, "total": 0}
                    result[st][r["action"]] = r["cnt"]
                    result[st]["total"] += r["cnt"]
                return result
        except sqlite3.OperationalError:
            return {}


def _default_kwargs(name: str) -> dict:
    if name == "simple_momentum":
        return {"lookback": 5}
    if name == "ma_crossover":
        return {"fast": 10, "slow": 30}
    if name == "mean_reversion":
        return {"period": 14, "oversold": 30, "overbought": 70}
    return {}


# -- Rendering ----------------------------------------------------------------

def _render(
    ticker: str,
    capital: float,
    source: str,
    strategies_data: list[dict],
    journaled_counts: dict[str, dict],
    generated_at: str,
) -> str:
    lines: list[str] = []

    lines += [
        f"# Strategy Comparison -- {ticker}",
        "",
        f"**Initial capital:** ${capital:,.2f}  ",
        f"**Data source:** {source}  ",
        f"**Generated:** {generated_at}",
        "",
        "---",
        "",
    ]

    # -- Comparison table --
    lines.append("## Performance Comparison")
    lines.append("")
    headers = [
        "Strategy", "Return%", "CAGR%", "Sharpe", "MaxDD%",
        "WinRate%", "ProfitFactor", "Trades", "Wins", "Losses",
        "AvgWin%", "AvgLoss%",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")

    for sd in strategies_data:
        m = sd["metrics"]
        if sd.get("error"):
            lines.append(f"| {sd['name']} | *error* | | | | | | | | | | |")
            continue
        lines.append(
            f"| {sd['name']} "
            f"| {_fmt(m.get('total_return_pct'))} "
            f"| {_fmt(m.get('cagr_pct'))} "
            f"| {_fmt(m.get('sharpe_ratio'))} "
            f"| {_fmt(m.get('max_drawdown_pct'))} "
            f"| {_fmt(m.get('win_rate'))} "
            f"| {_fmt(m.get('profit_factor'))} "
            f"| {m.get('total_trades', 0)} "
            f"| {m.get('winning_trades', 0)} "
            f"| {m.get('losing_trades', 0)} "
            f"| {_fmt(m.get('avg_win_pct'))} "
            f"| {_fmt(m.get('avg_loss_pct'))} |"
        )
    lines.append("")

    # -- Journaled signals comparison --
    if journaled_counts:
        lines += ["---", "", "## Journaled Signal Counts", ""]
        lines.append("| Strategy | Total | BUY | SELL | HOLD |")
        lines.append("|---|---|---|---|---|")
        for name in sorted(journaled_counts):
            jc = journaled_counts[name]
            lines.append(
                f"| {name} | {jc['total']} | {jc['BUY']} "
                f"| {jc['SELL']} | {jc['HOLD']} |"
            )
        lines.append("")

    # -- Per-strategy details --
    for i, sd in enumerate(strategies_data):
        if sd.get("error"):
            continue
        lines += [
            "---",
            "",
            f"## {sd['name']}",
            "",
        ]
        m = sd["metrics"]

        lines += [
            f"| Metric | Value |",
            f"|---|---|",
            f"| Total Return | {_fmt(m.get('total_return_pct'))}% |",
            f"| CAGR | {_fmt(m.get('cagr_pct'))}% |",
            f"| Sharpe Ratio | {_fmt(m.get('sharpe_ratio'))} |",
            f"| Max Drawdown | {_fmt(m.get('max_drawdown_pct'))}% |",
            f"| Win Rate | {_fmt(m.get('win_rate'))}% |",
            f"| Profit Factor | {_fmt(m.get('profit_factor'))} |",
            f"| Total Trades | {m.get('total_trades', 0)} |",
            f"| Winning Trades | {m.get('winning_trades', 0)} |",
            f"| Losing Trades | {m.get('losing_trades', 0)} |",
            f"| Avg Win | {_fmt(m.get('avg_win_pct'))}% |",
            f"| Avg Loss | {_fmt(m.get('avg_loss_pct'))}% |",
            "",
        ]

        # Equity sparkline
        if sd["equity_curve"]:
            spark = _sparkline(sd["equity_curve"])
            lines.append(f"**Equity curve:** {spark}")
            lines.append("")

        # Signal counts
        if sd["signals"]:
            from trading_lab.models import SignalAction
            buys = sum(1 for s in sd["signals"] if s.action == SignalAction.BUY)
            sells = sum(1 for s in sd["signals"] if s.action == SignalAction.SELL)
            holds = sum(1 for s in sd["signals"] if s.action == SignalAction.HOLD)
            lines.append(
                f"**Signals:** BUY {buys} / SELL {sells} / HOLD {holds} "
                f"({len(sd['signals'])} total)"
            )
            lines.append("")

    # -- Interpretation guide --
    lines += [
        "---",
        "",
        "## How to Read This",
        "",
        "- **Return% vs WinRate%** — high return with low win rate = a few big wins carrying the strategy. "
        "High win rate with low return = cutting winners too early.",
        "- **Profit Factor** — > 1.5 is good, > 2.0 is excellent. < 1.0 means the strategy loses money.",
        "- **MaxDD%** — how much you'd have been underwater at the worst point. "
        "Should match your psychological tolerance.",
        "- **Strategy fit** — the best backtest may not be the best strategy for your trading style. "
        "Consider signal frequency, holding period, and complexity.",
        "- **Compare against journaled counts** — are you actually following the best strategy, "
        "or journaling something else entirely?",
        "",
        "---",
        "",
        "*Generated by Sid Trading Lab strategy comparison v1.*",
        "*Past performance does not guarantee future results. No live trades were placed.*",
        "",
    ]

    return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
