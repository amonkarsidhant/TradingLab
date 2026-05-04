"""
Bull Discord Bot — remote interface to Sid Trading Lab with proper slash commands.

Registers Discord Application Commands (slash commands) so they auto-complete
in the Discord UI. All commands are DEMO-only.

Commands:
  /scan       — Scan watchlist for trading signals
  /risk       — Portfolio risk assessment (Munger reflection)
  /journal    — Daily trading journal report
  /weekly     — Weekly report
  /summary    — Account summary from T212
  /positions  — Open positions
  /buy        — Preview & confirm buy order
  /sell       — Preview & confirm sell order
  /dashboard  — Generate HTML dashboard
  /status     — Bot health check
  /reflect    — Munger reflection engine
  /help       — Show command list
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

# Load .env BEFORE importing project modules
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    load_dotenv(env_path)

from trading_lab.agentic.portfolio import PortfolioManager
from trading_lab.agentic.reflection import MungerReflectionEngine
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.config import get_settings
from trading_lab.data.market_data import make_provider
from trading_lab.logger import SnapshotLogger
from trading_lab.reports.dashboard import DashboardGenerator
from trading_lab.strategies import get_strategy
from trading_lab.watcher.kill_switch import KillSwitch

# ── Constants ─────────────────────────────────────────────────────────────────

COMMANDS = {
    "scan": "🔍 Scan watchlist for trading signals",
    "risk": "🧠 Portfolio risk assessment (Munger reflection)",
    "journal": "📓 Daily trading journal report",
    "weekly": "📅 Weekly report",
    "summary": "📊 Account summary from T212",
    "positions": "📋 Open positions",
    "buy": "📥 Preview & confirm buy order",
    "sell": "📤 Preview & confirm sell order",
    "dashboard": "📈 Generate HTML dashboard",
    "status": "🟢 Bot health check",
    "reflect": "🧠 Munger reflection engine",
    "help": "❓ Show command list",
}

_WATCHLIST = [
    "AAPL_US_EQ", "MSFT_US_EQ", "NVDA_US_EQ", "GOOGL_US_EQ",
    "AMZN_US_EQ", "META_US_EQ", "TSLA_US_EQ", "AMD_US_EQ",
    "CRM_US_EQ", "KO_US_EQ", "JNJ_US_EQ", "V_US_EQ",
]

_INTENTS = discord.Intents.default()
_INTENTS.message_content = True


# ── Helper functions ───────────────────────────────────────────────────────────

async def _chunk(text: str, size: int = 1900) -> list[str]:
    """Split text into Discord-safe chunks."""
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) > size:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


def _esc(text: str) -> str:
    """Escape Discord markdown."""
    return str(text).replace("`", "\\`").replace("*", "\\*").replace("_", "\\_")


async def _run_cli(interaction: discord.Interaction, *args: str) -> str:
    """Run a CLI command and capture stdout."""
    import subprocess

    project_root = Path(__file__).resolve().parents[2]
    cmd = [str(project_root / ".venv" / "bin" / "python"), "-m", "trading_lab.cli", *args]
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    if proc.returncode != 0:
        return f"Error (code {proc.returncode}):\n{proc.stderr or proc.stdout}"
    return proc.stdout


# ── Bot setup ─────────────────────────────────────────────────────────────────

class TradingBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=_INTENTS,
            help_command=None,
        )

    async def on_ready(self):
        print(f"🤖 Bull Discord Bot ready as {self.user}")
        try:
            synced = await self.tree.sync()
            print(f"   Synced {len(synced)} slash commands")
        except Exception as exc:
            print(f"   ❌ Failed to sync commands: {exc}")

        # Set activity
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="📈 Sid Trading Lab — DEMO",
            )
        )

    async def setup_hook(self) -> None:
        # Register all slash commands
        await self.tree.sync()


bot = TradingBot()


# ── Slash Commands ────────────────────────────────────────────────────────────

@bot.tree.command(name="scan", description=COMMANDS["scan"])
async def scan_cmd(interaction: discord.Interaction):
    """Run a scan across the watchlist."""
    await interaction.response.defer(thinking=True)

    settings = get_settings()
    pm = PortfolioManager(settings)
    results: list[str] = []

    try:
        state = pm.state()
        open_tickers = pm.get_open_tickers(state)

        for ticker in _WATCHLIST:
            strategy = get_strategy("simple_momentum", lookback=5)
            provider = make_provider(
                source="chained",
                ticker=ticker,
                cache_db=settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
            )
            prices = provider.get_prices(ticker=ticker, lookback=5)
            signal = strategy.generate_signal(ticker=ticker, prices=prices)

            status = "📌 OPEN" if ticker in open_tickers else ""
            if signal.action == "BUY":
                results.append(f"🟢 **{ticker}** — BUY (conf={signal.confidence:.2f}) {status}\n   {signal.reason}")
            elif signal.action == "SELL":
                results.append(f"🔴 **{ticker}** — SELL (conf={signal.confidence:.2f}) {status}\n   {signal.reason}")
            else:
                results.append(f"⚪ **{ticker}** — HOLD {status}")

        text = f"**🔍 Scan Results ({len(results)} tickers)**\n\n"
        text += "\n\n".join(results)

        # Add snapshot
        snap = await _run_cli(interaction, "account-summary")
        text += f"\n\n**📊 Account Summary**\n```{snap[:800]}```"

    except Exception as exc:
        text = f"**❌ Scan Error**\n```{_esc(exc)}```"

    for chunk in await _chunk(text):
        await interaction.followup.send(chunk[:2000])


@bot.tree.command(name="risk", description=COMMANDS["risk"])
async def risk_cmd(interaction: discord.Interaction):
    """Run Munger reflection / risk assessment."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        engine = MungerReflectionEngine(settings)
        report = engine.reflect()
        text = engine.format_reflection(report)
    except Exception as exc:
        text = f"**❌ Reflection Error**\n```{_esc(exc)}```"

    for chunk in await _chunk(text):
        await interaction.followup.send(chunk[:2000])


