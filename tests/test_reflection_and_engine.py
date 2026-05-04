"""Tests for reflection engine, auto-stop branch, and backtest cost model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from trading_lab.agentic.portfolio import Position, PortfolioState
from trading_lab.agentic.reflection import (
    MungerReflectionEngine,
    _SECTOR_CONCENTRATION_THRESHOLD_PCT,
    _TICKER_TO_SECTOR,
)
from trading_lab.backtest.engine import BacktestEngine
from trading_lab.engine import ExecutionEngine
from trading_lab.models import Signal, SignalAction, OrderType
from trading_lab.risk import RiskPolicy
from trading_lab.strategies.base import Strategy


# ── reflection: sector lookup ─────────────────────────────────────────────────

def test_ticker_to_sector_index_built_from_universes():
    assert _TICKER_TO_SECTOR["AAPL_US_EQ"] == "Technology"
    assert _TICKER_TO_SECTOR["JPM_US_EQ"] == "Financials"
    assert _TICKER_TO_SECTOR["XOM_US_EQ"] == "Energy"


def test_sector_for_unknown_ticker_returns_other():
    engine = _build_engine_no_state()
    assert engine._sector_for("UNKNOWN_XX_EQ") == "Other"


# ── reflection: concentration ────────────────────────────────────────────────

def test_concentration_flag_fires_for_any_sector_over_threshold():
    """Health > 50% must flag — not just Tech."""
    engine = _build_engine_no_state()
    state = PortfolioState(
        cash=100, total_value=1000, invested_value=900, unrealized_pnl=0,
        positions=[
            _pos("LLY_US_EQ", current_value=600),   # Healthcare 60%
            _pos("JPM_US_EQ", current_value=300),   # Financials 30%
        ],
    )
    flagged, exposure = engine._check_concentration(state)
    assert flagged is True
    assert exposure["Healthcare"] == 60.0
    assert exposure["Financials"] == 30.0


def test_concentration_does_not_flag_below_threshold():
    engine = _build_engine_no_state()
    state = PortfolioState(
        cash=100, total_value=1000, invested_value=900, unrealized_pnl=0,
        positions=[
            _pos("AAPL_US_EQ", current_value=400),
            _pos("LLY_US_EQ", current_value=400),
            _pos("JPM_US_EQ", current_value=100),
        ],
    )
    flagged, _ = engine._check_concentration(state)
    assert flagged is False


def test_concentration_other_bucket_does_not_trigger_flag():
    """Non-S&P500 names accumulate in 'Other'; that bucket should not flag."""
    engine = _build_engine_no_state()
    state = PortfolioState(
        cash=0, total_value=1000, invested_value=1000, unrealized_pnl=0,
        positions=[_pos("XYZ_US_EQ", current_value=900)],
    )
    flagged, exposure = engine._check_concentration(state)
    assert flagged is False
    assert exposure["Other"] == 90.0


# ── reflection: pnl% denominator ─────────────────────────────────────────────

def test_pnl_pct_uses_real_cost_basis_not_total_minus_unrealized():
    """Cash deposits used to inflate the old denominator. Verify cost-basis math."""
    engine = _build_engine_no_state()
    # Cost basis: 10 * 100 = 1000. Unrealized PnL: 200. → +20%.
    # Old (broken) math would use total_value - unrealized_pnl = 5000 → +4%.
    state = PortfolioState(
        cash=4000, total_value=6200, invested_value=2200, unrealized_pnl=200,
        positions=[_pos("AAPL_US_EQ", current_value=1200, avg_price=100, quantity=10)],
    )
    engine.pm.state = MagicMock(return_value=state)
    engine.pm.position_drawdown = MagicMock(return_value=0.0)
    with patch.object(engine, "_detect_regime", return_value=_fake_regime()):
        report = engine.reflect()
    assert report.portfolio_pnl_pct == 20.0


# ── reflection: days_held ────────────────────────────────────────────────────

def test_days_held_parses_iso8601_and_handles_z_suffix():
    engine = _build_engine_no_state()
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert engine._days_held(five_days_ago) == 5
    # Z-suffixed UTC string from T212
    z_iso = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert engine._days_held(z_iso) == 3


def test_days_held_returns_zero_for_blank_or_garbage():
    engine = _build_engine_no_state()
    assert engine._days_held("") == 0
    assert engine._days_held("not a date") == 0


# ── execution engine: auto-stop ──────────────────────────────────────────────

def test_auto_stop_uses_broker_price_oracle_not_positions():
    """Critical fix: new tickers (not held) used to get price=0 → stop at $0."""
    broker = MagicMock()
    broker._get_current_price.return_value = 200.0
    broker.market_order.return_value = {"id": 1}
    broker.stop_order.return_value = {"id": 2}
    broker.positions.side_effect = AssertionError(
        "auto-stop must NOT call positions() — that was the old broken path"
    )

    risk = RiskPolicy(trailing_stop_pct=0.07, max_quantity_per_order=100.0)
    engine = ExecutionEngine(broker=broker, risk_policy=risk, auto_stop=True)

    signal = Signal(
        strategy="test", ticker="NEW_US_EQ", action=SignalAction.BUY,
        confidence=0.9, reason="test", suggested_quantity=5.0,
        order_type=OrderType.MARKET,
    )
    result = engine.handle_signal(signal, dry_run=False)

    broker._get_current_price.assert_called_once_with("NEW_US_EQ")
    broker.stop_order.assert_called_once()
    kwargs = broker.stop_order.call_args.kwargs
    assert kwargs["ticker"] == "NEW_US_EQ"
    assert kwargs["quantity"] == -5.0
    # 200 * 0.93 = 186.0
    assert kwargs["stop_price"] == 186.0
    assert result["auto_stop_result"] == {"id": 2}


def test_auto_stop_skipped_under_dry_run():
    broker = MagicMock()
    broker._get_current_price.return_value = 100.0
    risk = RiskPolicy(trailing_stop_pct=0.07, max_quantity_per_order=100.0)
    engine = ExecutionEngine(broker=broker, risk_policy=risk, auto_stop=True)

    signal = Signal(
        strategy="test", ticker="AAPL_US_EQ", action=SignalAction.BUY,
        confidence=0.9, reason="test", suggested_quantity=1.0,
    )
    result = engine.handle_signal(signal, dry_run=True)
    broker.stop_order.assert_not_called()
    assert result["auto_stop_result"] is None


def test_auto_stop_skipped_when_disabled():
    broker = MagicMock()
    risk = RiskPolicy(trailing_stop_pct=0.07, max_quantity_per_order=100.0)
    engine = ExecutionEngine(broker=broker, risk_policy=risk, auto_stop=False)

    signal = Signal(
        strategy="test", ticker="AAPL_US_EQ", action=SignalAction.BUY,
        confidence=0.9, reason="test", suggested_quantity=1.0,
    )
    engine.handle_signal(signal, dry_run=False)
    broker.stop_order.assert_not_called()


def test_auto_stop_does_not_fire_on_zero_price():
    """If price oracle returns 0, do NOT place a $0 stop order."""
    broker = MagicMock()
    broker._get_current_price.return_value = 0.0
    risk = RiskPolicy(trailing_stop_pct=0.07, max_quantity_per_order=100.0)
    engine = ExecutionEngine(broker=broker, risk_policy=risk, auto_stop=True)

    signal = Signal(
        strategy="test", ticker="WEIRD_US_EQ", action=SignalAction.BUY,
        confidence=0.9, reason="test", suggested_quantity=1.0,
    )
    result = engine.handle_signal(signal, dry_run=False)
    broker.stop_order.assert_not_called()
    assert result["auto_stop_result"] is None


# ── backtest cost model ──────────────────────────────────────────────────────

class _AlwaysBuyOnceStrategy(Strategy):
    """Stateless test strategy: BUY at len==2, SELL at len==4. HOLD elsewhere.

    Stateless so the backtest engine's min-window probing doesn't disturb behavior.
    """
    name = "always_buy_once"

    def generate_signal(self, ticker: str, prices: list[float]) -> Signal:
        n = len(prices)
        if n == 2:
            return Signal(strategy="t", ticker=ticker, action=SignalAction.BUY,
                          confidence=1.0, reason="entry", suggested_quantity=1.0)
        if n == 4:
            return Signal(strategy="t", ticker=ticker, action=SignalAction.SELL,
                          confidence=1.0, reason="exit", suggested_quantity=1.0)
        return Signal(strategy="t", ticker=ticker, action=SignalAction.HOLD,
                      confidence=0.0, reason="hold")


def test_backtest_zero_costs_matches_naive_pnl():
    """Sanity: with zero commission/slippage, PnL = (exit_entry - entry_price) * qty.

    Strategy BUYs at window len==2 (prices[1]=105.0), SELL at len==4 which
    never fires with 3 prices, so trade closes at last price (110.0).
    """
    engine = BacktestEngine(_AlwaysBuyOnceStrategy(), initial_capital=10_000)
    prices = [100.0, 105.0, 110.0]
    result = engine.run(prices=prices, ticker="X_US_EQ")
    assert result.trades, "expected at least one closed trade"
    trade = result.trades[0]
    assert trade.entry_price == 105.0, f"expected BUY at prices[1]=105, got {trade.entry_price}"
    assert trade.exit_price == 110.0
    assert trade.pnl == 5.0


def test_backtest_slippage_worsens_fills_on_both_sides():
    """1% slippage: buy at 105*1.01=106.05, sell at 110*0.99=108.9."""
    engine = BacktestEngine(
        _AlwaysBuyOnceStrategy(), initial_capital=10_000, slippage_pct=0.01,
    )
    prices = [100.0, 105.0, 110.0]
    result = engine.run(prices=prices, ticker="X_US_EQ")
    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(106.05), f"got {trade.entry_price}"
    assert trade.exit_price == pytest.approx(108.9), f"got {trade.exit_price}"


def test_backtest_commission_reduces_pnl():
    """With 1% commission, the round-trip eats notional on both sides."""
    no_cost = BacktestEngine(_AlwaysBuyOnceStrategy(), initial_capital=10_000)
    with_cost = BacktestEngine(
        _AlwaysBuyOnceStrategy(), initial_capital=10_000, commission_pct=0.01,
    )
    prices = [100.0, 105.0, 110.0]
    no = no_cost.run(prices=prices, ticker="X_US_EQ").trades[0]
    yes = with_cost.run(prices=prices, ticker="X_US_EQ").trades[0]
    assert yes.pnl < no.pnl, "commission must reduce realized PnL"


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_engine_no_state() -> MungerReflectionEngine:
    """Construct a reflection engine without hitting the network."""
    engine = MungerReflectionEngine.__new__(MungerReflectionEngine)
    engine.settings = MagicMock(db_path="./x.sqlite3")
    engine.pm = MagicMock()
    engine.regime_detector = MagicMock()
    engine.round_trips = MagicMock()
    engine.round_trips.get_sharpe_for.return_value = {
        "win_rate": 0.5, "loss_rate": 0.5, "avg_return_wins": 0.1,
        "avg_return_losses": -0.05, "total_round_trips": 10,
        "avg_bars_open": 5.0, "max_consecutive_wins": 3,
        "max_consecutive_losses": 2,
    }
    return engine


def _pos(ticker: str, current_value: float, avg_price: float = 100.0,
         quantity: float = 1.0) -> Position:
    return Position(
        ticker=ticker, quantity=quantity, avg_price=avg_price,
        current_price=current_value / max(quantity, 1),
        current_value=current_value,
        unrealized_pnl=current_value - (avg_price * quantity),
        peak_price=current_value / max(quantity, 1),
    )


def _fake_regime():
    from trading_lab.agentic.reflection import RegimeSummary
    return RegimeSummary(
        regime="bull", description="x", cash_target_pct=10.0,
        position_size_pct=20.0, recommended_stop_pct=7.0,
        recommended_strategies=["momentum"],
    )


# Confirm the threshold constant is what the rules table claims (50%)
def test_concentration_threshold_is_50_per_not_to_do_list():
    assert _SECTOR_CONCENTRATION_THRESHOLD_PCT == 50.0
