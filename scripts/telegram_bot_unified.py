#!/usr/bin/env python3
"""
Sid Trading Lab — Unified Telegram Bot
═══════════════════════════════════════════
Merged: interactive trading bot + scheduled routine runner.

Features:
• 5 scheduled trading routines (pre-market, open, midday, close, weekly)
• Full interactive command set (status, positions, buy/sell, journal, etc.)
• Inline-button confirmations for orders (bypassed when AUTO_APPROVE=true)
• go-trader patterns: semaphore (max 4), timeout kills, failure throttle
• Single polling loop — no update conflicts
"""

from __future__ import annotations

import asyncio
import html
import json
import logging.handlers
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, time
from pathlib import Path
from typing import Any

# Replaced with PTB JobQueue
# Replaced with PTB JobQueue run_daily
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

# -- Project paths --
PROJECT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJECT_DIR / ".venv/bin/python3"
LOGS_DIR = PROJECT_DIR / "logs"

# ── Load .env ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / ".env")

# ── Import trading lab modules ────────────────────────────────────────────────
sys.path.insert(0, str(PROJECT_DIR / "src"))
from trading_lab.agentic.portfolio import PortfolioManager
from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.config import get_settings
from trading_lab.logger import SnapshotLogger
from trading_lab.watcher.kill_switch import KillSwitch
from trading_lab.watcher.loop import PositionWatcher

AUTO_APPROVE = os.getenv("AUTO_APPROVE", "false").lower() in ("true", "1", "yes")

# ── Config ────────────────────────────────────────────────────────────────────
MAX_LOG_LINES = 50
_MAX_MSG_LEN = 4000
PREVIEW = 1
PYTHON_SEMAPHORE = asyncio.Semaphore(4)
SCRIPT_TIMEOUT = 120  # seconds

# Scheduled jobs (UTC)
JOBS = [
    {
        "id": "autonomous_cycle",
        "cmd": [str(VENV_PYTHON), "-m", "trading_lab.cli", "autonomous-cycle"],
        "schedule": {"hour": "*/1"},  # Every hour
        "emoji": "🤖",
        "label": "Autonomous Cycle",
    },
    {
        "id": "premarket",
        "cmd": [str(VENV_PYTHON), "-m", "trading_lab.cli", "scan-rank"],
        "schedule": {"hour": 6, "minute": 0},
        "emoji": "🌅",
        "label": "Pre-market Scan",
    },
    {
        "id": "marketopen",
        "cmd": [str(VENV_PYTHON), "-m", "trading_lab.cli", "scan-rank"],
        "schedule": {"hour": 9, "minute": 30},
        "emoji": "🔔",
        "label": "Market Open",
    },
    {
        "id": "midday",
        "cmd": [str(VENV_PYTHON), "-m", "trading_lab.cli", "account-summary"],
        "schedule": {"hour": 12, "minute": 0},
        "emoji": "☀️",
        "label": "Midday Review",
    },
    {
        "id": "marketclose",
        "cmd": [str(VENV_PYTHON), "-m", "trading_lab.cli", "daily-journal"],
        "schedule": {"hour": 16, "minute": 0},
        "emoji": "🌆",
        "label": "Market Close",
    },
    {
        "id": "weekly",
        "cmd": [str(VENV_PYTHON), "-m", "trading_lab.cli", "weekly-report", "--date", "today"],
        "schedule": {"day_of_week": "fri", "hour": 17, "minute": 0},
        "emoji": "📊",
        "label": "Weekly Review",
    },
]

_COMMANDS = [
    ("/start", "Welcome and bot status"),
    ("/status", "Bot health + scheduler status"),
    ("/summary", "T212 account summary"),
    ("/positions", "Open positions"),
    ("/scan", "Run Jarvis autonomous scan"),
    ("/buy TICKER QTY", "Preview/confirm a buy (or auto-execute)"),
    ("/sell TICKER QTY", "Preview/confirm a sell (or auto-execute)"),
    ("/journal", "Daily journal report"),
    ("/weekly", "Weekly report"),
    ("/dashboard", "Generate HTML dashboard"),
    ("/risk", "Portfolio risk assessment"),
    ("/watcher", "Position watcher status"),
    ("/reset", "Reset kill switch"),
    ("/jobs", "List scheduled jobs"),
    ("/run_job JOB", "Manually run a scheduled job"),
    ("/job_logs JOB", "Show last 50 lines of job log"),
    ("/help", "This message"),
]

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOGS_DIR / "unified_bot.log", maxBytes=2_000_000, backupCount=3
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("unified_bot")

