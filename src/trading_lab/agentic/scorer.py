"""
EntryScorer — ranks ticker+strategy combinations by objective data,
not AI comfort. Uses factsheet metrics to produce a composite score.
"""
from __future__ import annotations

from trading_lab.data.market_data import make_provider
from trading_lab.factsheet.engine import FactsheetEngine, _parameter_stability


class EntryScorer:
    """Scores a ticker+strategy combination using factsheet data.

    Factors (each 0-25 points, total 0-100):
    - Sharpe ratio (0-25)
    - Profit factor (0-25)
    - Parameter stability CV (0-25)
    - Outperformance vs buy-and-hold (0-25)
    """

    def score(self, strategy_name: str, ticker: str, capital: float = 10_000.0) -> dict:
        engine = FactsheetEngine(strategy_name, ticker, capital)
        provider = make_provider(
            source="chained", ticker=ticker,
            cache_db="./trading_lab_cache.sqlite3",
        )
        prices = provider.get_prices(ticker=ticker, lookback=252)
        data = engine.generate(prices=prices)
        m = data["backtest"]["metrics"]
        bench = data["benchmark"]
        stab = data["parameter_stability"]

        sharpe = m.get("sharpe_ratio") or 0
        pf = m.get("profit_factor")
        outperf = bench.get("outperformance_pct") or 0

        cv = stab.get("cv")
        stable = stab.get("stable_range", False)

        sharpe_score = min(max((sharpe / 2.0) * 25, 0), 25)
        pf_score = min(max((pf or 0) * 10, 0), 25) if pf else 0
        stab_score = 25 if stable else (12.5 if cv is not None and cv < 2.0 else 0)
        outp_score = min(max((outperf / 10.0) * 25, 0), 25)

        total = round(sharpe_score + pf_score + stab_score + outp_score, 1)

        return {
            "strategy": strategy_name,
            "ticker": ticker,
            "score": total,
            "factors": {
                "sharpe": {"raw": sharpe, "score": round(sharpe_score, 1)},
                "profit_factor": {"raw": pf, "score": round(pf_score, 1)},
                "stability": {"raw": cv, "score": round(stab_score, 1), "stable": stable},
                "outperformance": {"raw": round(outperf, 2), "score": round(outp_score, 1)},
            },
            "verdict": data["verdict"],
        }

    def rank(
        self,
        candidates: list[tuple[str, str]],
        capital: float = 10_000.0,
    ) -> list[dict]:
        scored = [self.score(s, t, capital) for s, t in candidates]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored
