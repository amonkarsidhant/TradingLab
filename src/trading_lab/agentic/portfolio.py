"""
PortfolioManager — autonomous portfolio management for demo trading.

Reads account state, manages positions, executes trades, enforces constraints.
"""
from __future__ import annotations

from dataclasses import dataclass

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


@dataclass
class PortfolioState:
    cash: float
    total_value: float
    invested_value: float
    unrealized_pnl: float
    positions: list[Position]


class PortfolioManager:
    """Manages a demo portfolio with allocation rules.

    Constraints:
    - Max positions: 10
    - Max % per position: 20% of total equity
    - Min cash reserve: 10%
    - Rebalance when signal turns to SELL
    """

    MAX_POSITIONS = 10
    MAX_PCT_PER_POSITION = 0.20
    MIN_CASH_PCT = 0.10

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Trading212Client(settings)
        self.logger = SnapshotLogger(settings.db_path)
        self.engine = ExecutionEngine(
            broker=self.client,
            risk_policy=RiskPolicy(
                max_quantity_per_order=100.0,
                min_confidence_to_trade=0.50,
            ),
            logger=self.logger,
        )

    def state(self) -> PortfolioState:
        """Read current account state from T212."""
        summary = self.client.account_summary()
        positions_raw = self.client.positions()

        cash = summary.get("cash", {}).get("availableToTrade", 0)
        total = summary.get("totalValue", 0)
        invested = summary.get("investments", {}).get("currentValue", 0)
        pnl = summary.get("investments", {}).get("unrealizedProfitLoss", 0)

        positions = []
        for p in positions_raw:
            inst = p.get("instrument", {})
            wp = p.get("walletImpact", {})
            positions.append(Position(
                ticker=inst.get("ticker", "?"),
                quantity=p.get("quantity", 0),
                avg_price=p.get("averagePricePaid", 0),
                current_price=p.get("currentPrice", 0),
                current_value=wp.get("currentValue", 0),
                unrealized_pnl=wp.get("unrealizedProfitLoss", 0),
            ))

        return PortfolioState(
            cash=cash,
            total_value=total,
            invested_value=invested,
            unrealized_pnl=pnl,
            positions=positions,
        )

    def target_position_size(self, state: PortfolioState) -> float:
        """How much capital to allocate per new position."""
        max_per_pos = state.total_value * self.MAX_PCT_PER_POSITION
        min_cash_reserve = state.total_value * self.MIN_CASH_PCT
        deployable = max(0, state.cash - min_cash_reserve)
        slots = max(1, self.MAX_POSITIONS - len(state.positions))
        return min(max_per_pos, deployable / slots)

    def can_add_position(self, state: PortfolioState) -> bool:
        """Check if we can add another position."""
        if len(state.positions) >= self.MAX_POSITIONS:
            return False
        min_cash = state.total_value * self.MIN_CASH_PCT
        if state.cash <= min_cash:
            return False
        return True

    def place_order(self, ticker: str, quantity: float) -> dict:
        """Place a demo market order."""
        if not self.settings.can_place_orders:
            raise RuntimeError("Order placement disabled in config")
        return self.client.market_order(ticker=ticker, quantity=quantity, dry_run=False)

    def sell_position(self, position: Position) -> dict:
        """Sell an entire position."""
        return self.place_order(position.ticker, -position.quantity)

    def get_open_tickers(self, state: PortfolioState | None = None) -> set[str]:
        """Set of tickers we currently hold."""
        if state is None:
            state = self.state()
        return {p.ticker for p in state.positions}
