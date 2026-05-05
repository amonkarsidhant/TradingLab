import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich import print

from trading_lab.agents.pipeline import ReviewPipeline, render_review_report
from trading_lab.agentic.cash import CashAllocator
from trading_lab.agentic.reflection import MungerReflectionEngine
from trading_lab.agentic.scorer import EntryScorer
from trading_lab.agents.runner import AgentRunner, detect_provider
from trading_lab.backtest.engine import BacktestEngine
from trading_lab.backtest.report import render_report
from trading_lab.backtest.sweep import SweepEngine
from trading_lab.backtest.sweep_report import render_sweep_report
from trading_lab.config import get_settings
from trading_lab.brokers.trading212 import OrderType, Trading212Client
from trading_lab.data.market_data import make_provider
from trading_lab.engine import ExecutionEngine
from trading_lab.factsheet.engine import FactsheetEngine
from trading_lab.factsheet.report import render_factsheet
from trading_lab.logger import SnapshotLogger
from trading_lab.reports.daily_journal import DailyJournal
from trading_lab.reports.dashboard import DashboardGenerator
from trading_lab.reports.strategy_comparison import StrategyComparison
from trading_lab.reports.weekly_report import WeeklyReport
from trading_lab.risk import RiskPolicy
from trading_lab.shadow.account import ShadowAccount
from trading_lab.shadow.report import render_shadow_report
from trading_lab.strategies import get_strategy, list_strategies
from trading_lab import universes as universes_mod

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
    auto_stop: bool = typer.Option(
        False,
        "--auto-stop",
        help="Auto-place a trailing stop on live BUY entries. Ignored under dry-run.",
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
        auto_stop=auto_stop,
    )
    result = engine.handle_signal(signal, dry_run=dry_run)
    print_json(result)


