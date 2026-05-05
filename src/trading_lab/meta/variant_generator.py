"""Strategy Variant Generator — LLM-driven parameter mutation.

Phase 2 Milestone 1: Given a strategy's source code and performance by regime,
use an LLM to propose 3 parameter variants targeting the weakest regime.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_lab.agents.runner import AgentRunner
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.strategies import get_strategy

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class StrategyVariant:
    name: str
    code: str
    rationale: str
    base_strategy: str
    weakest_regime: str


class StrategyVariantGenerator:
    """Generates strategy variants via LLM prompt engineering."""

    PROMPT_PATH = PROJECT_DIR / "prompts" / "strategy_mutation.txt"
    MAX_RETRIES = 3

    def __init__(self, runner: AgentRunner | None = None) -> None:
        self._runner = runner

    @property
    def runner(self) -> AgentRunner:
        if self._runner is None:
            self._runner = AgentRunner()
        return self._runner

    # ── Public API ──────────────────────────────────────────────────────────────

    def generate(
        self,
        strategy_id: str,
        n_variants: int = 3,
    ) -> list[StrategyVariant]:
        """Generate N variant proposals for a strategy.

        Returns empty list if LLM fails or returns invalid JSON after retries.
        """
        source = self._read_source(strategy_id)
        if not source:
            logger.error("Cannot read source for %s", strategy_id)
            return []

        perf = self._fetch_performance(strategy_id)
        weakest = self._weakest_regime(perf)

        system_prompt = self._load_system_prompt()
        user_prompt = self._build_user_prompt(strategy_id, source, perf, weakest)

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                raw = self.runner.ask(system=system_prompt, user=user_prompt)
                variants = self._parse_json(raw, base=strategy_id, weakest=weakest)
                if variants:
                    logger.info(
                        "Generated %d variants for %s (weakest=%s) on attempt %d",
                        len(variants), strategy_id, weakest, attempt,
                    )
                    return variants
                logger.warning("Attempt %d: LLM returned empty/invalid variants", attempt)
            except Exception as exc:
                logger.warning("Attempt %d: LLM error: %s", attempt, exc)

        logger.error("Failed to generate variants for %s after %d attempts", strategy_id, self.MAX_RETRIES)
        return []

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _read_source(self, strategy_id: str) -> str:
        """Read the strategy's .py source from disk."""
        strategies_dir = PROJECT_DIR / "src" / "trading_lab" / "strategies"
        # Try exact match first
        for path in strategies_dir.glob("*.py"):
            if path.stem == strategy_id or strategy_id in path.read_text():
                return path.read_text()
        # Fallback: inspect module if already imported
        try:
            import inspect
            cls = get_strategy(strategy_id)
            return inspect.getsource(cls)
        except Exception:
            pass
        logger.warning("Could not find source file for %s in %s", strategy_id, strategies_dir)
        return ""

    def _fetch_performance(self, strategy_id: str) -> list[dict]:
        """Query strategy_regime_performance for all regimes."""
        registry = StrategyPerformanceRegistry()
        # We need all regimes for this strategy — the registry has per-regime rows
        # but no direct "all regimes for strategy" query. Use a heuristic:
        # query each known regime.
        from trading_lab.regime.detector import MarketRegime
        regimes = [r.value for r in MarketRegime]
        results: list[dict] = []
        for regime in regimes:
            rec = registry.record_for(strategy_id, regime)
            if rec:
                results.append({
                    "regime": regime,
                    "sharpe": rec.sharpe,
                    "win_rate": rec.win_rate,
                    "trades": rec.trade_count,
                    "avg_hold": rec.avg_hold_days,
                })
        return results

    @staticmethod
    def _weakest_regime(perf: list[dict]) -> str:
        """Find regime with lowest Sharpe (or fewest trades if no Sharpe data)."""
        if not perf:
            return "neutral"
        # Sort by sharpe ascending; if sharpe is 0, sort by trades descending
        scored = [(p["regime"], p.get("sharpe", 0.0), p.get("trades", 0)) for p in perf]
        scored.sort(key=lambda x: (x[1], -x[2]))
        return scored[0][0]

    def _load_system_prompt(self) -> str:
        """Load the system prompt template from prompts/strategy_mutation.txt."""
        if self.PROMPT_PATH.exists():
            return self.PROMPT_PATH.read_text()
        # Fallback inline prompt
        return (
            "You are a quantitative strategy researcher. "
            "Propose exactly 3 parameter mutations to improve the weakest regime. "
            "Return ONLY JSON with keys: name, code, rationale. "
            "Only change numeric parameters. Do not add imports or new methods."
        )

    @staticmethod
    def _build_user_prompt(
        strategy_id: str,
        source: str,
        perf: list[dict],
        weakest: str,
    ) -> str:
        """Build the user prompt with source + performance table."""
        perf_lines = "\n".join(
            f"  {p['regime']:<15} | Sharpe={p.get('sharpe',0):>6.2f} | Win={p.get('win_rate',0)*100:>5.1f}% | Trades={p.get('trades',0):>3}"
            for p in perf
        )
        return (
            f"STRATEGY: {strategy_id}\n"
            f"WEAKEST REGIME: {weakest}\n\n"
            f"SOURCE CODE:\n```python\n{source}\n```\n\n"
            f"PERFORMANCE BY REGIME:\n{perf_lines}\n\n"
            f"Generate 3 variants targeting the {weakest} regime. "
            f"Return ONLY the JSON object with key 'variants' as specified in your instructions."
        )

    @staticmethod
    def _parse_json(raw: str, base: str, weakest: str) -> list[StrategyVariant]:
        """Extract JSON from LLM response and parse variants."""
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to find a JSON block inside the text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return []
            else:
                return []

        variants = data.get("variants", [])
        if not isinstance(variants, list):
            return []

        results: list[StrategyVariant] = []
        for v in variants:
            if not isinstance(v, dict):
                continue
            name = v.get("name", "")
            code = v.get("code", "")
            rationale = v.get("rationale", "")
            if name and code:
                results.append(
                    StrategyVariant(
                        name=name,
                        code=code,
                        rationale=rationale,
                        base_strategy=base,
                        weakest_regime=weakest,
                    )
                )

        return results


def generate_variants(strategy_id: str, n: int = 3) -> list[dict]:
    """CLI entry point. Returns list of dicts for JSON serialization."""
    gen = StrategyVariantGenerator()
    variants = gen.generate(strategy_id, n_variants=n)
    return [v.__dict__ for v in variants]