# ── State ─────────────────────────────────────────────────────────────────────
class JobState:
    def __init__(self):
        self.last_run: dict[str, datetime] = {}
        self.last_result: dict[str, dict] = {}
        self.failure_counts: dict[str, int] = {}
        self.running: dict[str, bool] = {}
        self.last_notified: dict[str, datetime] = {}

state = JobState()


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _esc(text: str) -> str:
    return html.escape(str(text))


def _chunk(text: str, size: int = _MAX_MSG_LEN) -> list[str]:
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""
    for line in lines:
        # Handle lines that exceed the chunk size on their own
        while len(line) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:size])
            line = line[size:]
        if len(current) + len(line) > size:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


def _run_cli(*args: str, cwd: str | None = None) -> str:
    """Run a CLI command and return stdout."""
    cmd = [str(VENV_PYTHON), "-m", "trading_lab.cli", *args]
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(PROJECT_DIR / "src")},
    )
    if result.returncode != 0:
        return f"Error (code {result.returncode}):\n{result.stderr or result.stdout}"
    return result.stdout


def truncate(text: str, limit: int = _MAX_MSG_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def fmt_ago(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds/60)}m"
    return f"{int(seconds/3600)}h"


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduler core (go-trader inspired)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_python_script(cmd: list[str], cwd: str | None = None) -> tuple[str, str, int]:
    """Execute Python with semaphore + timeout + kill."""
    async with PYTHON_SEMAPHORE:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env={**os.environ, "PYTHONPATH": str(PROJECT_DIR / "src")},
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=SCRIPT_TIMEOUT)
            return stdout_b.decode("utf-8", errors="replace"), stderr_b.decode("utf-8", errors="replace"), proc.returncode or 0
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return "", f"Timed out after {SCRIPT_TIMEOUT}s", -1
        except Exception as e:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return "", str(e), -1


def should_notify_failure(job_id: str, count: int) -> bool:
    """Throttle: notify on 1st, every 10th, or hourly."""
    if count <= 1:
        return True
    if count % 10 == 0:
        return True
    last = state.last_notified.get(job_id)
    if last and (datetime.now(timezone.utc) - last).total_seconds() >= 3600:
        return True
    return False


async def run_job(application: Application, job_def: dict) -> dict:
    """Execute a scheduled trading routine."""
    job_id = job_def["id"]
    cmd = job_def["cmd"]

    state.running[job_id] = True
    start = time.time()
    logger.info(f"[{job_id}] Starting: {' '.join(cmd)}")

    stdout, stderr, exit_code = await run_python_script(cmd, cwd=str(PROJECT_DIR))
    duration = time.time() - start
    state.running[job_id] = False

    result = {
        "exit_code": exit_code,
        "duration_sec": duration,
        "stdout": stdout,
        "stderr": stderr,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state.last_run[job_id] = datetime.now(timezone.utc)
    state.last_result[job_id] = result

    # Failure throttling
    if exit_code != 0:
        state.failure_counts[job_id] = state.failure_counts.get(job_id, 0) + 1
        count = state.failure_counts[job_id]
        if should_notify_failure(job_id, count):
            state.last_notified[job_id] = datetime.now(timezone.utc)
            msg = (
                f"❌ <b>{job_def['label']}</b> failed (#{count})\n\n"
                f"<pre>{_esc(stderr[:400])}</pre>"
            )
            await send_telegram(application, msg)
    else:
        state.failure_counts[job_id] = 0
        state.last_notified[job_id] = datetime.now(timezone.utc)
        formatted = format_job_result(job_id, job_def["emoji"], job_def["label"], result)
        await send_telegram(application, formatted)

    # Persist log
    log_file = LOGS_DIR / f"{job_id}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now(timezone.utc).isoformat()} ===\n")
        f.write(f"EXIT: {exit_code} | DURATION: {duration:.1f}s\n")
        f.write(f"STDOUT:\n{stdout}\n")
        f.write(f"STDERR:\n{stderr}\n")

    logger.info(f"[{job_id}] Finished in {duration:.1f}s (exit={exit_code})")
    return result


