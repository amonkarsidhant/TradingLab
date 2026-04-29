import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich import print

from trading_lab.agents.pipeline import ReviewPipeline, render_review_report
from trading_lab.agents.runner import AgentRunner, detect_provider
from trading_lab.backtest.engine import BacktestEngine
from trading_lab.backtest.report import render_report
from trading_lab.config import get_settings
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.data.market_data import make_provider
from trading_lab.engine import ExecutionEngine
from trading_lab.logger import SnapshotLogger
from trading_lab.reports.daily_journal import DailyJournal
from trading_lab.risk import RiskPolicy
from trading_lab.strategies import get_strategy, list_strategies

app = typer.Typer(help="Sid Trading Lab CLI")


def get_client() -> Trading212Client:
    return Trading212Client(get_settings())


def get_logger() -> SnapshotLogger:
    return SnapshotLogger(get_settings().db_path)


@app.command("account-summary")
def account_summary(
    save_snapshot: bool = typer.Option(
        False, "--save-snapshot", help="Write response to local SQLite snapshot log."
    ),
):
    client = get_client()
    data = client.account_summary()
    if save_snapshot:
        get_logger().save_snapshot("account_summary", data)
        print("[green]Snapshot saved.[/green]")
    print_json(data)


@app.command("positions")
def positions(
    save_snapshot: bool = typer.Option(
        False, "--save-snapshot", help="Write response to local SQLite snapshot log."
    ),
):
    client = get_client()
    data = client.positions()
    if save_snapshot:
        get_logger().save_snapshot("positions", data)
        print("[green]Snapshot saved.[/green]")
    print_json(data)


@app.command("fetch-instruments")
def fetch_instruments(
    output: str = "data/instruments.json",
    save_snapshot: bool = typer.Option(
        False, "--save-snapshot", help="Write response to local SQLite snapshot log."
    ),
):
    client = get_client()
    instruments = client.instruments()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(instruments, indent=2), encoding="utf-8")
    print(f"[green]Saved instruments to {output_path}[/green]")
    if save_snapshot:
        get_logger().save_snapshot("instruments", instruments)
        print("[green]Snapshot saved.[/green]")


