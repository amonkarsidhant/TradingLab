"""
Tiered stop-loss module — partial exits at escalating drawdown levels.

Inspired by go-trader's tiered_tp_pct and tiered_tp_atr: as drawdown deepens,
close escalating fractions of the position (e.g. 50% at -5%, remainder at -7%).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_TIERED_STOPS: tuple[dict[str, Any], ...] = (
    {"drawdown_pct": 0.05, "close_fraction": 0.5},
    {"drawdown_pct": 0.07, "close_fraction": 1.0},
)


@dataclass
class TieredStop:
    """A single tier: close this fraction when drawdown reaches this level."""
    drawdown_pct: float
    close_fraction: float


class TieredStopLoss:
    """Manages tiered stop-loss exits for open positions.

    Example config (via env or passed dict):
        tiers = (
            {"drawdown_pct": 0.05, "close_fraction": 0.5},
            {"drawdown_pct": 0.07, "close_fraction": 1.0},
        )
        ts = TieredStopLoss(tiers)
        stop = ts.evaluate(ticker, drawdown, qty)
        if stop:
            qty_to_close = stop.close_fraction * qty
            broker.market_order(ticker, -qty_to_close)
    """

    def __init__(self, tiers: tuple[dict[str, Any], ...] | None = None):
        self.tiers: list[TieredStop] = []
        for t in tiers or DEFAULT_TIERED_STOPS:
            dd = float(t.get("drawdown_pct", t.get("dd", 0)))
            cf = float(t.get("close_fraction", t.get("fraction", 0)))
            if dd > 0 and cf > 0:
                self.tiers.append(TieredStop(drawdown_pct=dd, close_fraction=cf))
        self.tiers.sort(key=lambda x: x.drawdown_pct)
        self._closed_fraction: dict[str, float] = {}
        self._last_hit_tier: dict[str, float] = {}

    def evaluate(
        self,
        ticker: str,
        drawdown_pct: float,
        current_qty: float,
    ) -> TieredStop | None:
        """Return the single newly triggered tier, or None."""
        already = self._closed_fraction.get(ticker, 0.0)
        last_hit = self._last_hit_tier.get(ticker, -1.0)
        hit: TieredStop | None = None
        cumulative = already

        for tier in self.tiers:
            if drawdown_pct >= tier.drawdown_pct and tier.drawdown_pct > last_hit:
                new_cumulative = min(cumulative + tier.close_fraction, 1.0)
                actionable = new_cumulative - cumulative
                if actionable > 0.001:
                    hit = TieredStop(
                        drawdown_pct=tier.drawdown_pct,
                        close_fraction=actionable,
                    )
                    cumulative = new_cumulative
                    self._last_hit_tier[ticker] = tier.drawdown_pct

        if hit:
            self._closed_fraction[ticker] = cumulative

        return hit

    def reset(self, ticker: str) -> None:
        """Clear tracked state for a ticker (on full exit or position close)."""
        self._closed_fraction.pop(ticker, None)
        self._last_hit_tier.pop(ticker, None)

    def close_qty_for(self, ticker: str, drawdown_pct: float, total_qty: float) -> float:
        """Immediate quantity to close RIGHT NOW at this drawdown."""
        hit = self.evaluate(ticker, drawdown_pct, total_qty)
        if hit is None:
            return 0.0
        return round(total_qty * hit.close_fraction, 4)

    def get_closed_fraction(self, ticker: str) -> float:
        return self._closed_fraction.get(ticker, 0.0)
