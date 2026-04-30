"""
Kill Switch — closes all positions when portfolio drawdown exceeds threshold.
"""
from __future__ import annotations

import time
from typing import Any

from trading_lab.logger import SnapshotLogger
from trading_lab.watcher.guardrails import KILL_SWITCH_PCT


class KillSwitchState:
    IDLE = "idle"
    FIRED = "fired"
    RESET_PENDING = "reset_pending"


class KillSwitch:
    def __init__(self, logger: SnapshotLogger):
        self._logger = logger
        self._state = KillSwitchState.IDLE

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    def load_state(self) -> None:
        saved = self._logger.get_watcher_state("kill_switch_state")
        self._state = saved if saved else KillSwitchState.IDLE

    def evaluate(self, portfolio_drawdown_pct: float) -> bool:
        if self._state in (KillSwitchState.FIRED, KillSwitchState.RESET_PENDING):
            return False
        if portfolio_drawdown_pct >= KILL_SWITCH_PCT:
            self._state = KillSwitchState.FIRED
            self._logger.save_watcher_state(
                "kill_switch_state", KillSwitchState.FIRED
            )
            self._logger.save_watcher_state(
                "kill_switch_fired_at",
                __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat()
            )
            return True
        return False

    def portfolio_drawdown(self, total_value: float, peak_value: float) -> float:
        if peak_value <= 0 or total_value <= 0:
            return 0.0
        return (peak_value - total_value) / peak_value

    def fire(self, broker, positions_raw: list[dict]) -> list[dict]:
        results = []
        for pos in positions_raw:
            ticker = pos.get("instrument", {}).get("ticker", "?")
            qty = pos.get("quantityAvailableForTrading", pos.get("quantity", 0))
            if qty > 0:
                try:
                    result = broker.market_order(
                        ticker=ticker, quantity=-qty, dry_run=False
                    )
                    results.append({"ticker": ticker, "status": "closed", "result": result})
                    self._logger.save_watcher_event(
                        ticker=ticker,
                        drawdown_pct=KILL_SWITCH_PCT,
                        action_taken="kill_switch_close",
                        details=f"Closed {qty} shares via kill switch",
                    )
                    time.sleep(1.2)
                except Exception as e:
                    results.append({"ticker": ticker, "status": "failed", "error": str(e)})
            else:
                results.append({"ticker": ticker, "status": "skipped", "reason": "no available quantity"})
        return results

    def reset(self) -> None:
        self._state = KillSwitchState.IDLE
        self._logger.save_watcher_state("kill_switch_state", KillSwitchState.IDLE)

    def is_fired(self) -> bool:
        return self._state == KillSwitchState.FIRED

    def is_idle(self) -> bool:
        return self._state == KillSwitchState.IDLE