def format_job_result(job_id: str, emoji: str, label: str, result: dict) -> str:
    """Rich Telegram message from job result."""
    exit_code = result.get("exit_code", -1)
    duration = result.get("duration_sec", 0)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    status = "✅ SUCCESS" if exit_code == 0 else "❌ FAILED"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"━━━━━━━━━━━━━━━",
        f"{emoji}  <b>{label}</b>",
        f"",
        f"⏱  <b>Duration:</b> {duration:.1f}s  |  <b>Exit:</b> {exit_code}  |  <b>{status}</b>",
        f"🕐  <b>Time:</b> {now}",
        f"",
    ]

    if stdout.strip():
        ranked = []
        metrics = {}
        body_lines = stdout.strip().splitlines()

        for line in body_lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("=") or line_stripped.startswith("-"):
                continue
            m = re.match(
                r"(\d+)\s+([A-Za-z0-9_\.]+)\s+([\d\.\-]+)\s+[\d\.\-]+\s+[\d\.\-]+\s+(\w+)\s+([\d\.\-\+]+)\s+(\w+)",
                line_stripped,
            )
            if m:
                rank, ticker, score, _, outperf, verdict = m.groups()
                ranked.append({
                    "rank": int(rank),
                    "ticker": ticker.replace("_US_EQ", "").replace("_", "/"),
                    "score": float(score),
                    "verdict": verdict,
                })
                continue
            if "candidates" in line_stripped.lower():
                metrics["candidates"] = line_stripped
            if "top" in line_stripped.lower() and "of" in line_stripped.lower():
                metrics["top_line"] = line_stripped

        if ranked:
            lines.append("<b>📈 Top Signals</b>")
            lines.append(f"{'Rank':<6} {'Ticker':<10} {'Score':<8} {'Verdict'}")
            lines.append("─" * 35)
            for r in ranked[:8]:
                emoji_v = (
                    "🟢" if r["verdict"].lower() in ["buy", "strong"]
                    else "🔴" if r["verdict"].lower() in ["sell", "weak"] else "⚪"
                )
                lines.append(f"{r['rank']:<6} {r['ticker']:<10} {r['score']:<8} {emoji_v} {r['verdict']}")
            lines.append("")

        if "candidates" in metrics:
            lines.append(f"<b>📊 Summary:</b> {_esc(metrics['candidates'])}")
        if "top_line" in metrics:
            lines.append(f"<b>🏆</b> {_esc(metrics['top_line'])}")
        lines.append("")

        if not ranked:
            preview = [l for l in body_lines[:8] if l.strip() and not l.strip().startswith("=")]
            if preview:
                lines.append("<b>📄 Output</b>")
                lines.append("<pre>" + "\n".join(preview) + "</pre>")
                lines.append("")

    if stderr.strip():
        seen = set()
        clean_errors = []
        for e in stderr.strip().splitlines():
            key = e[:80]
            if key not in seen and "possibly delisted" not in e.lower():
                seen.add(key)
                clean_errors.append(e.strip()[:120])
        if clean_errors:
            lines.append("<b>⚠️  Warnings</b>")
            for e in clean_errors[:3]:
                lines.append(f"  • <code>{_esc(e)}</code>")
            lines.append("")
        elif "possibly delisted" in stderr:
            lines.append("<i>ℹ️  Some tickers had data issues (expected)</i>")
            lines.append("")

    lines.append(f"━━━━━━━━━━━━━━━")
    lines.append(f"🤖  <i>Sid Trading Lab</i>")
    lines.append(f"<i>Commands: /jobs, /status, /run_job, /job_logs</i>")
    return "\n".join(lines)


