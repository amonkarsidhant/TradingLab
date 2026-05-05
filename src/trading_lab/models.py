from dataclasses import dataclass
from enum import Enum


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeValidity(str, Enum):
    DAY = "DAY"
    GOOD_TILL_CANCEL = "GOOD_TILL_CANCEL"


@dataclass(frozen=True)
class Signal:
    strategy: str
    ticker: str
    action: SignalAction
    confidence: float
    reason: str
    suggested_quantity: float = 0.0
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_validity: TimeValidity = TimeValidity.DAY
    regime: str = ""           # <-- Phase 0: regime at signal generation time

    def is_trade_signal(self) -> bool:
        return self.action in {SignalAction.BUY, SignalAction.SELL}
