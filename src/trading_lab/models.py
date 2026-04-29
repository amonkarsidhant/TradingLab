from dataclasses import dataclass
from enum import Enum


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Signal:
    strategy: str
    ticker: str
    action: SignalAction
    confidence: float
    reason: str
    suggested_quantity: float = 0.0

    def is_trade_signal(self) -> bool:
        return self.action in {SignalAction.BUY, SignalAction.SELL}
