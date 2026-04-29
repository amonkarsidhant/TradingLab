import json
from pathlib import Path

import typer
from rich import print

from trading_lab.config import get_settings
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.data.market_data import (
    CsvMarketDataProvider,
    MarketDataProvider,
    StaticMarketDataProvider,
)
from trading_lab.engine import ExecutionEngine
from trading_lab.logger import SnapshotLogger
from trading_lab.risk import RiskPolicy
from trading_lab.strategies.simple_momentum import SimpleMomentumStrategy

app = typer.Typer(help="Sid Trading Lab CLI")


def get_client() -> Trading212Client:
    return Trading212Client(get_settings())


def get_logger() -> SnapshotLogger:
    return SnapshotLogger(get_settings().db_path)


def _get_market_data_provider(
    data_source: str, ticker: str, prices_file: str
) -> MarketDataProvider:
    if data_source == "static":
        return StaticMarketDataProvider()
    if data_source == "csv":
        path = prices_file or f"data/market/prices/{ticker}.csv"
        return CsvMarketDataProvider(path)
    raise typer.BadParameter(
        f"Unknown --data-source '{data_source}'. Use 'static' or 'csv'."
    )


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
        help="Price data source: 'static' (offline deterministic) or 'csv' (local file).",
    ),
    prices_file: str = typer.Option(
        "",
        help="Path to CSV price file (csv mode only). "
             "Defaults to data/market/prices/{ticker}.csv if not provided.",
    ),
    lookback: int = typer.Option(
        5,
        help="Lookback window in periods for the momentum strategy.",
    ),
):
    if strategy != "simple_momentum":
        raise typer.BadParameter("Only simple_momentum exists in the starter kit.")

    provider = _get_market_data_provider(data_source, ticker, prices_file)
    prices = provider.get_prices(ticker=ticker, lookback=lookback)

    strat = SimpleMomentumStrategy(lookback=lookback)
    signal = strat.generate_signal(ticker=ticker, prices=prices)

    engine = ExecutionEngine(
        broker=get_client(),
        risk_policy=RiskPolicy(),
        logger=get_logger(),  # signals are always journaled per risk-policy.md
    )
    result = engine.handle_signal(signal, dry_run=dry_run)
    print_json(result)


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    app()
