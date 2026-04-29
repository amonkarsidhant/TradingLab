"""Performance metrics for backtest results."""

from __future__ import annotations

import math


def compute_metrics(
    equity_curve: list[dict],
    trades: list[dict],
    initial_capital: float,
) -> dict:
    """Compute standard backtest metrics from equity curve and trades.

    Returns a dict with:
      total_return_pct, cagr_pct, sharpe_ratio, max_drawdown_pct,
      win_rate, profit_factor, total_trades, winning_trades,
      losing_trades, avg_win_pct, avg_loss_pct
    """
    final = equity_curve[-1]["equity"] if equity_curve else initial_capital
    total_return_pct = ((final - initial_capital) / initial_capital) * 100

    # Daily returns (simple) for Sharpe.
    daily_returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        curr = equity_curve[i]["equity"]
        if prev > 0:
            daily_returns.append((curr - prev) / prev)

    sharpe = _sharpe_ratio(daily_returns) if daily_returns else None
    max_dd = _max_drawdown_pct(equity_curve)
    cagr = _cagr(initial_capital, final, len(equity_curve))

    completed = [t for t in trades if t.get("pnl") is not None]
    total_trades = len(completed)
    winners = [t for t in completed if t["pnl"] > 0]
    losers = [t for t in completed if t["pnl"] <= 0]
    win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else None

    gross_profit = sum(t["pnl"] for t in winners) if winners else 0.0
    gross_loss = abs(sum(t["pnl"] for t in losers)) if losers else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    avg_win = (sum(t["return_pct"] for t in winners) / len(winners)) if winners else None
    avg_loss = (sum(t["return_pct"] for t in losers) / len(losers)) if losers else None

    return {
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr, 2) if cagr is not None else None,
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate": round(win_rate, 2) if win_rate is not None else None,
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "total_trades": total_trades,
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "avg_win_pct": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss_pct": round(avg_loss, 2) if avg_loss is not None else None,
    }


def _sharpe_ratio(daily_returns: list[float]) -> float:
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    var = sum((r - mean) ** 2 for r in daily_returns) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def _max_drawdown_pct(equity_curve: list[dict]) -> float:
    peak = equity_curve[0]["equity"]
    max_dd = 0.0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _cagr(initial: float, final: float, days: int) -> float | None:
    if days < 2 or initial <= 0:
        return None
    years = days / 252
    return ((final / initial) ** (1 / years) - 1) * 100
