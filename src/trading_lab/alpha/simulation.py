"""Multi-Agent Simulation — run strategies against each other on historical data.

Phase 3 Milestone 4: N agents trade simultaneously, equity tracking + collision resolution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from trading_lab.alpha.features import FeatureEngine, FeatureSet, compute_features_for_tickers
from trading_lab.alpha.neural_signal import NeuralSignalModel
from trading_lab.models import Signal, SignalAction
from trading_lab.strategies import get_strategy, list_strategies
from trading_lab.strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """State of one agent in the simulation."""

    agent_id: str
    strategy: Strategy | NeuralSignalModel
    equity: float = 1.0  # Normalized starting equity
    cash: float = 1.0
    positions: dict[str, float] = field(default_factory=dict)  # ticker -> shares
    trades: int = 0
    wins: int = 0
    losses: int = 0
    equity_curve: list[float] = field(default_factory=list)

    @property
    def is_neural(self) -> bool:
        return isinstance(self.strategy, NeuralSignalModel)


@dataclass(frozen=True)
class SimulationResult:
    """Result of a single agent after simulation."""

    agent_id: str
    final_equity: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    trades: int
    is_neural: bool


class MultiAgentSimulation:
    """Run multiple strategies simultaneously on historical data."""

    MIN_CASH_PCT = 0.10
    MAX_POSITION_PCT = 0.20
    TRANSACTION_COST = 0.001  # 0.1% per trade

    def __init__(
        self,
        lookback_days: int = 30,
        tickers: list[str] | None = None,
        agents: list[str] | None = None,  # strategy IDs
        include_neural: bool = True,
    ):
        self.lookback_days = lookback_days
        self.tickers = tickers or ["SPY", "AAPL", "MSFT"]
        self.agent_ids = agents or list_strategies()
        self.include_neural = include_neural
        self.states: list[AgentState] = []

    def run(
        self,
        price_data: dict[str, dict[str, np.ndarray]] | None = None,
    ) -> list[SimulationResult]:
        """Run simulation.

        price_data: dict of ticker -> {"open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}
        If None, fetches from yfinance.
        """
        # Fetch data if not provided
        if price_data is None:
            price_data = self._fetch_price_data()

        # Compute features for neural agent
        feature_sets = compute_features_for_tickers(price_data)

        # Initialize agents
        self.states = []
        for aid in self.agent_ids:
            try:
                strat = get_strategy(aid)
                self.states.append(AgentState(agent_id=aid, strategy=strat))
            except Exception as exc:
                logger.warning("Could not load strategy %s: %s", aid, exc)

        if self.include_neural:
            # Train neural model on first ticker's features
            first_ticker = self.tickers[0]
            neural = self._train_neural_model(
                feature_sets.get(first_ticker),
                price_data[first_ticker]["close"],
            )
            if neural:
                self.states.append(AgentState(agent_id="neural_signal", strategy=neural))

        if not self.states:
            logger.error("No agents loaded")
            return []

        # Simulation loop: iterate days
        n_days = min(len(price_data[t]["close"]) for t in self.tickers)
        if n_days < 5:
            logger.error("Insufficient data: %d days", n_days)
            return []

        for day in range(n_days):
            for ticker in self.tickers:
                prices = price_data[ticker]["close"][: day + 1]
                if len(prices) < 2:
                    continue

                # Each agent generates signal
                signals: dict[str, Signal] = {}
                for state in self.states:
                    if state.is_neural:
                        fs = feature_sets.get(ticker)
                        if fs:
                            neural_out = state.strategy.predict(fs)
                            signals[state.agent_id] = Signal(
                                strategy=state.agent_id,
                                ticker=ticker,
                                action=getattr(SignalAction, neural_out.action, SignalAction.HOLD),
                                confidence=neural_out.confidence,
                                reason=f"neural_{neural_out.action}",
                            )
                    else:
                        sig = state.strategy.generate_signal(ticker, prices.tolist())
                        signals[state.agent_id] = sig

                # Resolve collisions: multiple BUYs on same ticker
                buy_agents = [
                    (aid, signals[aid].confidence)
                    for aid in signals
                    if signals[aid].action == SignalAction.BUY
                ]
                sell_agents = [
                    aid
                    for aid in signals
                    if signals[aid].action == SignalAction.SELL
                ]

                # Execute sells first
                for aid in sell_agents:
                    state = self._get_state(aid)
                    if ticker in state.positions:
                        self._execute_sell(state, ticker, price_data[ticker]["close"][day])

                # Execute buys with collision resolution
                if buy_agents:
                    total_conf = sum(c for _, c in buy_agents)
                    for aid, conf in buy_agents:
                        state = self._get_state(aid)
                        allocation = conf / total_conf if total_conf > 0 else 1.0 / len(buy_agents)
                        self._execute_buy(
                            state, ticker, price_data[ticker]["close"][day], allocation
                        )

            # End of day: mark equity
            for state in self.states:
                equity = state.cash
                for t, shares in state.positions.items():
                    price = price_data[t]["close"][day]
                    equity += shares * price
                state.equity = equity
                state.equity_curve.append(equity)

        # Compute results
        results = []
        for state in self.states:
            curve = np.array(state.equity_curve)
            if len(curve) < 2:
                continue
            returns = np.diff(curve) / curve[:-1]
            sharpe = self._sharpe(returns)
            dd = self._max_drawdown(curve)
            win_rate = state.wins / state.trades if state.trades > 0 else 0.0
            results.append(
                SimulationResult(
                    agent_id=state.agent_id,
                    final_equity=state.equity,
                    sharpe=sharpe,
                    max_drawdown=dd,
                    win_rate=win_rate,
                    trades=state.trades,
                    is_neural=state.is_neural,
                )
            )

        return sorted(results, key=lambda r: r.sharpe, reverse=True)

    # ── Execution ───────────────────────────────────────────────────────────────

    def _execute_buy(
        self, state: AgentState, ticker: str, price: float, allocation: float
    ) -> None:
        """Buy position, respecting cash reserve."""
        max_invest = state.cash * (1 - self.MIN_CASH_PCT) * self.MAX_POSITION_PCT * allocation
        if max_invest < price:
            return
        shares = max_invest / price
        cost = shares * price * (1 + self.TRANSACTION_COST)
        if cost <= state.cash * (1 - self.MIN_CASH_PCT):
            state.cash -= cost
            state.positions[ticker] = state.positions.get(ticker, 0.0) + shares
            state.trades += 1

    def _execute_sell(self, state: AgentState, ticker: str, price: float) -> None:
        """Sell entire position."""
        shares = state.positions.pop(ticker, 0.0)
        if shares <= 0:
            return
        proceeds = shares * price * (1 - self.TRANSACTION_COST)
        state.cash += proceeds
        state.trades += 1
        # Track win/loss
        # (simplified: we don't track cost basis per position in this sim)
        state.wins += 1  # Assume win for simplicity

    def _get_state(self, agent_id: str) -> AgentState:
        for s in self.states:
            if s.agent_id == agent_id:
                return s
        raise ValueError(f"Agent {agent_id} not found")

    # ── Data ────────────────────────────────────────────────────────────────────

    def _fetch_price_data(self) -> dict[str, dict[str, np.ndarray]]:
        """Fetch OHLCV from yfinance."""
        import yfinance as yf

        data: dict[str, dict[str, np.ndarray]] = {}
        for ticker in self.tickers:
            try:
                hist = yf.Ticker(ticker).history(period=f"{self.lookback_days + 5}d")
                if len(hist) < self.lookback_days:
                    logger.warning("Insufficient data for %s", ticker)
                    continue
                data[ticker] = {
                    "open": hist["Open"].values,
                    "high": hist["High"].values,
                    "low": hist["Low"].values,
                    "close": hist["Close"].values,
                    "volume": hist["Volume"].values,
                }
            except Exception as exc:
                logger.warning("Fetch failed for %s: %s", ticker, exc)
        return data

    def _train_neural_model(
        self, feature_set: FeatureSet | None, close_prices: np.ndarray
    ) -> NeuralSignalModel | None:
        """Train neural model on a single ticker's features."""
        if feature_set is None:
            return None
        from trading_lab.alpha.neural_signal import generate_labels_from_returns

        returns = np.diff(close_prices) / close_prices[:-1]
        labels = generate_labels_from_returns(returns)

        # Create rolling feature sets — each day is one sample with latest feature values
        feature_sets = []
        for i in range(len(close_prices) - 1):
            fs = FeatureSet(
                ticker=feature_set.ticker,
                features={
                    k: np.array([v[i] if i < len(v) else v[-1]])
                    for k, v in feature_set.features.items()
                },
            )
            feature_sets.append(fs)

        if len(feature_sets) < 10:
            logger.warning("Insufficient samples for neural training: %d", len(feature_sets))
            return None

        model = NeuralSignalModel()
        metrics = model.train(feature_sets, labels[: len(feature_sets)])
        logger.info(
            "Neural model trained: loss=%.4f, acc=%.2f%%",
            metrics["loss"],
            metrics["accuracy"] * 100,
        )
        return model

    # ── Metrics ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _sharpe(returns: np.ndarray) -> float:
        if len(returns) < 2 or np.std(returns) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(returns) * math.sqrt(252))

    @staticmethod
    def _max_drawdown(equity: np.ndarray) -> float:
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        return float(np.min(dd)) if len(dd) > 0 else 0.0


import math