async def send_telegram(application: Application, text: str) -> None:
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID not set — cannot send scheduled notifications")
        return
    try:
        await application.bot.send_message(
            chat_id=chat_id,
            text=truncate(text),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Telegram command handlers — Interactive trading
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "<b>🐂 Bull — Sid Trading Lab Bot</b>\n\n"
        "Demo-only. No real money. AI suggests, you decide.\n\n"
        f"Timestamp: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>\n"
        "Use /help for all commands."
    )
    await update.message.reply_html(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["<b>🐂 Bull — Available Commands</b>\n"]
    for cmd, desc in _COMMANDS:
        lines.append(f"<code>{cmd}</code> — {desc}")
    lines.append("\n<i>All orders require confirmation. Demo only.</i>")
    await update.message.reply_html("\n".join(lines))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Bot health
    settings = get_settings()
    try:
        pm = PortfolioManager(settings)
        bot_state = pm.state()
        bot_text = (
            f"<b>🟢 Bot Status: OK</b>\n"
            f"Env: <code>{_esc(settings.t212_env)}</code>  |  Orders: <code>{settings.can_place_orders}</code>\n"
            f"Positions: {len(bot_state.positions)} / {pm.MAX_POSITIONS}  |  Cash: €{bot_state.cash:,.2f}\n"
        )
    except Exception as exc:
        bot_text = f"<b>🟡 Bot Status:</b> <code>{_esc(exc)}</code>\n"

    # Scheduler health
    sched_lines = ["\n<b>📅 Scheduled Jobs</b>"]
    for job in JOBS:
        jid = job["id"]
        last = state.last_run.get(jid)
        running = state.running.get(jid, False)
        failures = state.failure_counts.get(jid, 0)
        if running:
            status = "🟡 RUNNING"
        elif last:
            ago = (datetime.now(timezone.utc) - last).total_seconds()
            status = f"🟢 {fmt_ago(ago)} ago"
        else:
            status = "⚪ Never run"
        sched_lines.append(f"{job['emoji']} <b>{job['label']}</b> — {status}")
        if failures > 0:
            sched_lines.append(f"   ⚠️ Failures: {failures}")
    sched_lines.append("\n<i>Type /jobs for job management</i>")

    await update.message.reply_html(bot_text + "\n".join(sched_lines))


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    try:
        pm = PortfolioManager(settings)
        bot_state = pm.state()
        text = (
            "<b>📊 Account Summary</b>\n\n"
            f"Cash: €{bot_state.cash:,.2f}\n"
            f"Invested: €{bot_state.invested_value:,.2f}\n"
            f"Total Value: €{bot_state.total_value:,.2f}\n"
            f"Unrealized P&L: €{bot_state.unrealized_pnl:,.2f}\n"
            f"Positions: {len(bot_state.positions)}\n"
        )
    except Exception as exc:
        text = f"<b>Error</b>\n<pre>{_esc(exc)}</pre>"
    await update.message.reply_html(text)


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    try:
        pm = PortfolioManager(settings)
        bot_state = pm.state()
        if not bot_state.positions:
            text = "<b>📋 Positions</b>\n\nNo open positions."
        else:
            lines = ["<b>📋 Open Positions</b>\n"]
            for p in bot_state.positions:
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
    await update.message.reply_html("<b>🔍 Running Jarvis scan...</b>\n<i>This may take 60–90s.</i>")
    result = await asyncio.to_thread(_run_cli, "account-summary", "--save-snapshot")
    for chunk in _chunk(f"<b>Account Summary</b>\n<pre>{_esc(result)}</pre>"):
        await update.message.reply_html(chunk)

    jarvis_path = PROJECT_DIR / "scripts/jarvis.py"
    if jarvis_path.exists():
        result = await asyncio.to_thread(
            subprocess.run,
            [str(VENV_PYTHON), str(jarvis_path)],
            capture_output=True, text=True, cwd=str(PROJECT_DIR),
            env={**os.environ, "PYTHONPATH": str(PROJECT_DIR / "src")},
        )
        stdout = result.stdout or ""
        if result.returncode != 0:
            text = f"<b>❌ Scan Error</b>\n<pre>{_esc(result.stderr or stdout)}</pre>"
        else:
            text = f"<b>🔍 Jarvis Scan Complete</b>\n<pre>{_esc(stdout[-_MAX_MSG_LEN:])}</pre>"
        for chunk in _chunk(text):
            await update.message.reply_html(chunk)
    else:
        await update.message.reply_html("<i>Jarvis script not found — skipped.</i>")


# ── Buy / Sell with inline confirmation (or AUTO-APPROVE) ─────────────────────

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
        bot_state = pm.state()
        if not pm.can_add_position(bot_state):
            await update.message.reply_html("<b>Cannot buy:</b> position limit or cash reserve reached.")
            return ConversationHandler.END

        client = Trading212Client(settings)
        current_price = client._get_current_price(ticker)
        if not current_price:
            await update.message.reply_html(f"Cannot find current price for <code>{_esc(ticker)}</code>.")
            return ConversationHandler.END

        cost = quantity * current_price
        target = pm.target_position_size(bot_state)

        if AUTO_APPROVE:
            result = pm.place_order(ticker, quantity)
            text = (
                f"<b>✅ Buy Executed (AUTO)</b>\n\n"
                f"Ticker: <code>{_esc(ticker)}</code>\n"
                f"Quantity: {quantity}\n"
                f"Price: €{current_price:.2f}\n"
                f"Cost: €{cost:,.2f}\n"
                f"Cash After: €{bot_state.cash - cost:,.2f}"
            )
            await update.message.reply_html(text)
            return ConversationHandler.END

        text = (
            f"<b>📥 Buy Preview</b>\n\n"
            f"Ticker: <code>{_esc(ticker)}</code>\n"
            f"Quantity: {quantity}\n"
            f"Price: €{current_price:.2f}\n"
            f"Estimated Cost: €{cost:,.2f}\n"
            f"Target Size: €{target:,.2f}\n"
            f"Cash After: €{bot_state.cash - cost:,.2f}\n\n"
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
        bot_state = pm.state()
        pos = next((p for p in bot_state.positions if p.ticker == ticker), None)
        if not pos:
            await update.message.reply_html(f"No open position for <code>{_esc(ticker)}</code>.")
            return ConversationHandler.END
        if quantity > pos.quantity:
            await update.message.reply_html(f"You only hold {pos.quantity} shares of {_esc(ticker)}.")
            return ConversationHandler.END

        proceeds = quantity * pos.current_price

        if AUTO_APPROVE:
            result = pm.place_order(ticker, -quantity)
            text = (
                f"<b>✅ Sell Executed (AUTO)</b>\n\n"
                f"Ticker: <code>{_esc(ticker)}</code>\n"
                f"Quantity: {quantity} / {pos.quantity}\n"
                f"Price: €{pos.current_price:.2f}\n"
                f"Proceeds: €{proceeds:,.2f}\n"
                f"P&L on lot: €{(pos.current_price - pos.avg_price) * quantity:,.2f}"
            )
            await update.message.reply_html(text)
            return ConversationHandler.END

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
                f"<b>❌ Buy Failed</b>\n<pre>{_esc(exc)}</pre>", parse_mode=ParseMode.HTML,
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
                f"<b>❌ Sell Failed</b>\n<pre>{_esc(exc)}</pre>", parse_mode=ParseMode.HTML,
            )
        return ConversationHandler.END

    await query.edit_message_text("Unknown action.")
    return ConversationHandler.END


# ── Reports & dashboard ──────────────────────────────────────────────────────

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
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"dashboard_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.html",
                caption="Trading Lab Dashboard",
            )
        os.unlink(tmp_path)
    else:
        await update.message.reply_html(f"<b>Dashboard Error</b>\n<pre>{_esc(result)}</pre>")


