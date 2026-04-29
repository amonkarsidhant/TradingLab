"""
Market Regime Detector — dynamic strategy parameter adjustment.

Analyzes market data to detect the current regime and returns
adjusted strategy parameters, position sizing, and risk levels.

Regimes:
  bull_trending     — positive trend, low vol → momentum favored
  bear_volatile     — negative trend, high vol → defensive, tighter stops
  ranging_calm      — flat trend, low vol → mean reversion favored
  high_volatility   — any trend, very high vol → reduce exposure, increase cash
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeParams:
    """Strategy parameters adjusted for current market regime."""
    regime: str
    description: str
    # Strategy params
    momentum_lookback: int
    ma_fast: int
    ma_slow: int
    mean_rev_period: int
    mean_rev_oversold: int
    mean_rev_overbought: int
    # Risk params
    position_size_multiplier: float  # 1.0 = normal, 0.5 = half size
    cash_reserve_multiplier: float   # 1.0 = 10%, 2.0 = 20%
    trailing_stop_pct: float       # e.g. 0.07 = 7%
    # Behavior
    preferred_strategies: list[str]


class MarketRegimeDetector:
    """Detect market regime from a price series."""

    # Thresholds
    VOL_LOW = 0.012    # 1.2% daily std
    VOL_HIGH = 0.025   # 2.5% daily std
    TREND_UP = 0.003   # 0.3% avg daily return
    TREND_DOWN = -0.003

    def detect(self, prices: list[float]) -> RegimeParams:
        """Analyze prices and return regime + adjusted parameters."""
        if len(prices) < 10:
            return self._default_params()

        returns = self._returns(prices)
        if len(returns) < 5:
            return self._default_params()

        avg_return = sum(returns) / len(returns)
        vol = self._std(returns)
        max_dd = self._max_drawdown(prices)

        # Determine regime
        if vol > self.VOL_HIGH and max_dd > 0.05:
            return self._high_volatility_params(vol, max_dd)
        elif vol > self.VOL_HIGH and avg_return < self.TREND_DOWN:
            return self._bear_volatile_params(vol, avg_return)
        elif avg_return > self.TREND_UP and vol < self.VOL_HIGH:
            return self._bull_trending_params(avg_return, vol)
        elif vol < self.VOL_LOW:
            return self._ranging_calm_params(vol)
        else:
            return self._neutral_params(avg_return, vol)

    def _returns(self, prices: list[float]) -> list[float]:
        return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

    def _std(self, values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)

    def _max_drawdown(self, prices: list[float]) -> float:
        peak = prices[0]
        max_dd = 0.0
        for p in prices:
            if p > peak:
                peak = p
            dd = (peak - p) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def _default_params(self) -> RegimeParams:
        return RegimeParams(
            regime="neutral",
            description="Insufficient data — using default parameters.",
            momentum_lookback=5,
            ma_fast=10,
            ma_slow=30,
            mean_rev_period=14,
            mean_rev_oversold=30,
            mean_rev_overbought=70,
            position_size_multiplier=1.0,
            cash_reserve_multiplier=1.0,
            trailing_stop_pct=0.07,
            preferred_strategies=["simple_momentum", "ma_crossover", "mean_reversion"],
        )

    def _bull_trending_params(self, avg_return: float, vol: float) -> RegimeParams:
        return RegimeParams(
            regime="bull_trending",
            description=f"Bull market (+{avg_return:.2%} daily, {vol:.1%} vol). Momentum favored.",
            momentum_lookback=5,
            ma_fast=10,
            ma_slow=30,
            mean_rev_period=14,
            mean_rev_oversold=30,
            mean_rev_overbought=70,
            position_size_multiplier=1.2,
            cash_reserve_multiplier=0.8,
            trailing_stop_pct=0.08,
            preferred_strategies=["simple_momentum", "ma_crossover"],
        )

    def _bear_volatile_params(self, vol: float, avg_return: float) -> RegimeParams:
        return RegimeParams(
            regime="bear_volatile",
            description=f"Bear market ({avg_return:.2%} daily, {vol:.1%} vol). Defensive mode.",
            momentum_lookback=3,
            ma_fast=5,
            ma_slow=20,
            mean_rev_period=14,
            mean_rev_oversold=25,
            mean_rev_overbought=65,
            position_size_multiplier=0.5,
            cash_reserve_multiplier=2.0,
            trailing_stop_pct=0.05,
            preferred_strategies=["mean_reversion"],
        )

    def _ranging_calm_params(self, vol: float) -> RegimeParams:
        return RegimeParams(
            regime="ranging_calm",
            description=f"Range-bound calm ({vol:.1%} vol). Mean reversion favored.",
            momentum_lookback=10,
            ma_fast=20,
            ma_slow=50,
            mean_rev_period=14,
            mean_rev_oversold=30,
            mean_rev_overbought=70,
            position_size_multiplier=1.0,
            cash_reserve_multiplier=1.0,
            trailing_stop_pct=0.06,
            preferred_strategies=["mean_reversion", "ma_crossover"],
        )

    def _high_volatility_params(self, vol: float, max_dd: float) -> RegimeParams:
        return RegimeParams(
            regime="high_volatility",
            description=f"High volatility ({vol:.1%} vol, {max_dd:.1%} drawdown). Reduce exposure.",
            momentum_lookback=3,
            ma_fast=5,
            ma_slow=20,
            mean_rev_period=10,
            mean_rev_oversold=20,
            mean_rev_overbought=80,
            position_size_multiplier=0.3,
            cash_reserve_multiplier=3.0,
            trailing_stop_pct=0.04,
            preferred_strategies=["mean_reversion"],
        )

    def _neutral_params(self, avg_return: float, vol: float) -> RegimeParams:
        return RegimeParams(
            regime="neutral",
            description=f"Mixed signals ({avg_return:.2%} daily, {vol:.1%} vol). Balanced approach.",
            momentum_lookback=5,
            ma_fast=10,
            ma_slow=30,
            mean_rev_period=14,
            mean_rev_oversold=30,
            mean_rev_overbought=70,
            position_size_multiplier=1.0,
            cash_reserve_multiplier=1.0,
            trailing_stop_pct=0.07,
            preferred_strategies=["simple_momentum", "ma_crossover", "mean_reversion"],
        )
