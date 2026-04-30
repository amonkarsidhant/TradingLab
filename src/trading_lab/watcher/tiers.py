"""
Autonomy tiers — controls what the watcher can do without human approval.

Tier 1 (default): Alert only — send Telegram messages, never execute
Tier 2: Alert + draft — alerts + shows draft order but requires confirm
Tier 3: Auto-stops — auto-places stop-loss orders at -7%, alerts only at -3%/-5%
"""
from __future__ import annotations

from enum import IntEnum


class AutonomyTier(IntEnum):
    ALERT_ONLY = 1
    ALERT_AND_DRAFT = 2
    AUTO_STOPS = 3


class AutonomyRouter:
    """Routes actions based on autonomy tier."""

    def __init__(self, tier: int):
        self._tier = AutonomyTier(max(1, min(tier, 3)))

    @property
    def tier(self) -> AutonomyTier:
        return self._tier

    def can_place_stops(self) -> bool:
        return self._tier >= AutonomyTier.AUTO_STOPS

    def can_auto_sell(self) -> bool:
        return self._tier >= AutonomyTier.AUTO_STOPS

    def should_draft_orders(self) -> bool:
        return self._tier >= AutonomyTier.ALERT_AND_DRAFT

    def requires_confirm(self) -> bool:
        return self._tier < AutonomyTier.AUTO_STOPS
