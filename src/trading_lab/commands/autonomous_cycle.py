"""CLI command: autonomous-cycle — detect regime, select strategy, scan, log."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from rich import print

logger = logging.getLogger(__name__)


def run_autonomous_cycle():
    """One full autonomous cycle: detect regime, select strategy, run scan, log."""
    from trading_lab.regime.detector import RegimeDetector
    from trading_lab.registry.selector import StrategySelector
    from trading_lab.registry.performance import StrategyPerformanceRegistry
    from trading_lab.agentic.scorer import EntryScorer

    # 1. Detect regime
    detector = RegimeDetector()
    state = detector.detect()
    regime_str = state.regime.value

    # 2. Select strategy
    selector = StrategySelector()
    strategy_id, strategy_confidence = selector.select(state)

    # 3. Run scan-rank with selected strategy (bare tickers for yfinance)
    tickers = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
        "META", "TSLA", "AMD", "KO", "JNJ",
        "PG", "V", "MA", "CRM", "ADBE",
        "INTC", "UNH", "HD", "ABBV", "XOM",
    ]
    scorer = EntryScorer()
    results = scorer.rank([(strategy_id, t) for t in tickers])
    signals_count = len(results)

    # 4. Log cycle
    registry = StrategyPerformanceRegistry()
    registry.log_cycle(
        timestamp=state.timestamp,
        regime=regime_str,
        confidence=state.confidence,
        strategy=strategy_id,
        signals_count=signals_count,
        executed_count=0,  # No auto-execution in Phase 0 yet
    )

    # 5. Report
    print(f"✅ Autonomous cycle complete")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Regime:              {regime_str} (confidence: {state.confidence:.2f})")
    print(f"Strategy selected:   {strategy_id} (selector confidence: {strategy_confidence:.2f})")
    print(f"Scan signals:        {signals_count}")
    print(f"Timestamp:           {state.timestamp}")
    print(f"VIXY:                {state.vix_proxy:.2f} | Breadth: {state.breadth_pct:.2%} | Rotation: {state.sector_rotation:.3f}")

    if results:
        top = results[0]
        print(f"Top candidate:       {top['ticker']} (score: {top['score']}, verdict: {top['verdict']})")
        f = top["factors"]
        if f:
            sharpe = f.get("sharpe", {}).get("raw", "-")
            pf = f.get("profit_factor", {}).get("raw", "-")
            stable = "Y" if f.get("stability", {}).get("stable") else "N"
            print(f"  Sharpe: {sharpe} | PF: {pf} | Stable: {stable}")

    logger.info("Autonomous cycle: regime=%s strategy=%s signals=%d", regime_str, strategy_id, signals_count)

    return {
        "regime": regime_str,
        "confidence": state.confidence,
        "strategy_id": strategy_id,
        "signals_count": signals_count,
        "timestamp": state.timestamp,
        "vix_proxy": state.vix_proxy,
        "breadth_pct": state.breadth_pct,
        "sector_rotation": state.sector_rotation,
        "trend_score": state.trend_score,
    }
