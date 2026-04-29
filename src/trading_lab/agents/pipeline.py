"""Review pipeline: orchestrates the multi-agent review flow.

The pipeline runs in sequence:
  1. Technical Analyst
  2. Fundamentals / Sentiment Analyst
  3. Bull Researcher  ─┐  (parallel in spirit; sequential in v1)
  4. Bear Researcher   ─┘
  5. Risk Reviewer
  6. Summary

Each agent receives the signal + context and returns a structured text
response.  Results are collected in a ReviewResult for display or logging.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from trading_lab.agents.prompts import (
    BULL_SYSTEM,
    BEAR_SYSTEM,
    FUNDAMENTALS_SYSTEM,
    RISK_REVIEWER_SYSTEM,
    TECHNICAL_ANALYST_SYSTEM,
    bear_user,
    bull_user,
    fundamentals_user,
    risk_reviewer_user,
    technical_analyst_user,
)
from trading_lab.agents.runner import AgentRunner
from trading_lab.models import Signal

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    signal: Signal
    technical_review: str
    fundamentals_review: str
    bull_case: str
    bear_case: str
    risk_review: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


class ReviewPipeline:
    """Runs a signal through all review agents and collects results."""

    def __init__(
        self,
        runner: AgentRunner | None = None,
        db_path: str | None = None,
    ) -> None:
        self._runner = runner or AgentRunner()
        self._db_path = db_path

    def review(self, signal: Signal, prices: list[float] | None = None) -> ReviewResult:
        """Run the full multi-agent review pipeline.

        Returns a ReviewResult.  Also journals to SQLite if db_path was provided.
        """
        ctx = self._build_context(signal, prices)
        signal_json = json.dumps(signal.__dict__, indent=2, default=str)

        logger.info("Reviewing %s signal from %s", signal.action.value, signal.strategy)

        technical = self._runner.ask(
            system=TECHNICAL_ANALYST_SYSTEM,
            user=technical_analyst_user(signal_json, ctx),
        )
        fundamentals = self._runner.ask(
            system=FUNDAMENTALS_SYSTEM,
            user=fundamentals_user(signal_json, ctx),
        )
        bull = self._runner.ask(
            system=BULL_SYSTEM,
            user=bull_user(signal_json, ctx),
        )
        bear = self._runner.ask(
            system=BEAR_SYSTEM,
            user=bear_user(signal_json, ctx),
        )
        risk = self._runner.ask(
            system=RISK_REVIEWER_SYSTEM,
            user=risk_reviewer_user(signal_json, ctx),
        )

        result = ReviewResult(
            signal=signal,
            technical_review=technical,
            fundamentals_review=fundamentals,
            bull_case=bull,
            bear_case=bear,
            risk_review=risk,
        )

        if self._db_path:
            self._journal(result)

        return result

    def _build_context(self, signal: Signal, prices: list[float] | None) -> str:
        parts: list[str] = []
        parts.append(f"Strategy: {signal.strategy}")
        parts.append(f"Ticker: {signal.ticker}")
        parts.append(f"Suggested action: {signal.action.value}")
        parts.append(f"Suggested quantity: {signal.suggested_quantity}")
        parts.append(f"Signal confidence: {signal.confidence}")
        parts.append(f"Signal reason: {signal.reason}")

        if prices:
            parts.append(f"Recent closes ({len(prices)} periods): {_format_prices(prices)}")
        else:
            parts.append("Price data: not provided.")

        return "\n".join(parts)

    def _journal(self, result: ReviewResult) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS agent_reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        ticker TEXT NOT NULL,
                        action TEXT NOT NULL,
                        confidence REAL,
                        technical_review TEXT,
                        fundamentals_review TEXT,
                        bull_case TEXT,
                        bear_case TEXT,
                        risk_review TEXT
                    )
                """)
                conn.execute(
                    """INSERT INTO agent_reviews
                       (created_at, strategy, ticker, action, confidence,
                        technical_review, fundamentals_review,
                        bull_case, bear_case, risk_review)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.generated_at,
                        result.signal.strategy,
                        result.signal.ticker,
                        result.signal.action.value,
                        result.signal.confidence,
                        result.technical_review,
                        result.fundamentals_review,
                        result.bull_case,
                        result.bear_case,
                        result.risk_review,
                    ),
                )
            logger.debug("Agent review journaled to %s", self._db_path)
        except Exception:
            logger.warning("Failed to journal agent review", exc_info=True)


def _format_prices(prices: list[float]) -> str:
    if len(prices) <= 10:
        return ", ".join(f"${p:.2f}" for p in prices)
    first = ", ".join(f"${p:.2f}" for p in prices[:5])
    last = ", ".join(f"${p:.2f}" for p in prices[-5:])
    return f"{first} ... {last} ({len(prices)} total)"


def render_review_report(result: ReviewResult) -> str:
    """Render a ReviewResult as a markdown report suitable for stdout or file."""
    s = result.signal
    lines: list[str] = []

    lines.append(f"# Multi-Agent Review: {s.strategy} — {s.ticker}")
    lines.append("")
    lines.append(f"**Signal:** {s.action.value} | **Confidence:** {s.confidence:.0%}")
    lines.append(f"**Reason:** {s.reason}")
    lines.append(f"**Generated:** {result.generated_at}")
    lines.append("")

    for title, content in [
        ("Technical Analyst", result.technical_review),
        ("Fundamentals Analyst", result.fundamentals_review),
        ("Bull Case", result.bull_case),
        ("Bear Case", result.bear_case),
        ("Risk Review", result.risk_review),
    ]:
        lines.append(f"## {title}")
        lines.append("")
        lines.append(content.strip())
        lines.append("")

    lines.append("---")
    lines.append("*Generated by Sid Trading Lab multi-agent review pipeline v1.*")
    lines.append("*Agents advise. The human decides.*")
    lines.append("")

    return "\n".join(lines)