@bot.tree.command(name="journal", description=COMMANDS["journal"])
async def journal_cmd(interaction: discord.Interaction):
    """Generate daily journal report."""
    await interaction.response.defer(thinking=True)

    try:
        result = await _run_cli(interaction, "daily-journal")
        text = f"**📓 Daily Journal**\n```\n{result}\n```"
    except Exception as exc:
        text = f"**❌ Error**\n```{_esc(exc)}```"

    for chunk in await _chunk(text):
        await interaction.followup.send(chunk[:2000])


@bot.tree.command(name="weekly", description=COMMANDS["weekly"])
async def weekly_cmd(interaction: discord.Interaction):
    """Generate weekly report."""
    await interaction.response.defer(thinking=True)

    try:
        result = await _run_cli(interaction, "weekly-report")
        text = f"**📅 Weekly Report**\n```\n{result}\n```"
    except Exception as exc:
        text = f"**❌ Error**\n```{_esc(exc)}```"

    # Append round-trip stats if any
    try:
        from trading_lab.round_trips import RoundTripTracker
        settings = get_settings()
        rt = RoundTripTracker(settings.db_path)
        stats = rt.get_sharpe_for()
        if stats.get("trips", 0) > 0:
            text += (
                f"\n\n📈 **Round Trips**  trips={stats['trips']}  |  "
                f"avg_pnl={stats.get('avg_pnl_pct', 'N/A')}%  |  "
                f"win_rate={stats.get('win_rate', 'N/A')}%  |  "
                f"sharpe={stats.get('sharpe', 'N/A')}"
            )
    except Exception:
        pass

    for chunk in await _chunk(text):
        await interaction.followup.send(chunk[:2000])


@bot.tree.command(name="summary", description=COMMANDS["summary"])
async def summary_cmd(interaction: discord.Interaction):
    """Get T212 account summary."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        pm = PortfolioManager(settings)
        state = pm.state()

        text = (
            f"**📊 Account Summary**\n\n"
            f"Cash: €{state.cash:,.2f}\n"
            f"Invested: €{state.invested_value:,.2f}\n"
            f"Total Value: €{state.total_value:,.2f}\n"
            f"Unrealized P&L: €{state.unrealized_pnl:,.2f}\n"
            f"Positions: {len(state.positions)} / {pm.MAX_POSITIONS}\n"
            f"Cash %: {(state.cash / max(state.total_value, 1) * 100):.1f}%"
        )
    except Exception as exc:
        text = f"**❌ Error**\n```{_esc(exc)}```"

    await interaction.followup.send(text[:2000])


@bot.tree.command(name="positions", description=COMMANDS["positions"])
async def positions_cmd(interaction: discord.Interaction):
    """List open positions."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        pm = PortfolioManager(settings)
        state = pm.state()

        if not state.positions:
            text = "**📋 Open Positions**\n\nNo open positions."
        else:
            lines = ["**📋 Open Positions**"]
            for p in state.positions:
                pnl_pct = ((p.current_price - p.avg_price) / max(p.avg_price, 1) * 100) if p.avg_price > 0 else 0
                lines.append(
                    f"\n**{_esc(p.ticker)}**\n"
                    f"  Qty: {p.quantity}\n"
                    f"  Avg: €{p.avg_price:.2f} | Current: €{p.current_price:.2f}\n"
                    f"  Value: €{p.current_value:,.2f}\n"
                    f"  P&L: €{p.unrealized_pnl:,.2f} ({pnl_pct:+.2f}%)\n"
                    f"  Stop (7%): €{(p.avg_price * 0.93):.2f}"
                )
            text = "\n".join(lines)
    except Exception as exc:
        text = f"**❌ Error**\n```{_esc(exc)}```"

    for chunk in await _chunk(text):
        await interaction.followup.send(chunk[:2000])


