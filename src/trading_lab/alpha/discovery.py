"""Alpha Discovery Engine — LLM reads market context and proposes alpha hypotheses.

Phase 3 Milestone 1: Reads news, earnings, macro data and uses LLM to propose
novel quantifiable features that might predict outperformance.

No code generation — only natural language hypotheses with confidence scores.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yfinance as yf

from trading_lab.agents.runner import AgentRunner
from trading_lab.core.config import PROJECT_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlphaHypothesis:
    """A proposed alpha feature from the LLM."""

    feature_name: str
    description: str
    suggested_formula: str  # e.g., "RSI(14) * Volume_MA(20) / ATR(14)"
    target_regime: str  # "trending", "mean_reverting", "risk_off"
    confidence: float  # 0.0-1.0, LLM-estimated
    source: str = "llm"  # "llm", "manual", "simulation"


class AlphaDiscoveryEngine:
    """Discovers alpha hypotheses via LLM + market context."""

    def __init__(
        self,
        watchlist: list[str] | None = None,
        llm_provider: str | None = None,
    ):
        self.watchlist = watchlist or ["SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]
        self.llm_provider = llm_provider or os.getenv("LLM_PROVIDER", "openrouter")
        self.runner = AgentRunner(
            provider=self.llm_provider,
            model=os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4"),
        )
        self.prompt_path = PROJECT_DIR / "prompts" / "alpha_discovery.txt"

    # ── Context Gathering ───────────────────────────────────────────────────────

    def _fetch_context(self) -> dict:
        """Gather market context for LLM prompt."""
        context: dict[str, any] = {
            "timestamp": _now_iso(),
            "watchlist": self.watchlist,
        }

        # VIX proxy
        try:
            vix = yf.Ticker("VIXY")
            vix_hist = vix.history(period="5d")
            if not vix_hist.empty:
                context["vixy_close"] = float(vix_hist["Close"].iloc[-1])
                context["vixy_change_5d"] = float(
                    (vix_hist["Close"].iloc[-1] - vix_hist["Close"].iloc[0])
                    / vix_hist["Close"].iloc[0]
                    * 100
                )
        except Exception as exc:
            logger.warning("VIXY fetch failed: %s", exc)

        # SPY recent performance
        try:
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="5d")
            if not spy_hist.empty:
                context["spy_close"] = float(spy_hist["Close"].iloc[-1])
                context["spy_change_5d"] = float(
                    (spy_hist["Close"].iloc[-1] - spy_hist["Close"].iloc[0])
                    / spy_hist["Close"].iloc[0]
                    * 100
                )
        except Exception as exc:
            logger.warning("SPY fetch failed: %s", exc)

        # Sector rotation proxy (XLY / XLP)
        try:
            xly = yf.Ticker("XLY").history(period="5d")["Close"]
            xlp = yf.Ticker("XLP").history(period="5d")["Close"]
            if not xly.empty and not xlp.empty:
                context["sector_rotation"] = float(xly.iloc[-1] / xlp.iloc[-1])
        except Exception as exc:
            logger.warning("Sector rotation fetch failed: %s", exc)

        # News headlines for watchlist (first 3 tickers only to avoid rate limits)
        news: list[dict] = []
        for ticker in self.watchlist[:3]:
            try:
                t = yf.Ticker(ticker)
                ticker_news = t.news
                if ticker_news:
                    for item in ticker_news[:3]:
                        news.append(
                            {
                                "ticker": ticker,
                                "title": item.get("title", ""),
                                "publisher": item.get("publisher", ""),
                            }
                        )
            except Exception as exc:
                logger.debug("News fetch for %s failed: %s", ticker, exc)
        context["headlines"] = news[:10]  # cap at 10 headlines

        # Earnings calendar (placeholder — yfinance doesn't have reliable earnings calendar)
        # Use known upcoming earnings for major tickers
        context["earnings_this_week"] = self._known_earnings()

        return context

    def _known_earnings(self) -> list[dict]:
        """Return known upcoming earnings for watchlist tickers.

        In production, this would call an earnings API (e.g., Alpha Vantage,
        Finnhub, or scrape Yahoo Finance earnings calendar).
        """
        # Placeholder: return empty list; user can override with real data
        return []

    # ── LLM Prompting ─────────────────────────────────────────────────────────

    def _build_prompt(self, context: dict, strategy_id: str) -> str:
        """Build the alpha discovery prompt from template + context."""
        if self.prompt_path.exists():
            template = self.prompt_path.read_text()
        else:
            template = _DEFAULT_PROMPT

        # Serialize context as JSON for readability
        context_json = json.dumps(context, indent=2, default=str)

        return template.format(
            strategy_id=strategy_id,
            watchlist=", ".join(self.watchlist),
            context=context_json,
        )

    def discover(self, strategy_id: str = "simple_momentum", limit: int = 3) -> list[AlphaHypothesis]:
        """Run alpha discovery for a strategy.

        Returns up to `limit` hypotheses sorted by confidence descending.
        """
        context = self._fetch_context()
        prompt = self._build_prompt(context, strategy_id)

        logger.info("Running alpha discovery for %s (limit=%d)", strategy_id, limit)

        try:
            response = self.runner.run(prompt, max_tokens=4000)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return []

        hypotheses = self._parse_response(response, limit)
        logger.info("Discovered %d hypotheses", len(hypotheses))
        return hypotheses

    # ── Response Parsing ──────────────────────────────────────────────────────

    def _parse_response(self, response: str, limit: int) -> list[AlphaHypothesis]:
        """Parse LLM response into AlphaHypothesis objects.

        Expected format (markdown):
        ### Hypothesis 1
        - **Feature:** rsi_volatility_ratio
        - **Description:** ...
        - **Formula:** RSI(14) / ATR(14)
        - **Target Regime:** mean_reverting
        - **Confidence:** 0.72
        """
        hypotheses: list[AlphaHypothesis] = []

        # Try JSON first
        try:
            data = json.loads(response)
            if isinstance(data, list):
                for item in data[:limit]:
                    h = AlphaHypothesis(
                        feature_name=item.get("feature_name", "unknown"),
                        description=item.get("description", ""),
                        suggested_formula=item.get("suggested_formula", ""),
                        target_regime=item.get("target_regime", "unknown"),
                        confidence=float(item.get("confidence", 0.5)),
                    )
                    hypotheses.append(h)
                return hypotheses
        except json.JSONDecodeError:
            pass

        # Fallback: parse markdown
        lines = response.split("\n")
        current: dict[str, str] = {}

        for line in lines:
            line = line.strip()
            if line.startswith("### Hypothesis") or line.startswith("## Hypothesis"):
                if current:
                    h = self._hypothesis_from_dict(current)
                    if h:
                        hypotheses.append(h)
                current = {}
            elif line.startswith("- **Feature:**") or line.startswith("- **feature:**"):
                current["feature_name"] = line.split(":", 1)[1].strip().strip("`*")
            elif line.startswith("- **Description:**") or line.startswith("- **description:**"):
                current["description"] = line.split(":", 1)[1].strip()
            elif line.startswith("- **Formula:**") or line.startswith("- **formula:**") or line.startswith("- **Suggested Formula:**"):
                current["suggested_formula"] = line.split(":", 1)[1].strip().strip("`")
            elif line.startswith("- **Target Regime:**") or line.startswith("- **target_regime:**"):
                current["target_regime"] = line.split(":", 1)[1].strip().lower()
            elif line.startswith("- **Confidence:**") or line.startswith("- **confidence:**"):
                try:
                    current["confidence"] = line.split(":", 1)[1].strip()
                except IndexError:
                    pass

        if current:
            h = self._hypothesis_from_dict(current)
            if h:
                hypotheses.append(h)

        # Sort by confidence descending, cap at limit
        hypotheses.sort(key=lambda x: x.confidence, reverse=True)
        return hypotheses[:limit]

    def _hypothesis_from_dict(self, d: dict) -> AlphaHypothesis | None:
        """Build AlphaHypothesis from parsed dict."""
        name = d.get("feature_name", "")
        if not name:
            return None
        conf_str = d.get("confidence", "0.5")
        try:
            confidence = float(conf_str)
        except ValueError:
            confidence = 0.5
        return AlphaHypothesis(
            feature_name=name,
            description=d.get("description", ""),
            suggested_formula=d.get("suggested_formula", ""),
            target_regime=d.get("target_regime", "unknown"),
            confidence=max(0.0, min(1.0, confidence)),
        )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


_DEFAULT_PROMPT = """You are a quantitative research assistant. Your job is to propose novel alpha hypotheses — quantifiable features that might predict short-term outperformance.

CURRENT MARKET CONTEXT:
{context}

TARGET STRATEGY: {strategy_id}
WATCHLIST: {watchlist}

TASK: Propose 3 novel alpha hypotheses. For each:
1. Feature name (snake_case)
2. Description (1-2 sentences)
3. Suggested formula using standard technical indicators
4. Target regime where it should work best (trending, mean_reverting, risk_off)
5. Confidence score (0.0-1.0)

RULES:
- Features must be computable from OHLCV + volume data
- Prefer combinations of existing indicators, not exotic data sources
- Confidence should reflect how grounded the idea is in the current context
- Do NOT write code — only natural language descriptions and formulas

OUTPUT FORMAT (JSON):
[
  {
    "feature_name": "...",
    "description": "...",
    "suggested_formula": "...",
    "target_regime": "...",
    "confidence": 0.0
  }
]
"""