async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Risk assessment on current portfolio."""
    settings = get_settings()
    try:
        pm = PortfolioManager(settings)
        bot_state = pm.state()
        total_value = bot_state.total_value or 0
        invested = bot_state.invested_value or 0
        cash_pct = (bot_state.cash / total_value * 100) if total_value else 0

        lines = [
            "<b>⚠️ Risk Assessment</b>\n",
            f"Positions: {len(bot_state.positions)} / {pm.MAX_POSITIONS}  max",
            f"Cash reserve: {cash_pct:.1f}%  (min {pm.MIN_CASH_PCT}%)",
        ]

        max_weight = 0.0
        max_ticker = None
        for p in bot_state.positions:
            weight = (p.quantity * p.current_price) / total_value * 100 if total_value else 0
            if weight > max_weight:
                max_weight = weight
                max_ticker = p.ticker
            lines.append(
                f"  {_esc(p.ticker)}  weight {weight:.1f}%  "
                f"P&L {(p.current_price - p.avg_price) / p.avg_price * 100:.1f}%"
            )

        lines.append(f"\nLargest position: {_esc(max_ticker or 'N/A')} ({max_weight:.1f}%)")
        if cash_pct < pm.MIN_CASH_PCT:
            lines.append(f"🚨 Cash reserve BELOW {pm.MIN_CASH_PCT}%")
        if max_weight > 20:
            lines.append(f"🚨 Position weight above 20%")
        if len(bot_state.positions) >= pm.MAX_POSITIONS:
            lines.append(f"🚨 At max position limit")
    except Exception as exc:
        text = f"<b>Error</b>\n<pre>{_esc(exc)}</pre>"
        await update.message.reply_html(text)
        return
    for chunk in _chunk("\n".join(lines)):
        await update.message.reply_html(chunk)


async def watcher_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    try:
        watcher = PositionWatcher(settings)
        st = watcher.status()
        text = (
            "<b>👁️ Watcher Status</b>\n\n"
            f"Running: <code>{st['running']}</code>\n"
            f"Autonomy Tier: <code>{st['tier']}</code>\n"
            f"Interval: <code>{st['interval']}s</code>\n"
            f"Kill Switch: <code>{st['kill_switch_state']}</code>\n"
            f"Active Alerts: <code>{st.get('open_alerts', {})}</code>"
        )
    except Exception as exc:
        text = f"<b>Watcher Error</b>\n<pre>{_esc(exc)}</pre>"
    await update.message.reply_html(text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    try:
        logger_db = SnapshotLogger(settings.db_path)
        ks = KillSwitch(logger_db)
        ks.load_state()
        if ks.is_fired():
            ks.reset()
            await update.message.reply_html("<b>✅ Kill switch reset.</b> Trading can resume.")
        else:
            await update.message.reply_html("Kill switch is not active.")
    except Exception as exc:
        await update.message.reply_html(f"<b>Error</b>\n<pre>{_esc(exc)}</pre>")


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduler management commands
# ═══════════════════════════════════════════════════════════════════════════════

async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/jobs — list all scheduled jobs with status."""
    lines = ["<b>📅 Scheduled Jobs</b>\n"]
    for job in JOBS:
        jid = job["id"]
        last = state.last_run.get(jid)
        running = state.running.get(jid, False)
        failures = state.failure_counts.get(jid, 0)
        if running:
            status = "🟡 RUNNING"
        elif last:
            ago = (datetime.now(timezone.utc) - last).total_seconds()
            status = f"🟢 {fmt_ago(ago)} ago"
        else:
            status = "⚪ Scheduled (not yet run)"
        lines.append(
            f"{job['emoji']} <code>{jid}</code> — <b>{job['label']}</b>\n"
            f"   Status: {status}"
        )
        if failures > 0:
            lines.append(f"   ⚠️ Consecutive failures: {failures}")
        lines.append("")
    lines.append("<i>Run manually: /run_job premarket</i>")
    await update.message.reply_html("\n".join(lines))


