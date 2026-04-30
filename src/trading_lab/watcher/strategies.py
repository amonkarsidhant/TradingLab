"""
Deterministic strategy integration — runs existing strategy registry signals
alongside the watcher loop and logs agreement/disagreement with AI decisions.
"""
from __future__ import annotations

from trading_lab.data.market_data import make_provider
from trading_lab.logger import SnapshotLogger
from trading_lab.strategies import get_strategy, list_strategies


class DeterministicStrategyRunner:
    """Runs deterministic strategies on each tick and compares with AI."""

    def __init__(self, db_path: str, ticker: str = "SPY"):
        self.db_path = db_path
        self.ticker = ticker
        self.logger = SnapshotLogger(db_path)
        self._last_ai_action: str | None = None

    def set_ai_action(self, action: str) -> None:
        self._last_ai_action = action

    def run_and_compare(
        self, lookback: int = 30
    ) -> dict[str, dict]:
        provider = make_provider(
            source="chained",
            ticker=self.ticker,
            cache_db=self.db_path.replace(".sqlite3", "_cache.sqlite3"),
        )
        prices = provider.get_prices(ticker=self.ticker, lookback=lookback)

        results = {}
        for name in list_strategies():
            try:
                kwargs = {}
                if name == "simple_momentum":
                    kwargs = {"lookback": 5}
                elif name == "ma_crossover":
                    kwargs = {"fast": 10, "slow": 30}
                elif name == "mean_reversion":
                    kwargs = {"period": 14, "oversold": 30, "overbought": 70}
                else:
                    continue
                strategy = get_strategy(name, **kwargs)
                signal = strategy.generate_signal(ticker=self.ticker, prices=prices)
                action = signal.action.value
                results[name] = {
                    "action": action,
                    "confidence": signal.confidence,
                    "reason": signal.reason,
                }
            except Exception as e:
                results[name] = {"action": "ERROR", "error": str(e)}

        if self._last_ai_action:
            det_actions = {k: v["action"] for k, v in results.items() if v.get("action") in ("BUY", "SELL")}
            if det_actions:
                majority = max(set(det_actions.values()), key=list(det_actions.values()).count)
                if majority == self._last_ai_action:
                    self.logger.save_watcher_event(
                        ticker=self.ticker,
                        drawdown_pct=0,
                        action_taken="consensus",
                        details=f"AI={self._last_ai_action}, deterministic={det_actions}",
                    )
                else:
                    self.logger.save_watcher_event(
                        ticker=self.ticker,
                        drawdown_pct=0,
                        action_taken="divergence",
                        details=f"AI={self._last_ai_action}, deterministic={det_actions}",
                    )

        return results
