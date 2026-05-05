"""Variant Validator — backtest + A/B composite gate for generated strategies.

Phase 2 Milestone 3: Runs walk-forward backtest per variant, then A/B against
baseline. Computes composite score. Returns adoption recommendation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.meta.ab_harness import ABHarness, ABResult
from trading_lab.meta.sandbox import SyntaxSandbox
from trading_lab.meta.sweeper import StrategySweeper
from trading_lab.regime.detector import HistoricalRegimeDetector
from trading_lab.strategies import get_strategy
from trading_lab.strategies.base import Strategy

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class VariantValidationResult:
    variant_name: str
    baseline_name: str
    passes: bool
    sharpe_diff: float
    win_rate_diff: float
    dd_delta: float
    p_value: float | None
    composite_score: float
    reason: str
    ab_details: ABResult | None = None


class VariantValidator:
    """Validates a strategy variant against the baseline with composite gates."""

    # Adoption gates (ALL must pass)
    SHARPE_DIFF_MIN = 0.10
    DRAWDOWN_TOLERANCE = 2.0
    WIN_RATE_MIN = 0.50
    MIN_TRADES = 5
    P_VALUE_MAX = 0.10

    def __init__(self) -> None:
        self._sweeper = StrategySweeper()
        self._ab = ABHarness()

    # ── Public API ──────────────────────────────────────────────────────────────

    def validate(
        self,
        variant_source: str,
        baseline_id: str,
        tickers: list[str] | None = None,
        lookback_days: int = 126,
    ) -> VariantValidationResult | None:
        """Full validation pipeline for a single variant.

        1. Sandbox check
        2. Instantiate variant class
        3. Backtest on tickers
        4. A/B against baseline on same period
        5. Composite gate check
        """
        # Step 1: Sandbox
        sandbox = SyntaxSandbox.validate(variant_source)
        if not sandbox.valid:
            return VariantValidationResult(
                variant_name="unknown",
                baseline_name=baseline_id,
                passes=False,
                sharpe_diff=0.0,
                win_rate_diff=0.0,
                dd_delta=0.0,
                p_value=None,
                composite_score=-999.0,
                reason=f"Sandbox failed: {sandbox.error}",
            )

        # Step 2: Instantiate
        try:
            variant_cls = self._instantiate_from_source(variant_source)
            variant_name = getattr(variant_cls, "name", variant_cls.__name__)
        except Exception as exc:
            return VariantValidationResult(
                variant_name="unknown",
                baseline_name=baseline_id,
                passes=False,
                sharpe_diff=0.0,
                win_rate_diff=0.0,
                dd_delta=0.0,
                p_value=None,
                composite_score=-999.0,
                reason=f"Instantiation failed: {exc}",
            )

        # Step 3: Backtest both
        tickers = tickers or ["SPY"]
        ab_results = self._ab.compare(
            baseline_name=baseline_id,
            variant_name=variant_name,  # ABHarness will use get_strategy; we need a workaround
            tickers=tickers,
            lookback_days=lookback_days,
            persist=False,
        )

        # ABHarness expects both strategies to be in the registry.
        # Since the variant is not yet registered, we need a custom comparison.
        # Fall back to manual backtest + comparison.
        return self._manual_validate(variant_cls, baseline_id, tickers, lookback_days)

    # ── Manual validation (since variant is not in registry) ──────────────────────

    def _manual_validate(
        self,
        variant_cls: type[Strategy],
        baseline_id: str,
        tickers: list[str],
        lookback_days: int,
    ) -> VariantValidationResult | None:
        """Run backtests manually for both strategies and compare."""
        from trading_lab.data.market_data import make_provider
        from datetime import datetime, timedelta

        end = datetime.now()
        start = end - timedelta(days=lookback_days)

        total_sharpe_diff = 0.0
        total_win_diff = 0.0
        total_dd_delta = 0.0
        all_variant_pnls: list[float] = []
        all_baseline_pnls: list[float] = []
        total_baseline_trades = 0
        total_variant_trades = 0
        n_tickers = 0

        for ticker in tickers:
            try:
                provider = make_provider(source="yfinance", ticker=ticker)
                prices_data = provider.get_prices(ticker=ticker, lookback=lookback_days)
                if not prices_data or len(prices_data) < 30:
                    continue
                closes = prices_data if isinstance(prices_data, list) else prices_data.get("Close", {}).values.tolist()
                dates = [str(i) for i in range(len(closes))]

                baseline = get_strategy(baseline_id)
                variant = variant_cls()

                base_result = BacktestEngine(baseline).run(prices=closes, dates=dates, ticker=ticker)
                var_result = BacktestEngine(variant).run(prices=closes, dates=dates, ticker=ticker)

                base_sharpe = base_result.metrics.get("sharpe_ratio") or 0.0
                var_sharpe = var_result.metrics.get("sharpe_ratio") or 0.0
                total_sharpe_diff += (var_sharpe - base_sharpe)

                base_wr = base_result.metrics.get("win_rate") or 0.0
                var_wr = var_result.metrics.get("win_rate") or 0.0
                total_win_diff += (var_wr - base_wr)

                base_dd = base_result.metrics.get("max_drawdown_pct") or 0.0
                var_dd = var_result.metrics.get("max_drawdown_pct") or 0.0
                total_dd_delta += (var_dd - base_dd)

                # Collect daily equity returns for Welch test
                for i in range(1, len(var_result.equity_curve)):
                    prev = var_result.equity_curve[i - 1]["equity"]
                    curr = var_result.equity_curve[i]["equity"]
                    if prev > 0:
                        all_variant_pnls.append((curr - prev) / prev)

                for i in range(1, len(base_result.equity_curve)):
                    prev = base_result.equity_curve[i - 1]["equity"]
                    curr = base_result.equity_curve[i]["equity"]
                    if prev > 0:
                        all_baseline_pnls.append((curr - prev) / prev)

                total_baseline_trades += len(base_result.trades)
                total_variant_trades += len(var_result.trades)
                n_tickers += 1

            except Exception as exc:
                logger.debug("Manual validate skip %s: %s", ticker, exc)
                continue

        if n_tickers == 0:
            return None

        avg_sharpe_diff = total_sharpe_diff / n_tickers
        avg_win_diff = total_win_diff / n_tickers
        avg_dd_delta = total_dd_delta / n_tickers

        # Welch t-test on daily returns
        t_stat, p_value = ABHarness._welch_test(all_baseline_pnls, all_variant_pnls)

        # Composite score
        score = (avg_sharpe_diff * 2.0) + (avg_win_diff * 1.0) - (avg_dd_delta * 0.5)

        # Gate check
        reasons: list[str] = []
        if avg_sharpe_diff < self.SHARPE_DIFF_MIN:
            reasons.append(f"Sharpe diff {avg_sharpe_diff:.2f} < {self.SHARPE_DIFF_MIN}")
        if avg_dd_delta > self.DRAWDOWN_TOLERANCE:
            reasons.append(f"Drawdown delta {avg_dd_delta:.1f}% > {self.DRAWDOWN_TOLERANCE}%")
        if avg_win_diff + 0.5 < self.WIN_RATE_MIN:  # baseline might be ~50%, so check variant absolute
            reasons.append(f"Win rate too low")
        if total_variant_trades < self.MIN_TRADES:
            reasons.append(f"Trades {total_variant_trades} < {self.MIN_TRADES}")
        if p_value is not None and p_value > self.P_VALUE_MAX:
            reasons.append(f"p-value {p_value:.3f} > {self.P_VALUE_MAX}")

        passes = len(reasons) == 0

        return VariantValidationResult(
            variant_name=getattr(variant_cls, "name", variant_cls.__name__),
            baseline_name=baseline_id,
            passes=passes,
            sharpe_diff=round(avg_sharpe_diff, 3),
            win_rate_diff=round(avg_win_diff, 3),
            dd_delta=round(avg_dd_delta, 2),
            p_value=round(p_value, 4) if p_value else None,
            composite_score=round(score, 3),
            reason="; ".join(reasons) if reasons else "All gates passed",
        )

    # ── Internal ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _instantiate_from_source(source_code: str) -> type[Strategy]:
        """Compile source and return the Strategy subclass."""
        namespace: dict = {
            "Signal": __import__("trading_lab.models", fromlist=["Signal"]).Signal,
            "SignalAction": __import__("trading_lab.models", fromlist=["SignalAction"]).SignalAction,
            "Strategy": Strategy,
        }
        try:
            import numpy as np
            namespace["np"] = np
            namespace["numpy"] = np
        except ImportError:
            pass

        exec(compile(source_code, "<variant>", "exec"), namespace)
        for obj in namespace.values():
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                return obj
        raise ValueError("No Strategy subclass found")


def validate_variant(
    variant_source: str,
    baseline_id: str = "simple_momentum",
    tickers: list[str] | None = None,
    lookback_days: int = 126,
) -> dict:
    """CLI entry point. Returns dict for JSON serialization."""
    validator = VariantValidator()
    result = validator.validate(variant_source, baseline_id, tickers, lookback_days)
    if result is None:
        return {"error": "Validation failed — no results"}
    return {
        "variant": result.variant_name,
        "baseline": result.baseline_name,
        "passes": result.passes,
        "sharpe_diff": result.sharpe_diff,
        "win_rate_diff": result.win_rate_diff,
        "dd_delta": result.dd_delta,
        "p_value": result.p_value,
        "composite_score": result.composite_score,
        "reason": result.reason,
    }
