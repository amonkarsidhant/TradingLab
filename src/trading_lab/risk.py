from trading_lab.models import Signal, SignalAction


class RiskPolicy:
    def __init__(
        self,
        max_quantity_per_order: float = 1.0,
        min_confidence_to_trade: float = 0.70,
    ):
        self.max_quantity_per_order = max_quantity_per_order
        self.min_confidence_to_trade = min_confidence_to_trade

    def approve(self, signal: Signal) -> tuple[bool, str]:
        if signal.action == SignalAction.HOLD:
            return False, "HOLD signal; no trade needed."

        if signal.confidence < self.min_confidence_to_trade:
            return False, "Signal confidence below configured threshold."

        if abs(signal.suggested_quantity) > self.max_quantity_per_order:
            return False, "Suggested quantity exceeds max quantity per order."

        return True, "Approved by basic demo risk policy."