@bot.tree.command(name="buy", description="Preview and confirm a buy order")
@app_commands.describe(ticker="Ticker symbol (e.g. AAPL_US_EQ)", quantity="Number of shares")
async def buy_cmd(interaction: discord.Interaction, ticker: str, quantity: int):
    """Preview and confirm a buy order."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        pm = PortfolioManager(settings)
        state = pm.state()

        if not pm.can_add_position(state):
            await interaction.followup.send(
                "**❌ Cannot buy:** Position limit or cash reserve reached."
            )
            return

        client = Trading212Client(settings)
        current_price = client._get_current_price(ticker)

        if not current_price:
            await interaction.followup.send(
                f"**❌ Error:** Cannot find price for `{_esc(ticker)}`."
            )
            return

        cost = quantity * current_price
        target = pm.target_position_size(state)

        text = (
            f"**📥 Buy Preview**\n\n"
            f"Ticker: `{_esc(ticker)}`\n"
            f"Quantity: {quantity}\n"
            f"Price: €{current_price:.2f}\n"
            f"Estimated Cost: €{cost:,.2f}\n"
            f"Target Size: €{target:,.2f}\n"
            f"Cash After: €{state.cash - cost:,.2f}\n\n"
            f"✅ **Confirm with `/buy-confirm {ticker} {quantity}`**"
        )

    except Exception as exc:
        text = f"**❌ Error**\n```{_esc(exc)}```"

    await interaction.followup.send(text[:2000])


@bot.tree.command(name="sell", description="Preview and confirm a sell order")
@app_commands.describe(ticker="Ticker symbol (e.g. AAPL_US_EQ)", quantity="Number of shares")
async def sell_cmd(interaction: discord.Interaction, ticker: str, quantity: int):
    """Preview and confirm a sell order."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        pm = PortfolioManager(settings)
        state = pm.state()

        pos = next((p for p in state.positions if p.ticker == ticker), None)
        if not pos:
            await interaction.followup.send(
                f"**❌ Error:** No open position for `{_esc(ticker)}`."
            )
            return

        if quantity > pos.quantity:
            await interaction.followup.send(
                f"**❌ Error:** You only hold {pos.quantity} shares of `{_esc(ticker)}`."
            )
            return

        proceeds = quantity * pos.current_price

        text = (
            f"**📤 Sell Preview**\n\n"
            f"Ticker: `{_esc(ticker)}`\n"
            f"Quantity: {quantity} / {pos.quantity}\n"
            f"Price: €{pos.current_price:.2f}\n"
            f"Estimated Proceeds: €{proceeds:,.2f}\n"
            f"Unrealized P&L on lot: €{(pos.current_price - pos.avg_price) * quantity:,.2f}\n\n"
            f"✅ **Confirm with `/sell-confirm {ticker} {quantity}`**"
        )

    except Exception as exc:
        text = f"**❌ Error**\n```{_esc(exc)}```"

    await interaction.followup.send(text[:2000])


@bot.tree.command(name="buy-confirm", description="Confirm and execute a buy order")
@app_commands.describe(ticker="Ticker symbol (e.g. AAPL_US_EQ)", quantity="Number of shares")
async def buy_confirm_cmd(interaction: discord.Interaction, ticker: str, quantity: int):
    """Execute a confirmed buy order."""
    await interaction.response.defer(thinking=True)

    if not get_settings().can_place_orders:
        await interaction.followup.send("**❌ Error:** Order placement disabled in config.")
        return

    try:
        pm = PortfolioManager(get_settings())
        result = pm.place_order(ticker, quantity)
        await interaction.followup.send(
            f"**✅ Buy Executed**\n```json\n{json.dumps(result, indent=2, default=str)}\n```"
        )
    except Exception as exc:
        await interaction.followup.send(f"**❌ Buy Failed**\n```{_esc(exc)}```")


