"""
Regime-aware cash allocation — decides how much cash to hold
based on detected market regime, not inertia.
"""
from __future__ import annotations

from trading_lab.agentic.market_regime import MarketRegimeDetector
from trading_lab.data.market_data import make_provider


class CashAllocator:
    """Compares actual cash position to regime-target and recommends action."""

    def __init__(self, cache_db: str = "./trading_lab_cache.sqlite3"):
        self.detector = MarketRegimeDetector()
        self.cache_db = cache_db

    def analyze(self, total_value: float, cash: float, positions_count: int) -> dict:
        provider = make_provider(
            source="chained", ticker="SPY", cache_db=self.cache_db,
        )
        prices = provider.get_prices(ticker="SPY", lookback=60)
        regime = self.detector.detect(prices)

        cash_pct = cash / max(total_value, 1)

        target_cash_pct = 0.10 * regime.cash_reserve_multiplier
        max_position_pct = 0.20 * regime.position_size_multiplier
        target_invested_pct = 1.0 - target_cash_pct

        gap_pct = cash_pct - target_cash_pct
        gap_value = gap_pct * total_value

        slots = max(0, 10 - positions_count)
        deployable_per_slot = min(
            total_value * max_position_pct,
            max(0, gap_value) / max(slots, 1),
        )

        return {
            "regime": regime.regime,
            "regime_description": regime.description,
            "actual_cash_pct": round(cash_pct * 100, 1),
            "target_cash_pct": round(target_cash_pct * 100, 1),
            "gap_pct": round(gap_pct * 100, 1),
            "gap_value": round(gap_value, 2),
            "max_position_pct": round(max_position_pct * 100, 1),
            "deployable_per_slot": round(deployable_per_slot, 2),
            "free_slots": slots,
            "recommended_stop_pct": round(regime.trailing_stop_pct * 100, 1),
            "preferred_strategies": regime.preferred_strategies,
            "action": self._action(cash_pct, target_cash_pct),
        }

    @staticmethod
    def _action(cash_pct: float, target: float) -> str:
        if cash_pct > target + 0.15:
            return "DEPLOY — cash significantly above target"
        if cash_pct > target + 0.05:
            return "DEPLOY — cash moderately above target"
        if cash_pct < target - 0.05:
            return "REDUCE — cash below target, raise cash"
        return "OK — cash near target"
