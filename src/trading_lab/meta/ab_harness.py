"""A/B Harness — compare two strategies on the same tickers, same period.

Phase 1 Milestone 5: Statistical comparison of two strategy variants.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.data.market_data import make_provider
from trading_lab.strategies import get_strategy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ABResult:
    baseline_name: str
    variant_name: str
    ticker: str
    baseline_metrics: dict
    variant_metrics: dict
    baseline_trades: int
    variant_trades: int
    sharpe_diff: float
    win_rate_diff: float
    t_stat: float | None
    p_value: float | None
    verdict: str  # "pass", "fail", "inconclusive"
    reason: str


class ABHarness:
    """Run A/B backtests: baseline strategy vs variant strategy."""

    # Adopt if: variant Sharpe > baseline + MIN_SHARPE_DIFF, p < P_THRESHOLD, drawdown no worse
    MIN_SHARPE_DIFF = 0.10
    P_THRESHOLD = 0.10  # 90% confidence (two-sided → one-sided about 0.05)
    MAX_DD_WORSENING_PCT = 2.0  # variant max drawdown can be at most +2pct worse

    def __init__(
        self,
        capital: float = 10_000.0,
        min_sharpe_diff: float = 0.0,
        p_threshold: float = 0.0,
        max_dd_worsening: float = 0.0,
    ):
        self.capital = capital
        self.min_sharpe_diff = min_sharpe_diff or self.MIN_SHARPE_DIFF
        self.p_threshold = p_threshold or self.P_THRESHOLD
        self.max_dd_worsening = max_dd_worsening or self.MAX_DD_WORSENING_PCT

    def compare(
        self,
        baseline_name: str,
        variant_name: str,
        tickers: list[str] | None = None,
        lookback_days: int = 126,
    ) -> list[ABResult]:
        """Run A/B comparison across tickers, returning one ABResult per ticker."""
        tickers = tickers or ["SPY", "AAPL", "MSFT", "GOOGL", "AMZN"]
        results: list[ABResult] = []

        for ticker in tickers:
            result = self._compare_one(baseline_name, variant_name, ticker, lookback_days)
            if result:
                results.append(result)

        return results

    def _compare_one(
        self,
        baseline_name: str,
        variant_name: str,
        ticker: str,
        lookback_days: int,
    ) -> ABResult | None:
        provider = make_provider(source="yfinance", ticker=ticker)
        prices_data = provider.get_prices(ticker=ticker, lookback=lookback_days + 5)

        if prices_data is None:
            logger.warning("No data for %s — skipping A/B", ticker)
            return None

        closes = prices_data["Close"].values if hasattr(prices_data, "values") else prices_data
        dates = (
            prices_data.index.strftime("%Y-%m-%d").tolist()
            if hasattr(prices_data, "index")
            else [str(i) for i in range(len(closes))]
        )

        if len(closes) < 30:
            logger.warning("Only %d bars for %s — skipping A/B", len(closes), ticker)
            return None

        # Baseline
        baseline = get_strategy(baseline_name)
        baseline_engine = BacktestEngine(baseline, initial_capital=self.capital)
        baseline_result = baseline_engine.run(prices=closes, dates=dates, ticker=ticker)

        # Variant
        variant = get_strategy(variant_name)
        variant_engine = BacktestEngine(variant, initial_capital=self.capital)
        variant_result = variant_engine.run(prices=closes, dates=dates, ticker=ticker)

        # Daily returns from equity curves
        baseline_returns = self._daily_returns(baseline_result.equity_curve)
        variant_returns = self._daily_returns(variant_result.equity_curve)

        t_stat, p_value = self._welch_test(baseline_returns, variant_returns)

        # Drawdown comparison
        base_dd = baseline_result.metrics.get("max_drawdown_pct", 100)
        var_dd = variant_result.metrics.get("max_drawdown_pct", 100)
        dd_delta = var_dd - base_dd

        sharpe_diff = (variant_result.metrics.get("sharpe_ratio") or 0) - (
            baseline_result.metrics.get("sharpe_ratio") or 0
        )
        win_rate_diff = (variant_result.metrics.get("win_rate") or 0) - (
            baseline_result.metrics.get("win_rate") or 0
        )

        verdict, reason = self._verdict(
            sharpe_diff=sharpe_diff,
            p_value=p_value,
            dd_delta=dd_delta,
            variant_sharpe=variant_result.metrics.get("sharpe_ratio") or 0,
        )

        return ABResult(
            baseline_name=baseline_name,
            variant_name=variant_name,
            ticker=ticker,
            baseline_metrics=baseline_result.metrics,
            variant_metrics=variant_result.metrics,
            baseline_trades=len(baseline_result.trades),
            variant_trades=len(variant_result.trades),
            sharpe_diff=round(sharpe_diff, 3),
            win_rate_diff=round(win_rate_diff, 1),
            t_stat=round(t_stat, 3) if t_stat else None,
            p_value=round(p_value, 4) if p_value else None,
            verdict=verdict,
            reason=reason,
        )

    @staticmethod
    def _daily_returns(equity_curve: list[dict[str, Any]]) -> list[float]:
        returns = []
        for i in range(1, len(equity_curve)):
            prev, curr = equity_curve[i - 1]["equity"], equity_curve[i]["equity"]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    @staticmethod
    def _welch_test(baseline: list[float], variant: list[float]) -> tuple[float, float] | tuple[None, None]:
        if len(baseline) < 5 or len(variant) < 5:
            return None, None
        a = np.array(baseline, dtype=float)
        b = np.array(variant, dtype=float)
        na, nb = len(a), len(b)
        ma, mb = a.mean(), b.mean()
        sa2 = a.var(ddof=1) if na > 1 else 0.0
        sb2 = b.var(ddof=1) if nb > 1 else 0.0
        denom = math.sqrt(sa2 / na + sb2 / nb) if (sa2 / na + sb2 / nb) > 0 else 1e-9
        t = (mb - ma) / denom
        # Degrees of freedom (Welch–Satterthwaite)
        num = (sa2 / na + sb2 / nb) ** 2
        den = (sa2 ** 2) / (na ** 2 * max(na - 1, 1)) + (sb2 ** 2) / (nb ** 2 * max(nb - 1, 1))
        df = num / den if den > 0 else max(na, nb) - 1
        # Approximate p-value from t-statistic (two-sided via error function)
        from math import erf
        p = 2 * (1 - erf(abs(t) / math.sqrt(2)))
        return float(t), float(p)

    def _verdict(self, sharpe_diff: float, p_value: float | None, dd_delta: float, variant_sharpe: float) -> tuple[str, str]:
        if p_value is None:
            return "inconclusive", "Too few observations for statistical test"

        # First gate: drawdown
        if dd_delta > self.max_dd_worsening:
            return "fail", f"Drawdown worsened by {dd_delta:.1f}% (limit {self.max_dd_worsening:.1f}%)"

        # Second gate: Sharpe improvement + significance
        if sharpe_diff >= self.min_sharpe_diff and p_value < self.p_threshold:
            return "pass", f"Sharpe +{sharpe_diff:.2f} (p={p_value:.3f}), drawdown delta {dd_delta:.1f}%"

        if sharpe_diff > 0 and p_value < self.p_threshold:
            return "pass", f"Small improvement +{sharpe_diff:.2f} (p={p_value:.3f}), drawdown delta {dd_delta:.1f}%"

        if p_value >= self.p_threshold:
            return "inconclusive", f"Not significant (p={p_value:.3f}), Sharpe diff {sharpe_diff:.2f}"

        return "fail", f"Sharpe -{abs(sharpe_diff):.2f} (p={p_value:.3f}), drawdown delta {dd_delta:.1f}%"


def run_ab_test(
    baseline: str,
    variant: str,
    tickers: list[str] | None = None,
    lookback_days: int = 126,
) -> list[dict]:
    """CLI entry point. Return list of ABResult dicts."""
    harness = ABHarness()
    results = harness.compare(baseline, variant, tickers, lookback_days)
    return [r.__dict__ for r in results]