@bot.tree.command(name="sell-confirm", description="Confirm and execute a sell order")
@app_commands.describe(ticker="Ticker symbol (e.g. AAPL_US_EQ)", quantity="Number of shares")
async def sell_confirm_cmd(interaction: discord.Interaction, ticker: str, quantity: int):
    """Execute a confirmed sell order."""
    await interaction.response.defer(thinking=True)

    if not get_settings().can_place_orders:
        await interaction.followup.send("**❌ Error:** Order placement disabled in config.")
        return

    try:
        pm = PortfolioManager(get_settings())
        result = pm.place_order(ticker, -quantity)
        await interaction.followup.send(
            f"**✅ Sell Executed**\n```json\n{json.dumps(result, indent=2, default=str)}```"
        )
    except Exception as exc:
        await interaction.followup.send(f"**❌ Sell Failed**\n```{_esc(exc)}```")


@bot.tree.command(name="dashboard", description=COMMANDS["dashboard"])
async def dashboard_cmd(interaction: discord.Interaction):
    """Generate and send HTML dashboard."""
    await interaction.response.defer(thinking=True)

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            tmp_path = f.name

        settings = get_settings()
        db_path = settings.db_path
        gen = DashboardGenerator(db_path=db_path, cache_db_path=db_path.replace(".sqlite3", "_cache.sqlite3"))
        html = gen.generate(ticker="AAPL_US_EQ", data_source="chained")

        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(html)

        filename = f"dashboard_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.html"
        await interaction.followup.send(
            file=discord.File(tmp_path, filename=filename),
            content="**📈 Trading Lab Dashboard**",
        )

        os.unlink(tmp_path)

    except Exception as exc:
        await interaction.followup.send(f"**❌ Dashboard Error**\n```{_esc(exc)}```")


@bot.tree.command(name="status", description=COMMANDS["status"])
async def status_cmd(interaction: discord.Interaction):
    """Bot health check."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        pm = PortfolioManager(settings)
        state = pm.state()

        text = (
            f"**🟢 Bot Status: OK**\n\n"
            f"Environment: `demo`\n"
            f"Orders enabled: `true`\n"
            f"Open positions: {len(state.positions)} / {pm.MAX_POSITIONS}\n"
            f"Cash: €{state.cash:,.2f}\n"
            f"Total Value: €{state.total_value:,.2f}\n"
            f"Unrealized P&L: €{state.unrealized_pnl:,.2f}"
        )
    except Exception as exc:
        text = f"**🟡 Bot Status: Degraded**\n```T212 API: {_esc(exc)}```"

    await interaction.followup.send(text[:2000])


@bot.tree.command(name="reflect", description=COMMANDS["reflect"])
async def reflect_cmd(interaction: discord.Interaction):
    """Run Munger reflection engine."""
    await interaction.response.defer(thinking=True)

    try:
        settings = get_settings()
        engine = MungerReflectionEngine(settings)
        report = engine.reflect()
        text = engine.format_reflection(report)
    except Exception as exc:
        text = f"**❌ Reflection Error**\n```{_esc(exc)}```"

    for chunk in await _chunk(text):
        await interaction.followup.send(chunk[:2000])


@bot.tree.command(name="help", description=COMMANDS["help"])
async def help_cmd(interaction: discord.Interaction):
    """Show available commands."""
    lines = ["**🐂 Bull — Sid Trading Lab Commands**\n"]
    for name, desc in COMMANDS.items():
        lines.append(f"`/{name}` — {desc}")
    lines.append("\n*All orders go to DEMO environment. No real money.*")
    text = "\n".join(lines)
    await interaction.response.send_message(text[:2000])


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN not set.\n"
            "1. Go to https://discord.com/developers/applications\n"
            "2. Create a bot and copy the token\n"
            "3. Set DISCORD_BOT_TOKEN in your .env file"
        )

    print(f"🚀 Starting Bull Discord Bot...")
    print(f"   Token: {token[:10]}...")
    bot.run(token)


if __name__ == "__main__":
    main()
