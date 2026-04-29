from abc import ABC, abstractmethod
from trading_lab.models import Signal


class Strategy(ABC):
    name: str

    @abstractmethod
    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        raise NotImplementedError