@app.command("run-strategy")
def run_strategy(
    strategy: str = typer.Option("simple_momentum"),
    ticker: str = typer.Option("AAPL_US_EQ"),
    dry_run: bool = typer.Option(True),
    data_source: str = typer.Option(
        "static",
        help="Price data source: 'static', 'csv', 'yfinance', or 'chained'.",
    ),
    prices_file: str = typer.Option(
        "",
        help="Path to CSV price file (csv/chained mode only). "
             "Defaults to data/market/prices/{ticker}.csv if not provided.",
    ),
    lookback: int = typer.Option(
        5,
        help="Lookback window in periods for the strategy.",
    ),
    fast: int = typer.Option(
        10,
        help="Fast SMA period (ma_crossover only).",
    ),
    slow: int = typer.Option(
        30,
        help="Slow SMA period (ma_crossover only).",
    ),
    rsi_period: int = typer.Option(
        14,
        help="RSI period (mean_reversion only).",
    ),
    oversold: int = typer.Option(
        30,
        help="RSI oversold threshold (mean_reversion only).",
    ),
    overbought: int = typer.Option(
        70,
        help="RSI overbought threshold (mean_reversion only).",
    ),
):
    kwargs = _build_strategy_kwargs(
        strategy, lookback=lookback, fast=fast, slow=slow,
        rsi_period=rsi_period, oversold=oversold, overbought=overbought,
    )
    strat = get_strategy(strategy, **kwargs)

    provider = make_provider(
        source=data_source,
        ticker=ticker,
        prices_file=prices_file,
        cache_db=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    prices = provider.get_prices(ticker=ticker, lookback=lookback)
    signal = strat.generate_signal(ticker=ticker, prices=prices)

    engine = ExecutionEngine(
        broker=get_client(),
        risk_policy=RiskPolicy(),
        logger=get_logger(),
    )
    result = engine.handle_signal(signal, dry_run=dry_run)
    print_json(result)


@app.command("list-strategies")
def list_strategies_cli():
    """List all available strategies with their names."""
    for name in sorted(list_strategies()):
        print(f"  [bold]{name}[/bold]")


@app.command("backtest")
def backtest(
    strategy: str = typer.Option("simple_momentum"),
    ticker: str = typer.Option("AAPL_US_EQ"),
    data_source: str = typer.Option(
        "static",
        help="Price data source: 'static', 'csv', 'yfinance', or 'chained'.",
    ),
    prices_file: str = typer.Option(
        "",
        help="Path to CSV price file (csv/chained mode only).",
    ),
    lookback: int = typer.Option(5, help="Lookback window for simple_momentum."),
    fast: int = typer.Option(10, help="Fast SMA period (ma_crossover only)."),
    slow: int = typer.Option(30, help="Slow SMA period (ma_crossover only)."),
    rsi_period: int = typer.Option(14, help="RSI period (mean_reversion only)."),
    oversold: int = typer.Option(30, help="RSI oversold (mean_reversion only)."),
    overbought: int = typer.Option(70, help="RSI overbought (mean_reversion only)."),
    capital: float = typer.Option(10_000.0, help="Initial capital for the backtest."),
    output: str = typer.Option("", help="Write markdown report to file. Defaults to stdout."),
):
    """Run a walk-forward backtest and print a markdown report."""
    kwargs = _build_strategy_kwargs(
        strategy, lookback=lookback, fast=fast, slow=slow,
        rsi_period=rsi_period, oversold=oversold, overbought=overbought,
    )
    strat = get_strategy(strategy, **kwargs)

    provider = make_provider(
        source=data_source,
        ticker=ticker,
        prices_file=prices_file,
        cache_db=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    # Fetch a generous amount of history for the backtest.
    prices = provider.get_prices(ticker=ticker, lookback=252)

    engine = BacktestEngine(strat, initial_capital=capital)
    result = engine.run(prices=prices, ticker=ticker)

    report = render_report(result)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Backtest report written to {output_path}[/green]")
    else:
        typer.echo(report)


def _build_strategy_kwargs(name: str, **all_kwargs) -> dict:
    if name == "simple_momentum":
        return {"lookback": all_kwargs["lookback"]}
    if name == "ma_crossover":
        return {"fast": all_kwargs["fast"], "slow": all_kwargs["slow"]}
    if name == "mean_reversion":
        return {
            "period": all_kwargs["rsi_period"],
            "oversold": all_kwargs["oversold"],
            "overbought": all_kwargs["overbought"],
        }
    return {}


@app.command("review-signal")
def review_signal(
    strategy: str = typer.Option("simple_momentum"),
    ticker: str = typer.Option("AAPL_US_EQ"),
    data_source: str = typer.Option(
        "static",
        help="Price data source: 'static', 'csv', 'yfinance', or 'chained'.",
    ),
    prices_file: str = typer.Option("", help="Path to CSV price file."),
    lookback: int = typer.Option(5),
    fast: int = typer.Option(10),
    slow: int = typer.Option(30),
    rsi_period: int = typer.Option(14),
    oversold: int = typer.Option(30),
    overbought: int = typer.Option(70),
    output: str = typer.Option("", help="Write review to file. Defaults to stdout."),
):
    """Run the multi-agent review pipeline against a signal."""
    kwargs = _build_strategy_kwargs(
        strategy, lookback=lookback, fast=fast, slow=slow,
        rsi_period=rsi_period, oversold=oversold, overbought=overbought,
    )
    strat = get_strategy(strategy, **kwargs)

    provider = make_provider(
        source=data_source, ticker=ticker, prices_file=prices_file,
        cache_db=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    prices = provider.get_prices(ticker=ticker, lookback=max(lookback, 20))
    signal = strat.generate_signal(ticker=ticker, prices=prices)

    runner = AgentRunner()
    provider_name, model = detect_provider()
    print(f"[dim]Using {provider_name} / {model}[/dim]")

    pipeline = ReviewPipeline(
        runner=runner,
        db_path=get_settings().db_path,
    )
    result = pipeline.review(signal, prices=prices)
    report = render_review_report(result)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Review written to {output_path}[/green]")
    else:
        typer.echo(report)


@app.command("daily-journal")
def daily_journal(
    date: str = typer.Option(
        "",
        help="Date to report on (YYYY-MM-DD). Defaults to today (UTC).",
    ),
    output: str = typer.Option(
        "",
        help="Write report to this file path. "
             "Example: docs/journal/generated/2026-04-29.md. "
             "Defaults to stdout if not provided.",
    ),
):
    report_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    journal = DailyJournal(get_settings().db_path)
    report = journal.generate(report_date)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Journal written to {output_path}[/green]")
    else:
        typer.echo(report)


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    app()
