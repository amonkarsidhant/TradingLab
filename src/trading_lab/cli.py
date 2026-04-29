import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich import print

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
    # Build strategy kwargs from the CLI options — pass only what the strategy
    # constructor expects.  This is a simple dispatch; a proper per-strategy
    # CLI group would be nicer but we're keeping things boring and flat.
    strategy_kwargs: dict = {}
    if strategy == "simple_momentum":
        strategy_kwargs = {"lookback": lookback}
    elif strategy == "ma_crossover":
        strategy_kwargs = {"fast": fast, "slow": slow}
    elif strategy == "mean_reversion":
        strategy_kwargs = {"period": rsi_period, "oversold": oversold, "overbought": overbought}

    strat = get_strategy(strategy, **strategy_kwargs)

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
