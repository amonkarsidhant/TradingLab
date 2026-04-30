"""
PortfolioManager — autonomous portfolio management for demo trading.

Reads account state, manages positions, executes trades, enforces constraints.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.config import Settings
from trading_lab.engine import ExecutionEngine
from trading_lab.logger import SnapshotLogger
from trading_lab.risk import RiskPolicy


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_price: float
    current_price: float
    current_value: float
    unrealized_pnl: float
    peak_price: float = 0.0
    quantity_available: float = 0.0
    quantity_in_pies: float = 0.0
    fx_impact: float = 0.0
    account_currency: str = ""
    instrument_currency: str = ""


@dataclass
class PortfolioState:
    cash: float
    total_value: float
    invested_value: float
    unrealized_pnl: float
    positions: list[Position]
    account_currency: str = ""


class PortfolioManager:
    """Manages a demo portfolio with allocation rules.

    Constraints:
    - Max positions: 10
    - Max % per position: 20% of total equity
    - Min cash reserve: 10%
    - Trailing stop: -7% from peak price
    - Rebalance when signal turns to SELL
    """

    MAX_POSITIONS = 10
    MAX_PCT_PER_POSITION = 0.20
    MIN_CASH_PCT = 0.10
    TRAILING_STOP_PCT = 0.07

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Trading212Client(settings)
        self.logger = SnapshotLogger(settings.db_path)
        self.engine = ExecutionEngine(
            broker=self.client,
            risk_policy=RiskPolicy(
                max_quantity_per_order=100.0,
                min_confidence_to_trade=0.50,
                trailing_stop_pct=self.TRAILING_STOP_PCT,
            ),
            logger=self.logger,
        )
        self._peak_path = Path("memory/position_peaks.json")

    def _load_peaks(self) -> dict[str, float]:
        if self._peak_path.exists():
            try:
                return json.loads(self._peak_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_peaks(self, peaks: dict[str, float]) -> None:
        self._peak_path.parent.mkdir(parents=True, exist_ok=True)
        self._peak_path.write_text(json.dumps(peaks, indent=2), encoding="utf-8")

    def state(self) -> PortfolioState:
        summary = self.client.account_summary()
        positions_raw = self.client.positions()

        cash = summary.get("cash", {}).get("availableToTrade", 0)
        total = summary.get("totalValue", 0)
        invested = summary.get("investments", {}).get("currentValue", 0)
        pnl = summary.get("investments", {}).get("unrealizedProfitLoss", 0)
        account_currency = summary.get("currency", "")

        peaks = self._load_peaks()
        positions = []
        for p in positions_raw:
            inst = p.get("instrument", {})
            wp = p.get("walletImpact", {})
            ticker = inst.get("ticker", "?")
            current_price = p.get("currentPrice", 0)
            avg_price = p.get("averagePricePaid", 0)
            peak = max(peaks.get(ticker, avg_price), current_price, avg_price)
            peaks[ticker] = peak
            positions.append(Position(
                ticker=ticker,
                quantity=p.get("quantity", 0),
                avg_price=avg_price,
                current_price=current_price,
                current_value=wp.get("currentValue", 0),
                unrealized_pnl=wp.get("unrealizedProfitLoss", 0),
                peak_price=peak,
                quantity_available=p.get("quantityAvailableForTrading", 0),
                quantity_in_pies=p.get("quantityInPies", 0),
                fx_impact=wp.get("fxImpact", 0),
                account_currency=wp.get("currency", account_currency),
                instrument_currency=inst.get("currency", ""),
            ))
        self._save_peaks(peaks)

        return PortfolioState(
            cash=cash,
            total_value=total,
            invested_value=invested,
            unrealized_pnl=pnl,
            positions=positions,
            account_currency=account_currency,
        )

    def trailing_stop_hit(self, position: Position) -> bool:
        if position.peak_price <= 0 or position.current_price <= 0:
            return False
        drawdown = (position.peak_price - position.current_price) / position.peak_price
        return drawdown >= self.TRAILING_STOP_PCT

    def position_drawdown(self, position: Position) -> float:
        if position.peak_price <= 0:
            return 0.0
        return (position.peak_price - position.current_price) / position.peak_price

    def target_position_size(self, state: PortfolioState) -> float:
        max_per_pos = state.total_value * self.MAX_PCT_PER_POSITION
        min_cash_reserve = state.total_value * self.MIN_CASH_PCT
        deployable = max(0, state.cash - min_cash_reserve)
        slots = max(1, self.MAX_POSITIONS - len(state.positions))
        return min(max_per_pos, deployable / slots)

    def can_add_position(self, state: PortfolioState) -> bool:
        if len(state.positions) >= self.MAX_POSITIONS:
            return False
        min_cash = state.total_value * self.MIN_CASH_PCT
        if state.cash <= min_cash:
            return False
        return True

    def place_order(self, ticker: str, quantity: float) -> dict:
        if not self.settings.can_place_orders:
            raise RuntimeError("Order placement disabled in config")
        return self.client.market_order(ticker=ticker, quantity=quantity, dry_run=False)

    def place_stop_order(
        self, ticker: str, quantity: float, stop_price: float
    ) -> dict:
        if not self.settings.can_place_orders:
            raise RuntimeError("Order placement disabled in config")
        return self.client.stop_order(
            ticker=ticker, quantity=quantity, stop_price=stop_price, dry_run=False
        )

    def sell_position(self, position: Position) -> dict:
        result = self.place_order(position.ticker, -position.quantity_available or -position.quantity)
        peaks = self._load_peaks()
        peaks.pop(position.ticker, None)
        self._save_peaks(peaks)
        return result

    def get_open_tickers(self, state: PortfolioState | None = None) -> set[str]:
        if state is None:
            state = self.state()
        return {p.ticker for p in state.positions}