@app.command("strategy-factsheet")
def strategy_factsheet(
    strategy: str = typer.Option("simple_momentum", help="Strategy name to evaluate"),
    ticker: str = typer.Option("AAPL_US_EQ", help="Ticker symbol"),
    capital: float = typer.Option(10_000.0, help="Initial capital for backtests"),
    output: str = typer.Option("", help="Write factsheet to file. Defaults to stdout."),
):
    """Generate a comprehensive strategy factsheet with benchmark, cost sensitivity, and stability."""
    engine = FactsheetEngine(strategy, ticker, capital)
    from trading_lab.data.market_data import make_provider
    provider = make_provider(
        source="chained", ticker=ticker,
        cache_db=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    prices = provider.get_prices(ticker=ticker, lookback=252)
    data = engine.generate(prices=prices)
    report = render_factsheet(data)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Factsheet written to {output_path}[/green]")
    else:
        typer.echo(report)


@app.command("place-stop-order")
def place_stop_order(
    ticker: str = typer.Option(..., help="Ticker symbol, e.g. AAPL_US_EQ"),
    quantity: float = typer.Option(..., help="Positive to buy, negative to sell."),
    stop_price: float = typer.Option(..., help="Stop trigger price."),
    dry_run: bool = typer.Option(True),
    time_validity: str = typer.Option("DAY", help="DAY or GOOD_TILL_CANCEL"),
    save_snapshot: bool = typer.Option(False, "--save-snapshot"),
):
    """Place a stop order on the Trading 212 demo environment."""
    client = get_client()
    result = client.stop_order(
        ticker=ticker,
        quantity=quantity,
        stop_price=stop_price,
        dry_run=dry_run,
        time_validity=time_validity,
    )
    if save_snapshot:
        get_logger().save_snapshot("stop_order", result)
        print("[green]Snapshot saved.[/green]")
    print_json(result)


@app.command("place-limit-order")
def place_limit_order(
    ticker: str = typer.Option(..., help="Ticker symbol, e.g. AAPL_US_EQ"),
    quantity: float = typer.Option(..., help="Positive to buy, negative to sell."),
    limit_price: float = typer.Option(..., help="Limit price for the order."),
    dry_run: bool = typer.Option(True),
    time_validity: str = typer.Option("DAY", help="DAY or GOOD_TILL_CANCEL"),
    save_snapshot: bool = typer.Option(False, "--save-snapshot"),
):
    """Place a limit order on the Trading 212 demo environment."""
    client = get_client()
    result = client.limit_order(
        ticker=ticker,
        quantity=quantity,
        limit_price=limit_price,
        dry_run=dry_run,
        time_validity=time_validity,
    )
    if save_snapshot:
        get_logger().save_snapshot("limit_order", result)
        print("[green]Snapshot saved.[/green]")
    print_json(result)


@app.command("lookup-ticker")
def lookup_ticker(
    query: str = typer.Argument(..., help="Company name or symbol, e.g. 'Apple' or 'TSLA'"),
):
    """Look up a T212 ticker from a company name or symbol."""
    client = get_client()
    results = client.lookup_ticker(query)
    if not results:
        print("[red]No instruments found.[/red]")
        return
    for inst in results:
        print(f"  [bold]{inst.get('ticker')}[/bold]  {inst.get('name')}  ({inst.get('currencyCode', '?')})")


@app.command("cancel-order")
def cancel_order(
    order_id: int = typer.Argument(..., help="Order ID to cancel."),
):
    """Cancel a pending order by ID."""
    client = get_client()
    result = client.cancel_order(order_id)
    print("[green]Cancellation submitted.[/green]")
    print_json(result)


@app.command("pending-orders")
def pending_orders():
    """List all pending / open orders."""
    client = get_client()
    data = client.pending_orders()
    if not data:
        print("[dim]No pending orders.[/dim]")
        return
    print_json(data)


@app.command("reflect")
def reflect(
    output: str = typer.Option("", help="Write reflection to file. Defaults to stdout."),
):
    """Run the Munger Reflection Engine — constant portfolio introspection."""
    engine = MungerReflectionEngine(get_settings())
    try:
        report = engine.reflect()
        formatted = engine.format_reflection(report)
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(formatted, encoding="utf-8")
            print(f"[green]Reflection written to {output_path}[/green]")
        else:
            typer.echo(formatted)
    except Exception as exc:
        print(f"[red]Reflection failed:[/red] {exc}")
        import traceback
        traceback.print_exc()


@app.command("history-orders")
def history_orders(
    ticker: str = typer.Option("", help="Filter by ticker."),
    limit: int = typer.Option(50),
):
    """Fetch historical filled orders from Trading 212."""
    client = get_client()
    items = client.history_orders(ticker=ticker, limit=limit)
    print_json(items)


@app.command("market-order")
def market_order(
    ticker: str = typer.Option(..., help="Ticker symbol, e.g. AAPL_US_EQ"),
    quantity: float = typer.Option(..., help="Positive to buy, negative to sell."),
    extended_hours: bool = typer.Option(False, "--extended-hours"),
    dry_run: bool = typer.Option(True),
    save_snapshot: bool = typer.Option(False, "--save-snapshot"),
):
    """Place a market order. Defaults to dry-run."""
    client = get_client()
    result = client.market_order(
        ticker=ticker, quantity=quantity,
        dry_run=dry_run, extended_hours=extended_hours,
    )
    if save_snapshot:
        get_logger().save_snapshot("market_order", result)
        print("[green]Snapshot saved.[/green]")
    print_json(result)


@app.command("place-stop-limit-order")
def place_stop_limit_order(
    ticker: str = typer.Option(..., help="Ticker symbol, e.g. AAPL_US_EQ"),
    quantity: float = typer.Option(..., help="Positive to buy, negative to sell."),
    stop_price: float = typer.Option(..., help="Stop trigger price."),
    limit_price: float = typer.Option(..., help="Limit price once stop triggers."),
    dry_run: bool = typer.Option(True),
    time_validity: str = typer.Option("DAY"),
    save_snapshot: bool = typer.Option(False, "--save-snapshot"),
):
    """Place a stop-limit order on the Trading 212 demo environment."""
    client = get_client()
    result = client.stop_limit_order(
        ticker=ticker, quantity=quantity,
        stop_price=stop_price, limit_price=limit_price,
        dry_run=dry_run, time_validity=time_validity,
    )
    if save_snapshot:
        get_logger().save_snapshot("stop_limit_order", result)
    print_json(result)


@app.command("get-order")
def get_order(order_id: int = typer.Argument(..., help="Order ID to fetch.")):
    """Get details of a single order by ID."""
    print_json(get_client().get_order(order_id))


@app.command("replace-order")
def replace_order(
    order_id: int = typer.Argument(..., help="Existing order ID to cancel."),
    order_type: str = typer.Option(..., help="MARKET, LIMIT, STOP, or STOP_LIMIT"),
    ticker: str = typer.Option(...),
    quantity: float = typer.Option(...),
    limit_price: float = typer.Option(0.0, help="Required for LIMIT / STOP_LIMIT."),
    stop_price: float = typer.Option(0.0, help="Required for STOP / STOP_LIMIT."),
    time_validity: str = typer.Option("DAY"),
    dry_run: bool = typer.Option(True),
):
    """Cancel an existing order and replace it with new params."""
    client = get_client()
    result = client.replace_order(
        order_id=order_id,
        order_type=OrderType(order_type.upper()),
        ticker=ticker,
        quantity=quantity,
        limit_price=limit_price or None,
        stop_price=stop_price or None,
        time_validity=time_validity,
        dry_run=dry_run,
    )
    print_json(result)


@app.command("bracket-order")
def bracket_order(
    ticker: str = typer.Option(...),
    quantity: float = typer.Option(..., help="Positive entry quantity (long-only)."),
    stop_price: float = typer.Option(..., help="Protective stop-loss price."),
    take_profit_price: float = typer.Option(..., help="Take-profit limit price."),
    dry_run: bool = typer.Option(True),
):
    """Market entry + protective stop + take-profit limit (best-effort)."""
    client = get_client()
    result = client.bracket_order(
        ticker=ticker, quantity=quantity,
        stop_price=stop_price, take_profit_price=take_profit_price,
        dry_run=dry_run,
    )
    print_json(result)


@app.command("history-dividends")
def history_dividends(
    ticker: str = typer.Option(""),
    limit: int = typer.Option(50),
):
    """Fetch dividend history."""
    print_json(get_client().history_dividends(ticker=ticker, limit=limit))


@app.command("history-transactions")
def history_transactions(limit: int = typer.Option(50)):
    """Fetch account transaction history (deposits, withdrawals, fees)."""
    print_json(get_client().history_transactions(limit=limit))


@app.command("exchanges")
def exchanges():
    """List exchanges and their trading schedules."""
    print_json(get_client().exchanges())


@app.command("request-export")
def request_export(
    time_from: str = typer.Option(..., help="ISO 8601, e.g. 2025-01-01T00:00:00Z"),
    time_to: str = typer.Option(..., help="ISO 8601, e.g. 2025-12-31T23:59:59Z"),
    include_dividends: bool = typer.Option(True),
    include_interest: bool = typer.Option(True),
    include_orders: bool = typer.Option(True),
    include_transactions: bool = typer.Option(True),
):
    """Request a CSV export job. Use list-exports to poll status."""
    client = get_client()
    result = client.request_export(
        time_from=time_from, time_to=time_to,
        include_dividends=include_dividends, include_interest=include_interest,
        include_orders=include_orders, include_transactions=include_transactions,
    )
    print_json(result)


@app.command("list-exports")
def list_exports():
    """List CSV exports with status / download links."""
    print_json(get_client().list_exports())


# ── Discovery: instruments + universes ────────────────────────────────────────

@app.command("instruments-stats")
def instruments_stats():
    """Show counts of the cached T212 instrument universe (by type/currency/exchange/country)."""
    client = get_client()
    cache = client._instrument_cache
    cache.load_from_db()
    if cache.count == 0:
        print("[yellow]Cache empty — run `fetch-instruments` first.[/yellow]")
        return
    stats = cache.stats()
    print(f"[bold]Total cached: {stats['total']['all']}[/bold]\n")
    for group_name, group in stats.items():
        if group_name == "total":
            continue
        top = sorted(group.items(), key=lambda kv: -kv[1])[:15]
        print(f"[bold]{group_name}[/bold]")
        for k, v in top:
            print(f"  {k:<12} {v}")
        print()


@app.command("instruments-search")
def instruments_search(
    type: str = typer.Option("", help="STOCK, ETF, or WARRANT"),
    currency: str = typer.Option("", help="USD, EUR, GBP, ..."),
    exchange: str = typer.Option("", help="Exchange code, parsed from ticker (US, UK, DE, ...)."),
    country: str = typer.Option("", help="ISIN issuer country (US, CA, GB, ...)."),
    search: str = typer.Option("", help="Substring match on ticker/name/shortName."),
    limit: int = typer.Option(50),
):
    """Filter the cached instrument universe. AND across non-empty options."""
    client = get_client()
    cache = client._instrument_cache
    cache.load_from_db()
    if cache.count == 0:
        print("[yellow]Cache empty — run `fetch-instruments` first.[/yellow]")
        return
    results = cache.filter(
        type=type, currency=currency, exchange=exchange,
        country=country, search=search, limit=limit,
    )
    if not results:
        print("[red]No instruments match the filter.[/red]")
        return
    print(f"[dim]Showing {len(results)} of total cache size {cache.count}[/dim]\n")
    for inst in results:
        print(
            f"  [bold]{inst.get('ticker'):<22}[/bold] "
            f"{inst.get('type', '?'):<7} "
            f"{inst.get('currencyCode', '?'):<4} "
            f"{inst.get('name', '')}"
        )


@app.command("universe-list")
def universe_list():
    """List all curated diversification universes."""
    for name, items in universes_mod.all_universes().items():
        size = sum(len(v) for v in items.values()) if isinstance(next(iter(items.values()), None), list) else len(items)
        print(f"  [bold]{name}[/bold]  ({size} tickers)")


@app.command("universe-show")
def universe_show(name: str = typer.Argument(..., help="sectors, indexes, geographic, bonds, commodities, sp500_sectors")):
    """Print all tickers in one universe."""
    universes = universes_mod.all_universes()
    if name not in universes:
        print(f"[red]Unknown universe '{name}'. Try one of: {list(universes.keys())}[/red]")
        raise typer.Exit(1)
    universe = universes[name]
    if isinstance(next(iter(universe.values()), None), list):
        # sp500_sectors: dict[sector, list[ticker]]
        for sector, tickers in universe.items():
            print(f"\n[bold]{sector}[/bold]")
            for t in tickers:
                print(f"  {t}")
    else:
        for label, ticker in universe.items():
            print(f"  [bold]{ticker:<14}[/bold] {label}")


@app.command("universe-diversify")
def universe_diversify(
    categories: str = typer.Option(
        "indexes,geographic,bonds,commodities",
        help="Comma-separated category list. Add 'sectors' for a random sector ETF.",
    ),
    seed: int = typer.Option(0, help="Random seed (0 = nondeterministic)."),
):
    """Suggest a diversified ETF basket — one ticker per category."""
    cats = [c.strip() for c in categories.split(",") if c.strip()]
    basket = universes_mod.diversify(categories=cats, seed=seed or None)
    print(f"[bold]Diversified basket ({len(basket.tickers)} tickers)[/bold]\n")
    for label, ticker in basket.sources.items():
        print(f"  [bold]{ticker:<14}[/bold] {label}")


@app.command("sector-sample")
def sector_sample(
    sector: str = typer.Argument(..., help="GICS sector name, e.g. 'Technology'."),
    count: int = typer.Option(3),
    seed: int = typer.Option(0),
):
    """Pick `count` random S&P 500 tickers from one GICS sector."""
    try:
        tickers = universes_mod.sector_sample(sector, count=count, seed=seed or None)
    except KeyError as exc:
        print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    print(f"[bold]{sector} — {len(tickers)} picks[/bold]")
    for t in tickers:
        print(f"  {t}")


@app.command("instrument-info")
def instrument_info(ticker: str = typer.Argument(..., help="T212 ticker, e.g. AAPL_US_EQ")):
    """Fetch sector/industry/market-cap/PE for one ticker via yfinance.

    Slow (~1s per call) and rate-limited by Yahoo. Use sparingly.
    """
    from trading_lab.brokers.trading212 import _t212_ticker_to_yf
    try:
        import yfinance as yf
    except ImportError:
        print("[red]yfinance not installed.[/red]")
        raise typer.Exit(1)
    yf_symbol = _t212_ticker_to_yf(ticker)
    info = yf.Ticker(yf_symbol).info or {}
    keys = [
        "shortName", "longName", "sector", "industry", "country",
        "marketCap", "trailingPE", "forwardPE", "dividendYield",
        "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "averageVolume", "currency",
    ]
    extracted = {k: info.get(k) for k in keys if info.get(k) is not None}
    if not extracted:
        print(f"[yellow]No yfinance data for {yf_symbol} (T212: {ticker}).[/yellow]")
        return
    print(f"[bold]{ticker}[/bold]  (yfinance: {yf_symbol})\n")
    for k, v in extracted.items():
        print(f"  {k:<20} {v}")


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
    commission: float = typer.Option(
        0.0, "--commission",
        help="Commission as a fraction (0.001 = 10 bps). Applied to entry and exit notional.",
    ),
    slippage: float = typer.Option(
        0.0, "--slippage",
        help="Slippage as a fraction (0.001 = 10 bps). Worsens fill price on both sides.",
    ),
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

    engine = BacktestEngine(
        strat, initial_capital=capital,
        commission_pct=commission, slippage_pct=slippage,
    )
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


@app.command("param-sweep")
def param_sweep(
    strategy: str = typer.Option("simple_momentum"),
    ticker: str = typer.Option("AAPL_US_EQ"),
    data_source: str = typer.Option("static", help="static, csv, yfinance, or chained."),
    prices_file: str = typer.Option("", help="Path to CSV price file."),
    capital: float = typer.Option(10_000.0, help="Initial capital for backtests."),
    rank_by: str = typer.Option(
        "sharpe_ratio",
        help="Metric to rank by: sharpe_ratio, profit_factor, total_return_pct, win_rate.",
    ),
    output: str = typer.Option("", help="Write markdown report to file. Defaults to stdout."),
):
    """Run a parameter sweep — test many strategy parameter combos and find the best."""
    cls = list_strategies().get(strategy)
    if not cls:
        print(f"[red]Unknown strategy '{strategy}'.[/red]")
        raise typer.Exit(1)

    provider = make_provider(
        source=data_source, ticker=ticker, prices_file=prices_file,
        cache_db=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    prices = provider.get_prices(ticker=ticker, lookback=252)

    grid = _default_grid(strategy)

    engine = SweepEngine(cls, param_grid=grid, rank_by=rank_by, capital=capital)
    result = engine.run(prices=prices, ticker=ticker)

    report = render_sweep_report(result)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Sweep report written to {output_path}[/green]")
    else:
        typer.echo(report)


def _default_grid(strategy: str) -> dict:
    if strategy == "simple_momentum":
        return {
            "lookback": [3, 5, 7, 10, 14, 20],
            "threshold_pct": [0.5, 1.0, 2.0, 3.0],
        }
    if strategy == "ma_crossover":
        return {
            "fast": [5, 8, 13],
            "slow": [21, 34, 55],
        }
    if strategy == "mean_reversion":
        return {
            "period": [7, 14, 21],
            "oversold": [20, 25, 30],
            "overbought": [65, 70, 75],
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


@app.command("shadow-report")
def shadow_report(
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
    from_date: str = typer.Option("", help="Start date (YYYY-MM-DD)."),
    to_date: str = typer.Option("", help="End date (YYYY-MM-DD)."),
    output: str = typer.Option("", help="Write report to file. Defaults to stdout."),
):
    """Compare mechanical strategy execution against journaled signals."""
    kwargs = _build_strategy_kwargs(
        strategy, lookback=lookback, fast=fast, slow=slow,
        rsi_period=rsi_period, oversold=oversold, overbought=overbought,
    )
    strat = get_strategy(strategy, **kwargs)

    provider = make_provider(
        source=data_source, ticker=ticker, prices_file=prices_file,
        cache_db=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    prices = provider.get_prices(ticker=ticker, lookback=252)

    shadow = ShadowAccount(strategy=strat, db_path=get_settings().db_path)
    result = shadow.compare(
        prices=prices,
        ticker=ticker,
        from_date=from_date,
        to_date=to_date,
    )

    report = render_shadow_report(result)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Shadow report written to {output_path}[/green]")
    else:
        typer.echo(report)


@app.command("dashboard")
def dashboard(
    ticker: str = typer.Option("AAPL_US_EQ"),
    data_source: str = typer.Option(
        "static",
        help="Price data source: 'static', 'csv', 'yfinance', or 'chained'.",
    ),
    prices_file: str = typer.Option("", help="Path to CSV price file."),
    output: str = typer.Option(
        "",
        help="Write HTML dashboard to file. Defaults to stdout.",
    ),
):
    """Generate a static HTML dashboard with embedded data. No server required."""
    generator = DashboardGenerator(
        db_path=get_settings().db_path,
        cache_db_path=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    html = generator.generate(
        ticker=ticker,
        data_source=data_source,
        prices_file=prices_file,
    )
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        print(f"[green]Dashboard written to {output_path}[/green]")
    else:
        typer.echo(html)


@app.command("weekly-report")
def weekly_report(
    date: str = typer.Option(
        "",
        help="Date in the target week (YYYY-MM-DD). Defaults to today (UTC).",
    ),
    output: str = typer.Option(
        "",
        help="Write markdown report to file. Defaults to stdout.",
    ),
):
    """Generate a weekly summary report aggregating one trading week (Mon-Fri)."""
    report_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = WeeklyReport(get_settings().db_path).generate(report_date)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Weekly report written to {output_path}[/green]")
    else:
        typer.echo(report)


@app.command("strategy-comparison")
def strategy_comparison(
    ticker: str = typer.Option("AAPL_US_EQ"),
    data_source: str = typer.Option(
        "static",
        help="Price data source: 'static', 'csv', 'yfinance', or 'chained'.",
    ),
    prices_file: str = typer.Option("", help="Path to CSV price file."),
    capital: float = typer.Option(10_000.0, help="Initial capital for backtests."),
    output: str = typer.Option(
        "",
        help="Write markdown report to file. Defaults to stdout.",
    ),
):
    """Side-by-side metrics comparing all registered strategies."""
    comparison = StrategyComparison(
        db_path=get_settings().db_path,
        cache_db_path=get_settings().db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    report = comparison.compare(
        ticker=ticker,
        data_source=data_source,
        prices_file=prices_file,
        initial_capital=capital,
    )
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"[green]Comparison report written to {output_path}[/green]")
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


@app.command("autonomous-cycle")
def autonomous_cycle_cmd():
    """Run one fully autonomous cycle: detect regime → select strategy → scan → log."""
    from trading_lab.commands.autonomous_cycle import run_autonomous_cycle
    result = run_autonomous_cycle()
    print_json(result)


@app.command("scan-rank")
def scan_rank(
    strategy: str = typer.Option("simple_momentum", help="Strategy to score candidates on"),
    tickers: str = typer.Option("AAPL_US_EQ,MSFT_US_EQ,NVDA_US_EQ,GOOGL_US_EQ,AMZN_US_EQ,META_US_EQ,TSLA_US_EQ,AMD_US_EQ,KO_US_EQ,JNJ_US_EQ,PG_US_EQ,V_US_EQ,MA_US_EQ", help="Comma-separated tickers to rank"),
    capital: float = typer.Option(10_000.0, help="Capital for backtest"),
    top_n: int = typer.Option(5, help="Show top N results"),
):
    """Rank ticker+strategy combinations by objective factsheet data, not AI comfort."""
    ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]
    candidates = [(strategy, t) for t in ticker_list]
    scorer = EntryScorer()
    print(f"[dim]Scoring {len(candidates)} candidates with {strategy}...[/dim]")
    results = scorer.rank(candidates, capital)
    print(f"\n[bold]Top {min(top_n, len(results))} of {len(results)} candidates:[/bold]\n")
    print(f"{'Rank':<5} {'Ticker':<20} {'Score':<8} {'Sharpe':<8} {'PF':<6} {'Stable':<8} {'Outperf':<8} {'Verdict':<10}")
    print("-" * 75)
    for i, r in enumerate(results[:top_n], 1):
        f = r["factors"]
        print(f"{i:<5} {r['ticker']:<20} {r['score']:<8} {f['sharpe']['raw']:<8} {str(f['profit_factor']['raw'] or '-'):<6} {'Y' if f['stability']['stable'] else 'N':<8} {f['outperformance']['raw']:<8} {r['verdict']:<10}")


# ── Phase 0: regime-aware commands ──────────────────────────────────────────────────

@app.command("detect-regime")
def detect_regime_cmd():
    """Detect current market regime from VIXY, SPY, breadth, and sector rotation."""
    from trading_lab.regime.detector import RegimeDetector
    state = RegimeDetector().detect()
    print(f"[bold]Regime: {state.regime.value}[/bold] (confidence: {state.confidence:.2f})")
    print(f"  VIX proxy (VIXY):    {state.vix_proxy:.2f}")
    print(f"  Market breadth:      {state.breadth_pct:.2%}")
    print(f"  Sector rotation:     {state.sector_rotation:.3f}")
    print(f"  Trend score:         {state.trend_score:.4f}")
    print(f"  Timestamp:           {state.timestamp}")


@app.command("strategy-rank-by-regime")
def strategy_rank_by_regime(
    regime: str = typer.Option("", help="Regime to query (or 'current' to detect live)"),
    min_trades: int = typer.Option(5, help="Minimum trades for inclusion"),
):
    """Rank strategies by Sharpe for a given regime."""
    from trading_lab.regime.detector import RegimeDetector
    from trading_lab.registry.selector import StrategySelector
    from trading_lab.registry.performance import StrategyPerformanceRegistry

    if regime == "current" or not regime:
        state = RegimeDetector().detect()
        regime = state.regime.value
        print(f"[dim]Detected regime: {regime} (confidence {state.confidence:.2f})[/dim]\n")

    registry = StrategyPerformanceRegistry()
    rows = registry.all_for_regime(regime)
    filtered = [r for r in rows if r["trade_count"] >= min_trades]

    if not filtered:
        print(f"[yellow]No strategies with >= {min_trades} trades for regime '{regime}'.[/yellow]")
        print(f"  Available records: {len(rows)} (all with fewer trades)")
        return

    print(f"[bold]Strategies ranked for regime: {regime}[/bold]\n")
    print(f"{'#':<4} {'Strategy':<20} {'Sharpe':<8} {'Win%':<8} {'Trades':<8} {'AvgDays':<10}")
    print("-" * 60)
    for i, r in enumerate(filtered, 1):
        print(f"{i:<4} {r['strategy_id']:<20} {r['sharpe']:<8.2f} {r['win_rate']:<8.2%} {r['trade_count']:<8} {r['avg_hold_days']:<10.1f}")


@app.command("allocate")
def allocate(
    save_snapshot: bool = typer.Option(False, "--save-snapshot"),
):
    """Check current cash allocation against regime target and recommend deployment."""
    settings = get_settings()
    from trading_lab.brokers.trading212 import Trading212Client
    client = Trading212Client(settings)
    summary = client.account_summary()
    total = summary.get("totalValue", 0)
    cash = summary.get("cash", {}).get("availableToTrade", 0)
    positions_raw = client.positions()
    pos_count = len(positions_raw)
    allocator = CashAllocator(
        cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
    )
    result = allocator.analyze(total, cash, pos_count)
    print(f"[bold]Regime:[/bold] {result['regime']}")
    print(f"  {result['regime_description']}")
    print(f"[bold]Cash:[/bold] {result['actual_cash_pct']}% (target: {result['target_cash_pct']}%)")
    print(f"  Gap: {result['gap_pct']:+.1f}% (€{result['gap_value']:+,.2f})")
    print(f"[bold]Action:[/bold] {result['action']}")
    print(f"  Free slots: {result['free_slots']}")
    print(f"  Deployable per slot: €{result['deployable_per_slot']:,.2f}")
    print(f"  Max position size: {result['max_position_pct']}%")
    print(f"  Recommended stop: {result['recommended_stop_pct']}%")
    print(f"  Preferred strategies: {', '.join(result['preferred_strategies'])}")
    if save_snapshot:
        get_logger().save_snapshot("allocation", result)
        print("[green]Snapshot saved.[/green]")


@app.command("seed-registry")
def seed_registry_command(
    days: int = typer.Option(180, "--days", "-d", help="Historical lookback days"),
    tickers: str = typer.Option(
        "SPY,AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,CRM",
        "--tickers", "-t", help="Comma-separated tickers to backtest",
    ),
    db_path: str = typer.Option("./trading_lab.sqlite3", "--db-path", help="SQLite DB path"),
    min_window: int = typer.Option(10, "--min-window", help="Minimum regime window days"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would happen without writing"),
    fast: bool = typer.Option(False, "--fast", help="Seed with SPY only (faster)"),
):
    """Seed strategy_regime_performance with historical backtests."""
    import subprocess, sys
    script = Path(__file__).resolve().parent.parent / "scripts" / "seed_registry.py"
    args = [
        sys.executable, str(script),
        "--days", str(days),
        "--tickers", tickers,
        "--db-path", db_path,
        "--min-window", str(min_window),
    ]
    if dry_run:
        args.append("--dry-run")
    if fast:
        args.append("--fast")
    subprocess.run(args)


@app.command("sweep-strategies")
def sweep_strategies(
    tickers: str = typer.Option(
        "SPY,AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,CRM",
        "--tickers", "-t", help="Comma-separated tickers",
    ),
    lookback_days: int = typer.Option(126, "--lookback", "-l", help="Days to backtest per window"),
    save_registry: bool = typer.Option(True, "--save/--no-save", help="Write to strategy_regime_performance"),
):
    """Walk-forward sweep: backtest all strategies across regime windows."""
    from trading_lab.meta.sweeper import StrategySweeper
    tlist = [t.strip() for t in tickers.split(",")]
    sweeper = StrategySweeper(tickers=tlist, lookback_days=lookback_days)
    results = sweeper.sweep(save_registry=save_registry)
    print(f"\n[bold]Sweep complete. {len(results)} results.[/bold]\n")
    print(f"{'Strategy':<20} {'Regime':<12} {'Sharpe':<8} {'Win%':<8} {'Trades':<8}")
    print("-" * 60)
    for r in results:
        print(f"{r.strategy_id:<20} {r.regime:<12} {r.sharpe:<8.2f} {r.win_rate:<8.2%} {r.total_trades:<8}")


@app.command("regime-allocate")
def regime_allocate(
    regime: str = typer.Option("", "--regime", "-r", help="Regime name (omit for auto-detect)"),
    strategy: str = typer.Option("", "--strategy", "-s", help="Strategy ID (omit for best in regime)"),
    total_equity: float = typer.Option(0.0, "--equity", "-e", help="Total equity (0 = fetch from T212)"),
    open_positions: int = typer.Option(-1, "--positions", "-p", help="Open position count (-1 = auto)"),
    tickers: str = typer.Option("SPY,AAPL,MSFT", "--tickers", "-t", help="Comma-separated tickers"),
):
    """Regime-aware position sizing using backtest Sharpe from registry."""
    from trading_lab.meta.allocator import CapitalAllocator
    from trading_lab.brokers.trading212 import Trading212Client
    from trading_lab.regime.detector import RegimeDetector
    from trading_lab.registry.selector import StrategySelector

    settings = get_settings()

    if not regime:
        state = RegimeDetector().detect()
        regime = state.regime.value
        print(f"[dim]Detected regime: {regime} (confidence {state.confidence:.2f})[/dim]\n")

    if not strategy:
        selector = StrategySelector()
        strategy, confidence = selector.select(state)
        print(f"Selected strategy: {strategy} (confidence {confidence:.2f})")

    if total_equity <= 0:
        client = Trading212Client(settings)
        summary = client.account_summary()
        total_equity = summary.get("totalValue", 0)
        cash = summary.get("cash", {}).get("availableToTrade", 0)
        open_positions = open_positions if open_positions >= 0 else len(client.positions())
    else:
        cash = None

    allocator = CapitalAllocator()
    tlist = [t.strip() for t in tickers.split(",")]
    allocations = allocator.allocate(
        regime=regime,
        strategy_id=strategy,
        total_equity=total_equity,
        open_positions=open_positions,
        tickers=tlist,
        current_cash=cash,
    )

    print(f"[bold]Allocations for {regime} / {strategy}[/bold]\n")
    print(f"{'Ticker':<8} {'Value':<12} {'%Equity':<10} {'Conf':<8} {'Reason'}")
    print("-" * 60)
    for a in allocations:
        print(f"{a.ticker:<8} ${a.target_value:<11,.2f} {a.target_pct:<10.2%} {a.confidence:<8.2f} {a.reason}")


@app.command("ab-test")
def ab_test(
    baseline: str = typer.Option("simple_momentum", "--baseline", "-b", help="Baseline strategy"),
    variant: str = typer.Option("mean_reversion", "--variant", "-v", help="Variant strategy"),
    tickers: str = typer.Option(
        "SPY,AAPL,MSFT,GOOGL,AMZN", "--tickers", "-t", help="Comma-separated tickers",
    ),
    lookback_days: int = typer.Option(126, "--lookback", "-l", help="Backtest days per ticker"),
    persist: bool = typer.Option(True, "--persist/--no-persist", help="Save results to SQLite"),
):
    """A/B test two strategies on the same tickers. Verdict: pass, fail, inconclusive."""
    from trading_lab.meta.ab_harness import ABHarness
    tlist = [t.strip() for t in tickers.split(",")]
    harness = ABHarness()
    results = harness.compare(baseline, variant, tickers=tlist, lookback_days=lookback_days, persist=persist)
    print(f"\n[bold]A/B Test: {baseline} vs {variant}[/bold]\n")
    print(f"{'Ticker':<8} {'Base#':<6} {'Var#':<6} {'SharpeDiff':<11} {'WinDiff':<9} {'t-stat':<8} {'p-value':<10} {'Verdict'}")
    print("-" * 80)
    for r in results:
        print(
            f"{r.ticker:<8} {r.baseline_trades:<6} {r.variant_trades:<6} "
            f"{r.sharpe_diff:+10.2f} {r.win_rate_diff:+8.1f}% "
            f"{r.t_stat!s:<8} {r.p_value!s:<10} {r.verdict.upper()}"
        )
    adopted = [r.ticker for r in results if r.verdict == "pass"]
    if adopted:
        print(f"\n[green]Variant PASSES on: {', '.join(adopted)}[/green]")
    if persist:
        print(f"\n[dim]Results saved to ab_results table.[/dim]")


@app.command("generate-variants")
def generate_variants_command(
    strategy: str = typer.Option("simple_momentum", "--strategy", "-s", help="Base strategy to mutate"),
    n: int = typer.Option(3, "--n", help="Number of variants to generate"),
):
    """Use LLM to generate strategy variants targeting the weakest regime."""
    from trading_lab.meta.variant_generator import StrategyVariantGenerator
    gen = StrategyVariantGenerator()
    variants = gen.generate(strategy, n_variants=n)
    if not variants:
        print("[red]No variants generated. Check LLM provider config.[/red]")
        return
    print(f"\n[bold]Generated {len(variants)} variants for {strategy}[/bold]\n")
    for i, v in enumerate(variants, 1):
        print(f"{i}. [cyan]{v.name}[/cyan]")
        print(f"   Rationale: {v.rationale}")
        print(f"   Weakest regime: {v.weakest_regime}")
        print(f"   Code preview: {v.code[:120]}...")
        print()


@app.command("sandbox-test")
def sandbox_test_command(
    file: str = typer.Option(..., "--file", "-f", help="Path to variant .py file"),
):
    """Validate generated strategy code: syntax, imports, instantiation, test call."""
    from trading_lab.meta.sandbox import SyntaxSandbox
    path = Path(file)
    if not path.exists():
        print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)
    source = path.read_text()
    result = SyntaxSandbox.validate(source)
    print(f"\n[bold]Sandbox Test: {file}[/bold]\n")
    status = "[green]PASS[/green]" if result.valid else "[red]FAIL[/red]"
    print(f"Valid: {status}")
    if result.error:
        print(f"Error: {result.error}")
    if result.forbidden_imports:
        print(f"Forbidden imports: {', '.join(result.forbidden_imports)}")
    print(f"Has generate_signal: {result.has_generate_signal}")
    print(f"SignalAction valid: {result.signal_action_valid}")
    if result.test_signal:
        print(f"Test signal: {result.test_signal}")


@app.command("validate-variant")
def validate_variant_command(
    file: str = typer.Option(..., "--file", "-f", help="Path to variant .py file"),
    baseline: str = typer.Option("simple_momentum", "--baseline", "-b", help="Baseline strategy"),
    tickers: str = typer.Option("SPY", "--tickers", "-t", help="Comma-separated tickers"),
    lookback: int = typer.Option(126, "--lookback", "-l", help="Backtest days"),
):
    """Run backtest + A/B composite gate on a variant against baseline."""
    from trading_lab.meta.variant_validator import VariantValidator
    path = Path(file)
    if not path.exists():
        print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)
    source = path.read_text()
    validator = VariantValidator()
    tlist = [t.strip() for t in tickers.split(",")]
    result = validator.validate(source, baseline, tickers=tlist, lookback_days=lookback)
    if result is None:
        print("[red]Validation failed — no results[/red]")
        return
    print(f"\n[bold]Variant Validation: {result.variant_name} vs {baseline}[/bold]\n")
    status = "[green]PASS[/green]" if result.passes else "[red]FAIL[/red]"
    print(f"Verdict: {status}")
    print(f"Sharpe diff: {result.sharpe_diff:+.3f}")
    print(f"Win rate diff: {result.win_rate_diff:+.1%}")
    print(f"Drawdown delta: {result.dd_delta:+.2f}%")
    print(f"p-value: {result.p_value}")
    print(f"Composite score: {result.composite_score:.3f}")
    print(f"Reason: {result.reason}")


@app.command("adopt-variant")
def adopt_variant_command(
    file: str = typer.Option(..., "--file", "-f", help="Path to variant .py file"),
    baseline: str = typer.Option("simple_momentum", "--baseline", "-b", help="Baseline strategy"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without git commit"),
    force: bool = typer.Option(False, "--force", help="Skip validation and adopt directly"),
):
    """Adopt a validated variant: git commit + swap active strategy."""
    from trading_lab.meta.adoption_manager import AdoptionManager
    from trading_lab.meta.variant_validator import VariantValidator
    path = Path(file)
    if not path.exists():
        print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)
    source = path.read_text()

    # Auto-validate unless --force
    validation = None
    if not force:
        validator = VariantValidator()
        validation = validator.validate(source, baseline)
        if validation is None or not validation.passes:
            print("[red]Validation failed. Use --force to override.[/red]")
            if validation:
                print(f"Reason: {validation.reason}")
            return

    manager = AdoptionManager()
    variant_name = Path(file).stem
    result = manager.adopt(
        variant_source=source,
        variant_name=variant_name,
        baseline_id=baseline,
        validation=validation,
        dry_run=dry_run,
    )
    print(f"\n[bold]Adoption Result[/bold]\n")
    print(f"Strategy: {result.strategy_id}")
    print(f"Action: {result.action}")
    if result.git_commit:
        print(f"Git commit: {result.git_commit[:8]}")
    if result.pre_adopt_tag:
        print(f"Pre-adoption tag: {result.pre_adopt_tag}")
    if result.error:
        print(f"[red]Error: {result.error}[/red]")


@app.command("rollback-strategy")
def rollback_strategy_command(
    variant: str = typer.Option(..., "--variant", "-v", help="Variant strategy ID to roll back"),
    baseline: str = typer.Option("simple_momentum", "--baseline", "-b", help="Baseline to restore"),
    reason: str = typer.Option("live_performance_degraded", "--reason", "-r", help="Rollback reason"),
):
    """Rollback to pre-adoption baseline strategy."""
    from trading_lab.meta.adoption_manager import AdoptionManager
    manager = AdoptionManager()
    result = manager.rollback(variant, baseline, reason=reason)
    print(f"\n[bold]Rollback Result[/bold]\n")
    print(f"Variant: {result.strategy_id}")
    print(f"Action: {result.action}")
    if result.git_commit:
        print(f"Git commit: {result.git_commit[:8]}")
    if result.pre_adopt_tag:
        print(f"Restored from tag: {result.pre_adopt_tag}")
    if result.error:
        print(f"[red]Error: {result.error}[/red]")


@app.command("watchdog-check")
def watchdog_check_command(
    variant: str = typer.Option(..., "--variant", "-v", help="Variant strategy ID"),
    baseline: str = typer.Option("simple_momentum", "--baseline", "-b", help="Baseline strategy ID"),
):
    """Check 48h observation window after adoption."""
    from trading_lab.meta.watchdog import AdoptionWatchdog
    w = AdoptionWatchdog()
    result = w.check(variant, baseline)
    print(f"\n[bold]Watchdog Check: {variant}[/bold]\n")
    status_color = {
        "observing": "[yellow]",
        "confirmed": "[green]",
        "rollback_triggered": "[red]",
        "rollback_failed": "[red]",
        "insufficient_data": "[dim]",
    }.get(result.status, "")
    print(f"Status: {status_color}{result.status.upper()}[/]")
    print(f"Hours elapsed: {result.hours_elapsed}")
    print(f"Live Sharpe: {result.live_sharpe:.2f} (expected: {result.expected_sharpe:.2f})")
    print(f"Live Drawdown: {result.live_drawdown:.1f}% (expected: {result.expected_drawdown:.1f}%)")
    print(f"Reason: {result.reason}")


@app.command("strategy-history")
def strategy_history_command(
    strategy: str = typer.Option("", "--strategy", "-s", help="Filter to one strategy"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows"),
):
    """Show immutable audit trail of strategy mutations."""
    from trading_lab.meta.change_log import ChangeLog
    log = ChangeLog()
    rows = log.list_changes(strategy_id=strategy, limit=limit)
    if not rows:
        print("[dim]No change log entries found.[/dim]")
        return
    print(f"\n[bold]Strategy Change Log[/bold] ({len(rows)} entries)\n")
    print(f"{'Time':<20} {'Strategy':<25} {'Action':<10} {'Score':<8} {'Reason'}")
    print("-" * 100)
    for r in rows:
        ts = r.get("timestamp", "")[:19]
        sid = r.get("strategy_id", "")
        action = r.get("action", "")
        score = r.get("composite_score", 0.0)
        reason = (r.get("reason", "") or "")[:50]
        print(f"{ts:<20} {sid:<25} {action:<10} {score:<8.2f} {reason}")
    print(f"\n[dim]Success rate: {log.success_rate():.1f}% (adoptions not rolled back)[/dim]")


@app.command("performance-feedback")
def performance_feedback(
    strategy_id: str = typer.Option("", "--strategy", "-s", help="Filter to one strategy"),
    since: str = typer.Option("", "--since", help="YYYY-MM-DD (default: 7 days ago)"),
    report: bool = typer.Option(False, "--report", help="Write to file"),
):
    """Compare live P&L to backtest expected — flag divergence."""
    from trading_lab.meta.performance_feedback import PerformanceFeedback
    fb = PerformanceFeedback()
    results = fb.report(since=since, strategy_id=strategy_id)
    if not results:
        print("[yellow]No live trades with regime labels found.[/yellow]")
        return
    print(f"\n[bold]Performance Feedback[/bold]\n")
    print(f"{'Strategy':<20} {'Regime':<12} {'LiveSharpe':<11} {'ExpSharpe':<11} {'Alert':<8} {'Reason'}")
    print("-" * 90)
    for r in results:
        alert_color = {
            "none": "[green]", "watch": "[yellow]",
            "warning": "[orange]", "critical": "[red]",
        }.get(r.alert, "")
        print(
            f"{r.strategy_id:<20} {r.regime:<12} {r.live_sharpe:<11.2f} "
            f"{r.expected_sharpe:<11.2f} {alert_color}{r.alert.upper():<8}[/] {r.reason}"
        )
    criticals = [r for r in results if r.alert == "critical"]
    if criticals:
        print(f"\n[red]CRITICAL: {len(criticals)} strategy-regime pair(s) underperforming.[/red]")
    elif results:
        print(f"\n[dim]No critical alerts.[/dim]")
    if report:
        path = Path("feedback_report.md")
        path.write_text("\n".join(f"- {r.strategy_id} / {r.regime}: {r.alert}" for r in results))
        print(f"[green]Report written to {path}[/green]")


# ── Phase 3 Commands ──────────────────────────────────────────────────────────

@app.command("discover-alpha")
def discover_alpha(
    strategy: str = typer.Option("simple_momentum", "--strategy", "-s", help="Base strategy to improve"),
    limit: int = typer.Option(3, "--limit", "-n", help="Max hypotheses"),
):
    """LLM-driven alpha hypothesis discovery."""
    from trading_lab.alpha.discovery import AlphaDiscoveryEngine
    engine = AlphaDiscoveryEngine()
    hypotheses = engine.discover(strategy_id=strategy, limit=limit)
    if not hypotheses:
        print("[yellow]No hypotheses discovered. Check LLM provider config.[/yellow]")
        return
    print(f"\n[bold]Alpha Hypotheses for {strategy}[/bold]\n")
    for i, h in enumerate(hypotheses, 1):
        print(f"{i}. [cyan]{h.feature_name}[/cyan] (confidence: {h.confidence:.0%})")
        print(f"   Regime: {h.target_regime}")
        print(f"   Formula: {h.suggested_formula}")
        print(f"   {h.description}")
        print()


@app.command("engineer-features")
def engineer_features(
    tickers: str = typer.Option("SPY", "--tickers", "-t", help="Comma-separated tickers"),
    days: int = typer.Option(30, "--days", "-d", help="Lookback days"),
    custom: str = typer.Option("", "--custom", "-c", help="Custom formula: name=formula"),
):
    """Compute engineered features for tickers."""
    from trading_lab.alpha.features import FeatureEngine
    import yfinance as yf
    import numpy as np

    tlist = [t.strip() for t in tickers.split(",")]
    custom_features = {}
    if custom:
        for pair in custom.split(";"):
            if "=" in pair:
                name, formula = pair.split("=", 1)
                custom_features[name.strip()] = formula.strip()

    engine = FeatureEngine(custom_features=custom_features)
    print(f"\n[bold]Feature Engineering[/bold]\n")
    for ticker in tlist:
        hist = yf.Ticker(ticker).history(period=f"{days + 20}d")
        if len(hist) < days:
            print(f"[red]Insufficient data for {ticker}[/red]")
            continue
        fs = engine.compute(
            ticker=ticker,
            open_=hist["Open"].values,
            high=hist["High"].values,
            low=hist["Low"].values,
            close=hist["Close"].values,
            volume=hist["Volume"].values,
        )
        print(f"[green]{ticker}[/green]: {len(fs.names())} features")
        for name in fs.names()[:5]:
            val = fs.latest(name)
            print(f"  {name}: {val:.4f}")
        if len(fs.names()) > 5:
            print(f"  ... and {len(fs.names()) - 5} more")


@app.command("neural-signal")
def neural_signal(
    ticker: str = typer.Option("SPY", "--ticker", "-t"),
    epochs: int = typer.Option(500, "--epochs", "-e"),
):
    """Train neural signal model on features."""
    from trading_lab.alpha.features import FeatureEngine
    from trading_lab.alpha.neural_signal import NeuralSignalModel, generate_labels_from_returns
    import yfinance as yf
    import numpy as np

    print(f"\n[bold]Neural Signal: {ticker}[/bold]\n")
    hist = yf.Ticker(ticker).history(period="60d")
    if len(hist) < 30:
        print("[red]Insufficient data[/red]")
        return

    engine = FeatureEngine()
    fs = engine.compute(
        ticker=ticker,
        open_=hist["Open"].values,
        high=hist["High"].values,
        low=hist["Low"].values,
        close=hist["Close"].values,
        volume=hist["Volume"].values,
    )

    returns = np.diff(hist["Close"].values) / hist["Close"].values[:-1]
    labels = generate_labels_from_returns(returns)

    # Create rolling feature sets
    feature_sets = []
    for i in range(len(hist) - 1):
        from trading_lab.alpha.features import FeatureSet
        fset = FeatureSet(
            ticker=ticker,
            features={k: np.array([v[i] if i < len(v) else v[-1]]) for k, v in fs.features.items()},
        )
        feature_sets.append(fset)

    model = NeuralSignalModel()
    model.EPOCHS = epochs
    metrics = model.train(feature_sets, labels[: len(feature_sets)])
    print(f"Training: loss={metrics['loss']:.4f}, accuracy={metrics['accuracy']:.1%}")
    print(f"Parameters: {model.parameter_count()}")

    # Predict latest
    latest = feature_sets[-1]
    signal = model.predict(latest)
    print(f"\nLatest signal: {signal.action} (confidence: {signal.confidence:.1%})")
    print(f"Probabilities: BUY={signal.probabilities['BUY']:.1%}, HOLD={signal.probabilities['HOLD']:.1%}, SELL={signal.probabilities['SELL']:.1%}")


@app.command("run-simulation")
def run_simulation(
    tickers: str = typer.Option("SPY", "--tickers", "-t"),
    days: int = typer.Option(30, "--days", "-d"),
    agents: str = typer.Option("", "--agents", "-a", help="Comma-separated strategy IDs (default: all registered)"),
    no_neural: bool = typer.Option(False, "--no-neural", help="Skip neural agent"),
):
    """Run multi-agent simulation on historical data."""
    from trading_lab.alpha.simulation import MultiAgentSimulation
    from trading_lab.alpha.analytics import SimulationAnalytics
    from datetime import datetime, timezone

    tlist = [t.strip() for t in tickers.split(",")]
    agent_list = [a.strip() for a in agents.split(",")] if agents else None

    sim = MultiAgentSimulation(
        lookback_days=days,
        tickers=tlist,
        agents=agent_list,
        include_neural=not no_neural,
    )
    results = sim.run()

    sim_id = f"sim_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    analytics = SimulationAnalytics()
    report = analytics.analyze(
        results=results,
        sim_id=sim_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        tickers=tlist,
        lookback_days=days,
    )

    print(f"\n[bold]Simulation: {sim_id}[/bold]\n")
    print(f"Tickers: {', '.join(tlist)}")
    print(f"Days: {days}")
    print(f"Agents: {', '.join(report.agents)}")
    print(f"\n[bold]Leaderboard[/bold]\n")
    print(f"{'Rank':<6} {'Agent':<20} {'Equity':<10} {'Sharpe':<8} {'Alpha':<8}")
    print("-" * 60)
    for e in report.leaderboard:
        neural_tag = " [neural]" if e.is_neural else ""
        print(f"{e.rank:<6} {e.agent_id + neural_tag:<20} {e.final_equity:<10.4f} {e.sharpe:<8.2f} {e.alpha_vs_baseline:+.1%}")
    print(f"\n[bold]Recommendation:[/bold] {report.recommendation}")


@app.command("sim-leaderboard")
def sim_leaderboard(
    sim_id: str = typer.Option("", "--sim-id", "-s", help="Simulation ID (default: latest)"),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """Show simulation leaderboard from database."""
    from trading_lab.alpha.analytics import SimulationAnalytics
    analytics = SimulationAnalytics()
    if sim_id:
        report = analytics.get_report(sim_id)
        if report:
            print(analytics.format_report(report))
        else:
            print(f"[red]Simulation {sim_id} not found[/red]")
    else:
        sims = analytics.list_sims(limit=limit)
        if not sims:
            print("[dim]No simulations found.[/dim]")
            return
        print(f"\n[bold]Recent Simulations[/bold]\n")
        print(f"{'Sim ID':<25} {'Time':<20} {'Best Agent':<20} {'Sharpe':<8} {'Alpha'}")
        print("-" * 90)
        for s in sims:
            print(f"{s['sim_id']:<25} {s['timestamp'][:19]:<20} {s['best_agent']:<20} {s['best_sharpe']:<8.2f} {s['alpha_pct']:+.1%}")


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    app()
