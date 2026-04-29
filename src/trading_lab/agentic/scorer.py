"""
SignalScorer — multi-factor scoring for trade signals.

Scores each signal by combining:
1. Strategy confidence (0-1)
2. Backtest quality (Sharpe ratio normalized)
3. Price momentum strength (% move magnitude)
4. Win rate from backtest

Higher score = more attractive trade.
"""
from __future__ import annotations

from trading_lab.backtest.engine import BacktestEngine
from trading_lab.models import Signal


class SignalScorer:
    """Score trade signals using multi-factor analysis."""

    def score(self, signal: Signal, prices: list[float]) -> float:
        """Return a composite score (0-100) for a signal.

        Factors:
        - confidence (0-1) → 0-40 points
        - momentum strength (% move) → 0-30 points
        - backtest Sharpe (if computable) → 0-30 points
        """
        confidence_score = min(signal.confidence, 1.0) * 40

        # Momentum strength: bigger % move = higher score (capped)
        if len(prices) >= 2:
            pct_move = (prices[-1] - prices[0]) / prices[0] * 100
            momentum_score = min(abs(pct_move) * 2, 30)  # 15% move = max score
        else:
            momentum_score = 0

        # Backtest Sharpe (quick backtest on recent data)
        sharpe_score = self._estimate_sharpe(signal, prices)

        total = confidence_score + momentum_score + sharpe_score
        return round(total, 2)

    def _estimate_sharpe(self, signal: Signal, prices: list[float]) -> float:
        """Quick backtest on recent prices to estimate Sharpe."""
        if len(prices) < 20:
            return 15  # neutral mid-point

        try:
            from trading_lab.strategies import get_strategy

            kwargs = {}
            if signal.strategy == "simple_momentum":
                kwargs = {"lookback": 5}
            elif signal.strategy == "ma_crossover":
                kwargs = {"fast": 10, "slow": 30}
            elif signal.strategy == "mean_reversion":
                kwargs = {"period": 14, "oversold": 30, "overbought": 70}

            strategy = get_strategy(signal.strategy, **kwargs)
            engine = BacktestEngine(strategy, initial_capital=10000.0)
            result = engine.run(prices=prices, ticker=signal.ticker)
            sharpe = result.metrics.get("sharpe_ratio")
            if sharpe is None:
                return 15
            # Normalize Sharpe: 0→15, 1→22, 2→30 (cap at 30)
            return min(15 + sharpe * 7.5, 30)
        except Exception:
            return 15

    def rank(self, candidates: list[tuple[Signal, list[float]]]) -> list[tuple[Signal, float]]:
        """Rank signals by score, highest first."""
        scored = [(signal, self.score(signal, prices)) for signal, prices in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
