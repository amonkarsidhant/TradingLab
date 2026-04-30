"""
Bull Telegram Bot — remote interface to the trading lab.

Commands:
  /start      Welcome message
  /summary    Account summary from T212
  /positions  Open positions
  /scan       Run Jarvis autonomous scan
  /buy        Preview and confirm a buy order
  /sell       Preview and confirm a sell order
  /journal    Daily journal report
  /weekly     Weekly report
  /dashboard  Generate HTML dashboard (sent as file)
  /status     Bot health check
  /help       Show command list

Safety:
  - All orders go through PortfolioManager (max 10 positions, 20% per pos, 10% cash)
  - /buy and /sell require inline-button confirmation
  - Demo environment only
  - All activity logged to SQLite
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from trading_lab.agentic.portfolio import PortfolioManager
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.config import get_settings
from trading_lab.logger import SnapshotLogger

# -- Constants -----------------------------------------------------------------

PREVIEW = 1

_MAX_MSG_LEN = 4000

_COMMANDS = [
    ("/start", "Welcome and bot status"),
    ("/summary", "T212 account summary"),
    ("/positions", "Open positions"),
    ("/scan", "Run Jarvis autonomous scan"),
    ("/buy TICKER QTY", "Preview and confirm a buy"),
    ("/sell TICKER QTY", "Preview and confirm a sell"),
    ("/journal", "Daily journal report"),
    ("/weekly", "Weekly report"),
    ("/dashboard", "Generate HTML dashboard"),
    ("/status", "Bot health check"),
    ("/help", "This message"),
]


# -- Helpers -------------------------------------------------------------------

def _chunk(text: str, size: int = _MAX_MSG_LEN) -> list[str]:
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
    return html.escape(str(text))


def _run_cli(*args: str, cwd: str | None = None) -> str:
    """Run a CLI command and return stdout."""
    cmd = ["python", "-m", "trading_lab.cli", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return f"Error (code {result.returncode}):\n{result.stderr or result.stdout}"
    return result.stdout


# -- Handlers ------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>🐂 Bull — Sid Trading Lab Bot</b>\n\n"
        "Demo-only. No real money. AI suggests, you decide.\n\n"
        f"Timestamp: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>\n"
        "Use /help for commands."
    )
    await update.message.reply_html(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["<b>Available Commands</b>"]
    for cmd, desc in _COMMANDS:
        lines.append(f"<code>{cmd}</code> — {desc}")
    lines.append("\n<i>All orders require confirmation. Demo only.</i>")
    await update.message.reply_html("\n".join(lines))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    pm = PortfolioManager(settings)
    try:
        state = pm.state()
        text = (
            "<b>🟢 Bot Status: OK</b>\n\n"
            f"Environment: <code>{_esc(settings.t212_env)}</code>\n"
            f"Orders enabled: <code>{settings.can_place_orders}</code>\n"
            f"Open positions: {len(state.positions)} / {pm.MAX_POSITIONS}\n"
            f"Cash: €{state.cash:,.2f}\n"
            f"Total Value: €{state.total_value:,.2f}\n"
        )
    except Exception as exc:
        text = f"<b>🟡 Bot Status: Degraded</b>\n\nT212 API: <code>{_esc(exc)}</code>"
    await update.message.reply_html(text)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    pm = PortfolioManager(settings)
    try:
        state = pm.state()
        text = (
            "<b>📊 Account Summary</b>\n\n"
            f"Cash: €{state.cash:,.2f}\n"
            f"Invested: €{state.invested_value:,.2f}\n"
            f"Total Value: €{state.total_value:,.2f}\n"
            f"Unrealized P&L: €{state.unrealized_pnl:,.2f}\n"
            f"Positions: {len(state.positions)}\n"
        )
    except Exception as exc:
        text = f"<b>Error</b>\n<pre>{_esc(exc)}</pre>"
    await update.message.reply_html(text)


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    pm = PortfolioManager(settings)
    try:
        state = pm.state()
        if not state.positions:
            text = "<b>📋 Positions</b>\n\nNo open positions."
        else:
            lines = ["<b>📋 Open Positions</b>\n"]
            for p in state.positions:
                lines.append(
                    f"\n<b>{_esc(p.ticker)}</b>\n"
                    f"  Qty: {p.quantity}\n"
                    f"  Avg: €{p.avg_price:.2f}\n"
                    f"  Current: €{p.current_price:.2f}\n"
                    f"  Value: €{p.current_value:,.2f}\n"
                    f"  P&L: €{p.unrealized_pnl:,.2f}"
                )
            text = "\n".join(lines)
    except Exception as exc:
        text = f"<b>Error</b>\n<pre>{_esc(exc)}</pre>"
    for chunk in _chunk(text):
        await update.message.reply_html(chunk)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>🔍 Running Jarvis scan...</b>\n<i>This may take 60-90s due to API rate limits.</i>")

    project_root = Path(__file__).resolve().parents[3]
    result = await asyncio.to_thread(_run_cli, "account-summary", "--save-snapshot", cwd=str(project_root))
    for chunk in _chunk(f"<b>Account Summary</b>\n<pre>{_esc(result)}</pre>"):
        await update.message.reply_html(chunk)

    result = await asyncio.to_thread(
        subprocess.run,
        ["python", "scripts/jarvis.py"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0:
        text = f"<b>❌ Scan Error</b>\n<pre>{_esc(stderr or stdout)}</pre>"
    else:
        text = f"<b>🔍 Jarvis Scan Complete</b>\n<pre>{_esc(stdout[-_MAX_MSG_LEN:])}</pre>"
    for chunk in _chunk(text):
        await update.message.reply_html(chunk)


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    args = context.args
    if len(args) != 2:
        await update.message.reply_html("Usage: <code>/buy TICKER QTY</code>\nExample: <code>/buy AAPL_US_EQ 1</code>")
        return ConversationHandler.END

    ticker, qty_str = args[0], args[1]
    try:
        quantity = int(qty_str)
    except ValueError:
        await update.message.reply_html("Quantity must be an integer.")
        return ConversationHandler.END

    settings = get_settings()
    pm = PortfolioManager(settings)

    try:
        state = pm.state()
        if not pm.can_add_position(state):
            await update.message.reply_html("<b>Cannot buy:</b> position limit or cash reserve reached.")
            return ConversationHandler.END

        # Get current price via T212 positions, then yfinance fallback for new tickers.
        client = Trading212Client(settings)
        current_price = client._get_current_price(ticker)

        if not current_price:
            await update.message.reply_html(
                f"Cannot find current price for <code>{_esc(ticker)}</code> "
                f"(not held and no yfinance quote)."
            )
            return ConversationHandler.END

        cost = quantity * current_price
        target = pm.target_position_size(state)

        text = (
            f"<b>📥 Buy Preview</b>\n\n"
            f"Ticker: <code>{_esc(ticker)}</code>\n"
            f"Quantity: {quantity}\n"
            f"Price: €{current_price:.2f}\n"
            f"Estimated Cost: €{cost:,.2f}\n"
            f"Target Size: €{target:,.2f}\n"
            f"Cash After: €{state.cash - cost:,.2f}\n\n"
            f"Confirm this order?"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm Buy", callback_data=f"buy:{ticker}:{quantity}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return PREVIEW
    except Exception as exc:
        await update.message.reply_html(f"<b>Error</b>\n<pre>{_esc(exc)}</pre>")
        return ConversationHandler.END


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    args = context.args
    if len(args) != 2:
        await update.message.reply_html("Usage: <code>/sell TICKER QTY</code>\nExample: <code>/sell AAPL_US_EQ 1</code>")
        return ConversationHandler.END

    ticker, qty_str = args[0], args[1]
    try:
        quantity = int(qty_str)
    except ValueError:
        await update.message.reply_html("Quantity must be an integer.")
        return ConversationHandler.END

    settings = get_settings()
    pm = PortfolioManager(settings)

    try:
        state = pm.state()
        pos = next((p for p in state.positions if p.ticker == ticker), None)
        if not pos:
            await update.message.reply_html(f"No open position for <code>{_esc(ticker)}</code>.")
            return ConversationHandler.END

        if quantity > pos.quantity:
            await update.message.reply_html(f"You only hold {pos.quantity} shares of {_esc(ticker)}.")
            return ConversationHandler.END

        proceeds = quantity * pos.current_price

        text = (
            f"<b>📤 Sell Preview</b>\n\n"
            f"Ticker: <code>{_esc(ticker)}</code>\n"
            f"Quantity: {quantity} / {pos.quantity}\n"
            f"Price: €{pos.current_price:.2f}\n"
            f"Estimated Proceeds: €{proceeds:,.2f}\n"
            f"Unrealized P&L on lot: €{(pos.current_price - pos.avg_price) * quantity:,.2f}\n\n"
            f"Confirm this order?"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm Sell", callback_data=f"sell:{ticker}:{quantity}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return PREVIEW
    except Exception as exc:
        await update.message.reply_html(f"<b>Error</b>\n<pre>{_esc(exc)}</pre>")
        return ConversationHandler.END


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("❌ Order cancelled.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    if data.startswith("buy:"):
        _, ticker, qty_str = data.split(":")
        quantity = int(qty_str)
        settings = get_settings()
        pm = PortfolioManager(settings)
        try:
            result = pm.place_order(ticker, quantity)
            await query.edit_message_text(
                f"<b>✅ Buy Executed</b>\n<pre>{_esc(json.dumps(result, indent=2, default=str))}</pre>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            await query.edit_message_text(
                f"<b>❌ Buy Failed</b>\n<pre>{_esc(exc)}</pre>",
                parse_mode=ParseMode.HTML,
            )
        return ConversationHandler.END

    if data.startswith("sell:"):
        _, ticker, qty_str = data.split(":")
        quantity = int(qty_str)
        settings = get_settings()
        pm = PortfolioManager(settings)
        try:
            result = pm.place_order(ticker, -quantity)
            await query.edit_message_text(
                f"<b>✅ Sell Executed</b>\n<pre>{_esc(json.dumps(result, indent=2, default=str))}</pre>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            await query.edit_message_text(
                f"<b>❌ Sell Failed</b>\n<pre>{_esc(exc)}</pre>",
                parse_mode=ParseMode.HTML,
            )
        return ConversationHandler.END

    await query.edit_message_text("Unknown action.")
    return ConversationHandler.END


async def journal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>📓 Generating daily journal...</b>")
    result = await asyncio.to_thread(_run_cli, "daily-journal")
    for chunk in _chunk(f"<b>Daily Journal</b>\n<pre>{_esc(result)}</pre>"):
        await update.message.reply_html(chunk)


async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>📅 Generating weekly report...</b>")
    result = await asyncio.to_thread(_run_cli, "weekly-report", "--date", "")
    for chunk in _chunk(f"<b>Weekly Report</b>\n<pre>{_esc(result)}</pre>"):
        await update.message.reply_html(chunk)


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>📈 Generating dashboard...</b>")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        tmp_path = f.name
    result = await asyncio.to_thread(_run_cli, "dashboard", "--data-source", "static", "--output", tmp_path)
    if "written to" in result.lower() or Path(tmp_path).exists():
        await update.message.reply_document(
            document=open(tmp_path, "rb"),
            filename=f"dashboard_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.html",
            caption="Trading Lab Dashboard",
        )
        os.unlink(tmp_path)
    else:
        await update.message.reply_html(f"<b>Dashboard Error</b>\n<pre>{_esc(result)}</pre>")


# -- Entry point ---------------------------------------------------------------

def create_application(token: str) -> Application:
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("journal", journal_command))
    app.add_handler(CommandHandler("weekly", weekly_command))
    app.add_handler(CommandHandler("dashboard", dashboard_command))

    order_conv = ConversationHandler(
        entry_points=[
            CommandHandler("buy", buy_command),
            CommandHandler("sell", sell_command),
        ],
        states={
            PREVIEW: [CallbackQueryHandler(confirm_callback)],
        },
        fallbacks=[CallbackQueryHandler(confirm_callback)],
    )
    app.add_handler(order_conv)

    return app


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set.\n"
            "1. Talk to @BotFather on Telegram to create a bot.\n"
            "2. Copy the token into .env as TELEGRAM_BOT_TOKEN=<token>"
        )

    app = create_application(token)
    print(f"Bull Telegram Bot started at {datetime.now(timezone.utc).isoformat()} UTC")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
