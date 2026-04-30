from trading_lab.models import Signal, SignalAction, OrderType


class RiskPolicy:
    def __init__(
        self,
        max_quantity_per_order: float = 1.0,
        min_confidence_to_trade: float = 0.70,
        max_positions: int = 10,
        max_pct_per_position: float = 0.20,
        min_cash_pct: float = 0.10,
        trailing_stop_pct: float = 0.07,
        take_profit_pct: float = 0.15,
        trim_fraction: float = 0.5,
    ):
        self.max_quantity_per_order = max_quantity_per_order
        self.min_confidence_to_trade = min_confidence_to_trade
        self.max_positions = max_positions
        self.max_pct_per_position = max_pct_per_position
        self.min_cash_pct = min_cash_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.take_profit_pct = take_profit_pct
        self.trim_fraction = trim_fraction

    def approve(self, signal: Signal) -> tuple[bool, str]:
        if signal.action == SignalAction.HOLD:
            return False, "HOLD signal; no trade needed."
        if signal.confidence < self.min_confidence_to_trade:
            return False, "Signal confidence below configured threshold."
        if abs(signal.suggested_quantity) > self.max_quantity_per_order:
            return False, "Suggested quantity exceeds max quantity per order."
        return True, "Approved by basic demo risk policy."

    def trailing_stop_price(self, entry_price: float) -> float:
        return entry_price * (1 - self.trailing_stop_pct)

    def take_profit_price(self, entry_price: float) -> float:
        return entry_price * (1 + self.take_profit_pct)

    def stop_hit(self, peak_price: float, current_price: float) -> bool:
        if peak_price <= 0 or current_price <= 0:
            return False
        drawdown = (peak_price - current_price) / peak_price
        return drawdown >= self.trailing_stop_pct