async def run_job_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/run_job <job> — manually trigger a scheduled job."""
    if not context.args:
        await update.message.reply_html(
            "Usage: <code>/run_job &lt;job&gt;</code>\n\n"
            "Jobs: <code>premarket</code>, <code>marketopen</code>, <code>midday</code>, <code>marketclose</code>, <code>weekly</code>"
        )
        return

    job_id = context.args[0].lower()
    job_def = next((j for j in JOBS if j["id"] == job_id), None)
    if not job_def:
        await update.message.reply_html(f"❌ Unknown job: <code>{job_id}</code>")
        return

    await update.message.reply_html(f"🚀 Running <b>{job_def['label']}</b>...")
    result = await run_job(context.application, job_def)
    # run_job already sends formatted result to chat, but also reply here
    formatted = format_job_result(job_id, job_def["emoji"], job_def["label"], result)
    await update.message.reply_html(formatted)


async def job_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/job_logs <job> — show recent log tail."""
    if not context.args:
        await update.message.reply_html("Usage: <code>/job_logs &lt;job&gt;</code>")
        return

    job_id = context.args[0].lower()
    log_file = LOGS_DIR / f"{job_id}.log"
    if not log_file.exists():
        await update.message.reply_html(f"❌ No logs for <code>{job_id}</code>")
        return

    lines = log_file.read_text(encoding="utf-8").splitlines()
    tail = lines[-MAX_LOG_LINES:]
    text = f"📄 <b>{job_id}</b> logs (last {len(tail)} lines):\n\n<pre>\n" + "\n".join(tail) + "\n</pre>"
    await update.message.reply_html(truncate(text))


