"""
Hard Guardrails — non-negotiable safety rules enforced at the daemon level.

These constants cannot be overridden by env vars, config files, or AI instructions.
They are compiled into the watcher module and are the last line of defense.
"""
from __future__ import annotations

from dataclasses import dataclass

# === NON-NEGOTIABLE CONSTANTS ===
MAX_POSITIONS = 10
MAX_PCT_PER_POSITION = 0.20
MIN_CASH_PCT = 0.10
STOP_LOSS_PCT = 0.07
KILL_SWITCH_PCT = 0.25
ALERT_THRESHOLDS = sorted([0.03, 0.05, 0.07], reverse=True)


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str | None = None


class GuardrailEnforcer:
    """Stateless guardrail checker. Every action is validated against ALL rules."""

    def check_new_position(
        self,
        current_position_count: int,
        proposed_allocation_pct: float,
        current_cash_pct: float,
    ) -> GuardrailResult:
        if current_position_count >= MAX_POSITIONS:
            return GuardrailResult(
                allowed=False,
                reason=f"GUARDRAIL: max positions ({MAX_POSITIONS}) reached",
            )
        if proposed_allocation_pct > MAX_PCT_PER_POSITION:
            return GuardrailResult(
                allowed=False,
                reason=f"GUARDRAIL: max allocation ({MAX_PCT_PER_POSITION*100:.0f}%) per position exceeded",
            )
        if current_cash_pct < MIN_CASH_PCT:
            return GuardrailResult(
                allowed=False,
                reason=f"GUARDRAIL: min cash reserve ({MIN_CASH_PCT*100:.0f}%) not met",
            )
        return GuardrailResult(allowed=True)

    def check_kill_switch(self, portfolio_drawdown_pct: float) -> GuardrailResult:
        if portfolio_drawdown_pct >= KILL_SWITCH_PCT:
            return GuardrailResult(
                allowed=True,
                reason=f"KILL SWITCH: portfolio drawdown {portfolio_drawdown_pct*100:.1f}% >= {KILL_SWITCH_PCT*100:.0f}%",
            )
        return GuardrailResult(allowed=False)

    def check_stop_trigger(self, drawdown_pct: float) -> GuardrailResult:
        return GuardrailResult(
            allowed=drawdown_pct >= STOP_LOSS_PCT,
            reason=f"Stop trigger at {drawdown_pct*100:.1f}% drawdown",
        )
