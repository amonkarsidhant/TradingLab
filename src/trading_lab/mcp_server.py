"""
MCP server for Sid Trading Lab.

Gives Claude Desktop tools to interact with the trading lab:
- Read T212 demo account data
- Run strategies and backtests
- Place demo orders (with explicit confirmation)
- Review signal history

Safety: all orders require confirm=true. Demo environment only.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.config import get_settings
from trading_lab.data.market_data import make_provider
from trading_lab.reports.daily_journal import DailyJournal
from trading_lab.reports.strategy_comparison import StrategyComparison
from trading_lab.strategies import get_strategy, list_strategies

app = Server("sid-trading-lab")


def _client() -> Trading212Client:
    return Trading212Client(get_settings())


# ── Tools ──────────────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_account_summary",
        description="Get your Trading 212 demo account summary (cash, equity, positions value).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_positions",
        description="List all open positions in your Trading 212 demo account.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="run_strategy",
        description="Run a strategy on a ticker and get the latest signal (BUY/SELL/HOLD).",
        inputSchema={
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "Strategy name: simple_momentum, ma_crossover, mean_reversion"},
                "ticker": {"type": "string", "description": "Ticker symbol, e.g. AAPL_US_EQ"},
                "data_source": {"type": "string", "enum": ["static", "csv", "yfinance", "chained"], "default": "yfinance"},
                "lookback": {"type": "integer", "description": "Lookback periods for price data", "default": 30},
            },
            "required": ["strategy", "ticker"],
        },
    ),
    Tool(
        name="run_backtest",
        description="Run a walk-forward backtest for a strategy on a ticker and return performance metrics.",
        inputSchema={
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "Strategy name"},
                "ticker": {"type": "string", "description": "Ticker symbol"},
                "data_source": {"type": "string", "enum": ["static", "csv", "yfinance", "chained"], "default": "yfinance"},
                "capital": {"type": "number", "description": "Initial capital", "default": 10000},
            },
            "required": ["strategy", "ticker"],
        },
    ),
    Tool(
        name="place_demo_order",
        description="Place a market order on the Trading 212 DEMO environment. Requires explicit confirmation.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol to trade"},
                "quantity": {"type": "number", "description": "Number of shares (positive=buy, negative=sell)"},
                "confirm": {"type": "boolean", "description": "Must be true to actually place the order"},
            },
            "required": ["ticker", "quantity", "confirm"],
        },
    ),
    Tool(
        name="get_recent_signals",
        description="Get the most recent strategy signals from the local SQLite journal.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of signals to return", "default": 10},
            },
        },
    ),
    Tool(
        name="get_daily_journal",
        description="Generate a daily journal report summarising today's signals and snapshots.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date YYYY-MM-DD, defaults to today"},
            },
        },
    ),
    Tool(
        name="compare_strategies",
        description="Run backtests for ALL registered strategies on a ticker and compare side-by-side.",
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol"},
                "data_source": {"type": "string", "enum": ["static", "csv", "yfinance", "chained"], "default": "yfinance"},
                "capital": {"type": "number", "description": "Initial capital", "default": 10000},
            },
            "required": ["ticker"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    settings = get_settings()

    # ── Account Summary ─────────────────────────────────────────────────────
    if name == "get_account_summary":
        client = _client()
        data = client.account_summary()
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    # ── Positions ─────────────────────────────────────────────────────────────
    if name == "get_positions":
        client = _client()
        data = client.positions()
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    # ── Run Strategy ──────────────────────────────────────────────────────────
    if name == "run_strategy":
        strat_name = arguments["strategy"]
        ticker = arguments["ticker"]
        source = arguments.get("data_source", "yfinance")
        lookback = arguments.get("lookback", 30)

        kwargs = {}
        if strat_name == "simple_momentum":
            kwargs = {"lookback": 5}
        elif strat_name == "ma_crossover":
            kwargs = {"fast": 10, "slow": 30}
        elif strat_name == "mean_reversion":
            kwargs = {"period": 14, "oversold": 30, "overbought": 70}

        strategy = get_strategy(strat_name, **kwargs)
        provider = make_provider(
            source=source,
            ticker=ticker,
            cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
        )
        prices = provider.get_prices(ticker=ticker, lookback=lookback)
        signal = strategy.generate_signal(ticker=ticker, prices=prices)

        result = {
            "strategy": signal.strategy,
            "ticker": signal.ticker,
            "action": signal.action.value,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "suggested_quantity": signal.suggested_quantity,
            "prices_available": len(prices),
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    # ── Run Backtest ────────────────────────────────────────────────────────
    if name == "run_backtest":
        strat_name = arguments["strategy"]
        ticker = arguments["ticker"]
        source = arguments.get("data_source", "yfinance")
        capital = arguments.get("capital", 10_000.0)

        kwargs = {}
        if strat_name == "simple_momentum":
            kwargs = {"lookback": 5}
        elif strat_name == "ma_crossover":
            kwargs = {"fast": 10, "slow": 30}
        elif strat_name == "mean_reversion":
            kwargs = {"period": 14, "oversold": 30, "overbought": 70}

        strategy = get_strategy(strat_name, **kwargs)
        provider = make_provider(
            source=source,
            ticker=ticker,
            cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
        )
        prices = provider.get_prices(ticker=ticker, lookback=252)

        engine = BacktestEngine(strategy, initial_capital=capital)
        result = engine.run(prices=prices, ticker=ticker)

        summary = {
            "strategy": strat_name,
            "ticker": ticker,
            "initial_capital": capital,
            "final_equity": result.final_equity,
            "total_return_pct": result.metrics.get("total_return_pct"),
            "cagr_pct": result.metrics.get("cagr_pct"),
            "sharpe_ratio": result.metrics.get("sharpe_ratio"),
            "max_drawdown_pct": result.metrics.get("max_drawdown_pct"),
            "win_rate": result.metrics.get("win_rate"),
            "profit_factor": result.metrics.get("profit_factor"),
            "total_trades": result.metrics.get("total_trades"),
            "signals_generated": len(result.signals),
        }
        return [TextContent(type="text", text=json.dumps(summary, indent=2, default=str))]

    # ── Place Demo Order ────────────────────────────────────────────────────
    if name == "place_demo_order":
        ticker = arguments["ticker"]
        quantity = arguments["quantity"]
        confirm = arguments.get("confirm", False)

        if not confirm:
            return [TextContent(
                type="text",
                text=(
                    "SAFETY: Order NOT placed. You must set confirm=true to place a demo order.\n"
                    f"Would place: {quantity} shares of {ticker} on DEMO environment.\n"
                    "This is a deliberate safety step — AI suggests, human confirms."
                ),
            )]

        if not settings.can_place_orders:
            return [TextContent(
                type="text",
                text=(
                    "ERROR: Order placement is disabled.\n"
                    "Set ORDER_PLACEMENT_ENABLED=true and DEMO_ORDER_CONFIRM=I_ACCEPT_DEMO_ORDER_TEST in .env"
                ),
            )]

        client = _client()
        result = client.market_order(ticker=ticker, quantity=quantity, dry_run=False)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    # ── Recent Signals ────────────────────────────────────────────────────────
    if name == "get_recent_signals":
        limit = arguments.get("limit", 10)
        try:
            with sqlite3.connect(settings.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                data = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            data = []
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    # ── Daily Journal ─────────────────────────────────────────────────────────
    if name == "get_daily_journal":
        date = arguments.get("date", "")
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        journal = DailyJournal(settings.db_path)
        report = journal.generate(date)
        return [TextContent(type="text", text=report)]

    # ── Compare Strategies ────────────────────────────────────────────────────
    if name == "compare_strategies":
        ticker = arguments["ticker"]
        source = arguments.get("data_source", "yfinance")
        capital = arguments.get("capital", 10_000.0)

        comparison = StrategyComparison(
            db_path=settings.db_path,
            cache_db_path=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
        )
        report = comparison.compare(
            ticker=ticker,
            data_source=source,
            initial_capital=capital,
        )
        return [TextContent(type="text", text=report)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