# ═══════════════════════════════════════════════════════════════════════════════
# Application bootstrap
# ═══════════════════════════════════════════════════════════════════════════════

async def run_scheduled_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB JobQueue callback wrapper for scheduled trading routines."""
    job_def = context.job.data
    await run_job(context.application, job_def)


def setup_job_queue(application: Application) -> None:
    """Register cron jobs using PTB JobQueue (same event loop as bot)."""
    for job_def in JOBS:
        schedule = job_def["schedule"]

        # Handle hourly repeating jobs
        if schedule.get("hour") == "*/1":
            job = application.job_queue.run_repeating(
                run_scheduled_job,
                interval=3600,  # 1 hour in seconds
                first=10,       # First run 10s after start
                name=job_def["id"],
            )
            logger.info(f"Scheduled {job_def['id']} hourly via JobQueue")
            job.data = job_def
            continue

        hour = schedule["hour"]
        minute = schedule["minute"]
        run_time = time(hour=hour, minute=minute, tzinfo=timezone.utc)

        if job_def["id"] == "weekly":
            # Friday only (0=Monday, 4=Friday)
            job = application.job_queue.run_daily(
                run_scheduled_job,
                time=run_time,
                days=(4,),
                name=job_def["id"],
            )
        else:
            # Mon–Fri trading days
            job = application.job_queue.run_daily(
                run_scheduled_job,
                time=run_time,
                days=(0, 1, 2, 3, 4),
                name=job_def["id"],
            )
        job.data = job_def
        logger.info(f"Scheduled {job_def['id']} via JobQueue at {hour:02d}:{minute:02d} UTC")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Build application
    application = Application.builder().token(token).build()

    # ── Interactive trading handlers ─────────────────────────────────────────
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("journal", journal_command))
    application.add_handler(CommandHandler("weekly", weekly_command))
    application.add_handler(CommandHandler("dashboard", dashboard_command))
    application.add_handler(CommandHandler("watcher", watcher_command))
    application.add_handler(CommandHandler("reset", reset_command))

    application.add_handler(CommandHandler("risk", risk_command))

    # Order conversation handler
    order_conv = ConversationHandler(
        entry_points=[
            CommandHandler("buy", buy_command),
            CommandHandler("sell", sell_command),
        ],
        states={
            PREVIEW: [CallbackQueryHandler(confirm_callback)],
        },
        fallbacks=[CallbackQueryHandler(confirm_callback)],
        per_chat=True,
        per_user=True,
        conversation_timeout=300,
    )
    application.add_handler(order_conv)

    # ── Scheduler management handlers ────────────────────────────────────────
    application.add_handler(CommandHandler("jobs", jobs_command))
    application.add_handler(CommandHandler("run_job", run_job_command))
    application.add_handler(CommandHandler("job_logs", job_logs_command))

    # ── Scheduler setup (PTB JobQueue) ───────────────────────────────────────
    setup_job_queue(application)

    # ── Start ──────────────────────────────────────────────────────────────
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
