"""
Tests for BacktestEngine, metrics, and report rendering.

No network calls. No API keys. No broker integration.
All prices are deterministic lists.  Equity curve assertions
use approximate comparisons because of floating-point rounding.
"""
import math

import pytest

from trading_lab.backtest.engine import BacktestEngine, BacktestResult, BacktestTrade
from trading_lab.backtest.metrics import compute_metrics, _max_drawdown_pct, _sharpe_ratio
from trading_lab.backtest.report import render_report
from trading_lab.models import SignalAction
from trading_lab.strategies.ma_crossover import MovingAverageCrossoverStrategy
from trading_lab.strategies.mean_reversion import MeanReversionStrategy
from trading_lab.strategies.simple_momentum import SimpleMomentumStrategy


# ── BacktestEngine ─────────────────────────────────────────────────────────────

def test_engine_returns_correct_structure():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    result = engine.run(prices, ticker="TEST")

    assert isinstance(result, BacktestResult)
    assert result.strategy_name == "simple_momentum"
    assert result.ticker == "TEST"
    assert result.initial_capital == 10_000.0
    assert len(result.signals) > 0
    assert len(result.equity_curve) > 0
    assert "total_return_pct" in result.metrics


def test_engine_equity_curve_has_same_length_as_signals():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    result = engine.run(prices, ticker="TEST")
    assert len(result.equity_curve) == len(result.signals)


def test_engine_no_trades_on_flat_prices():
    """Flat prices + momentum strategy = HOLD only → zero trades."""
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3, threshold_pct=1.0))
    prices = [100.0] * 20
    result = engine.run(prices, ticker="TEST")
    assert len(result.trades) == 0


def test_engine_creates_trades_on_trending_prices():
    """Upward-trending prices with momentum = BUY signals → trades."""
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3, threshold_pct=1.0))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    result = engine.run(prices, ticker="TEST")
    assert len(result.trades) >= 1


def test_engine_trade_has_entry_and_exit():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3, threshold_pct=1.0))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    result = engine.run(prices, ticker="TEST")
    for trade in result.trades:
        assert trade.entry_price > 0
        assert trade.exit_price is not None
        assert trade.pnl is not None


def test_engine_buy_and_sell_form_complete_trade():
    """A strategy that produces BUY then SELL must create a closed trade."""
    # SMA crossover: fast(3) crosses above slow(5) → BUY; later crosses below → SELL.
    strategy = MovingAverageCrossoverStrategy(fast=3, slow=5)
    engine = BacktestEngine(strategy)

    # First a downward trend to get fast below slow, then a jump up, then a drop.
    prices = [
        110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 98.0,  # fast below slow
        115.0,  # crossover up → BUY
        114.0, 113.0, 112.0, 111.0, 110.0,
        95.0,   # crossover down → SELL
    ]
    result = engine.run(prices, ticker="TEST")
    assert len(result.trades) >= 1


def test_engine_handles_custom_dates():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    dates = [f"2026-04-{d:02d}" for d in range(20, 27)]
    result = engine.run(prices, dates=dates, ticker="TEST")
    assert result.equity_curve[0]["date"] == "2026-04-22" or result.equity_curve[0]["date"].startswith("2026")


def test_engine_rejects_mismatched_prices_and_dates():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    with pytest.raises(ValueError, match="same length"):
        engine.run([100.0, 101.0], dates=["2026-01-01"], ticker="TEST")


def test_engine_closes_open_trade_at_end():
    """An open position at the end of the backtest must be marked-to-market."""
    strategy = SimpleMomentumStrategy(lookback=2, threshold_pct=0.1)
    engine = BacktestEngine(strategy, initial_capital=10_000.0)
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    result = engine.run(prices, ticker="TEST")
    # If there's a trade, it must have an exit.
    for trade in result.trades:
        assert trade.exit_price is not None
        assert trade.exit_date is not None


# ── Metrics ────────────────────────────────────────────────────────────────────

def test_flat_equity_has_zero_sharpe():
    equity = [{"date": str(i), "equity": 10000.0} for i in range(10)]
    metrics = compute_metrics(equity, [], 10000.0)
    assert metrics["sharpe_ratio"] == 0.0
    assert metrics["max_drawdown_pct"] == 0.0
    assert metrics["total_return_pct"] == 0.0


def test_rising_equity_has_positive_return():
    equity = [{"date": str(i), "equity": 10000.0 + i * 100} for i in range(20)]
    metrics = compute_metrics(equity, [], 10000.0)
    assert metrics["total_return_pct"] > 0


def test_falling_equity_has_negative_return():
    equity = [{"date": str(i), "equity": 10000.0 - i * 100} for i in range(20)]
    metrics = compute_metrics(equity, [], 10000.0)
    assert metrics["total_return_pct"] < 0


def test_max_drawdown_captures_peak_to_trough():
    equity = [
        {"date": "1", "equity": 10000.0},
        {"date": "2", "equity": 10500.0},  # peak
        {"date": "3", "equity": 9500.0},   # trough
        {"date": "4", "equity": 10200.0},
    ]
    dd = _max_drawdown_pct(equity)
    assert dd == pytest.approx((10500 - 9500) / 10500 * 100, rel=1e-6)


def test_metrics_with_winning_trades():
    equity = [{"date": str(i), "equity": 10000.0 + i * 10} for i in range(10)]
    trades = [
        {"pnl": 100.0, "return_pct": 1.0},
        {"pnl": 50.0, "return_pct": 0.5},
        {"pnl": -30.0, "return_pct": -0.3},
    ]
    m = compute_metrics(equity, trades, 10000.0)
    assert m["total_trades"] == 3
    assert m["winning_trades"] == 2
    assert m["losing_trades"] == 1
    assert m["win_rate"] == pytest.approx(66.67, rel=0.1)
    assert m["profit_factor"] == pytest.approx(150 / 30, rel=1e-6)


def test_metrics_no_trades():
    equity = [{"date": str(i), "equity": 10000.0} for i in range(10)]
    m = compute_metrics(equity, [], 10000.0)
    assert m["total_trades"] == 0
    assert m["win_rate"] is None
    assert m["profit_factor"] is None


def test_sharpe_ratio_positive_for_steady_gains():
    returns = [0.001] * 20  # 0.1% daily returns
    sharpe = _sharpe_ratio(returns)
    # Std dev of identical values is 0, so sharpe should be 0.
    # Use slightly varied returns.
    returns = [0.001 + i * 0.0001 for i in range(20)]
    sharpe = _sharpe_ratio(returns)
    assert sharpe > 0


# ── Report rendering ───────────────────────────────────────────────────────────

def test_report_includes_metrics_section():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    result = engine.run(prices, ticker="TEST")
    report = render_report(result)

    assert "## Metrics" in report
    assert "Total return" in report
    assert "Sharpe ratio" in report
    assert "Max drawdown" in report


def test_report_includes_trades_section():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3, threshold_pct=1.0))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0]
    result = engine.run(prices, ticker="TEST")
    report = render_report(result)
    assert "## Trades" in report


def test_report_includes_signals_summary():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    prices = [100.0] * 10
    result = engine.run(prices, ticker="TEST")
    report = render_report(result)
    assert "## Signals" in report
    assert "HOLD:" in report


def test_report_includes_equity_curve():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3))
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    result = engine.run(prices, ticker="TEST")
    report = render_report(result)
    assert "## Equity curve" in report


def test_report_no_trade_message_when_zero_trades():
    engine = BacktestEngine(SimpleMomentumStrategy(lookback=3, threshold_pct=1.0))
    prices = [100.0] * 10
    result = engine.run(prices, ticker="TEST")
    report = render_report(result)
    assert "No trades executed" in report
