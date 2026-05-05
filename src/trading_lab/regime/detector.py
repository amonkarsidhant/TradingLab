"""
External-data regime detector for Sid Trading Lab Phase 0.

Fetches VIXY (VIX proxy), SPY trend, sector rotation (XLY/XLP ratio),
and market breadth (percentage of major stocks above 50-day MA).

Regimes:
  risk_on     — low VIX, strong breadth, uptrend
  risk_off    — high VIX, weak breadth, downtrend
  neutral     — mixed signals
  volatile    — spiking VIX, churning breadth
  trending    — low VIX, strong directional breadth
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class Regime(Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"
    VOLATILE = "volatile"
    TRENDING = "trending"


@dataclass(frozen=True)
class RegimeState:
    regime: Regime
    vix_proxy: float
    breadth_pct: float
    sector_rotation: float
    trend_score: float
    confidence: float
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "vix_proxy": round(self.vix_proxy, 4),
            "breadth_pct": round(self.breadth_pct, 4),
            "sector_rotation": round(self.sector_rotation, 4),
            "trend_score": round(self.trend_score, 4),
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp,
        }


class RegimeDetector:
    """Detect market regime from external data (VIXY, SPY, XLY, XLP)."""

    # Thresholds (calibrated for demo; should be walk-forward optimized in Phase 1)
    VIX_HIGH = 25.0
    VIX_MED = 18.0
    BREADTH_STRONG = 0.60
    BREADTH_WEAK = 0.40
    ROTATION_RISK_ON = 1.15
    ROTATION_RISK_OFF = 0.95
    TREND_UP = 0.02
    TREND_DOWN = -0.02

    def __init__(self, breadth_tickers: Optional[list[str]] = None) -> None:
        self._breadth_tickers = breadth_tickers or [
            "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "JPM",
            "JNJ", "V", "PG", "UNH", "HD", "MA", "BAC", "ABBV", "PFE", "KO",
            "PEP", "WMT", "MRK", "AVGO", "TMO", "COST", "DIS", "ABT", "ACN",
            "DHR", "VZ", "NKE", "TXN", "ADBE", "CRM", "CMCSA", "XOM", "CVX",
            "LLY", "NFLX", "AMD", "QCOM", "HON", "INTC", "AMGN", "SPGI", "IBM",
        ]

    def detect(self) -> RegimeState:
        from datetime import datetime, timezone

        import yfinance as yf

        vix_proxy = self._fetch_vixy(yf)
        trend_score = self._fetch_spy_trend(yf)
        sector_rotation = self._fetch_sector_rotation(yf)
        breadth_pct = self._fetch_breadth(yf)

        regime, confidence = self._classify(
            vix_proxy, breadth_pct, sector_rotation, trend_score
        )

        return RegimeState(
            regime=regime,
            vix_proxy=vix_proxy,
            breadth_pct=breadth_pct,
            sector_rotation=sector_rotation,
            trend_score=trend_score,
            confidence=confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ── Fetch helpers ──────────────────────────────────────────────────────────

    def _fetch_vixy(self, yf) -> float:
        """VIXY close price as VIX proxy."""
        try:
            ticker = yf.Ticker("VIXY")
            hist = ticker.history(period="5d")
            if hist.empty:
                return 15.0
            return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.warning("VIXY fetch failed: %s", exc)
            return 15.0

    def _fetch_spy_trend(self, yf) -> float:
        """SPY return vs 20EMA minus return vs 50SMA — composite trend score."""
        try:
            ticker = yf.Ticker("SPY")
            hist = ticker.history(period="60d")
            if hist.empty or len(hist) < 50:
                return 0.0
            closes = hist["Close"].values
            ema20 = self._ema(closes, 20)
            sma50 = self._sma(closes, 50)
            if sma50 == 0:
                return 0.0
            score = (closes[-1] - ema20) / ema20 - (closes[-1] - sma50) / sma50
            return float(score)
        except Exception as exc:
            logger.warning("SPY trend fetch failed: %s", exc)
            return 0.0

    def _fetch_sector_rotation(self, yf) -> float:
        """XLY / XLP ratio.  > 1.15 = risk-on (growth), < 0.95 = risk-off (defensive)."""
        try:
            xly = yf.Ticker("XLY").history(period="5d")
            xlp = yf.Ticker("XLP").history(period="5d")
            if xly.empty or xlp.empty:
                return 1.0
            xly_close = float(xly["Close"].iloc[-1])
            xlp_close = float(xlp["Close"].iloc[-1])
            if xlp_close == 0:
                return 1.0
            return xly_close / xlp_close
        except Exception as exc:
            logger.warning("Sector rotation fetch failed: %s", exc)
            return 1.0

    def _fetch_breadth(self, yf) -> float:
        """Percentage of breadth_tickers above their 50-day MA."""
        above = 0
        total = 0
        for sym in self._breadth_tickers:
            try:
                hist = yf.Ticker(sym).history(period="60d")
                if hist.empty or len(hist) < 50:
                    continue
                closes = hist["Close"].values
                ma50 = self._sma(closes, 50)
                if closes[-1] > ma50:
                    above += 1
                total += 1
            except Exception as exc:
                logger.debug("Breadth skip %s: %s", sym, exc)
                continue
        if total == 0:
            return 0.5
        return above / total

    # ── Math helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _sma(values: np.ndarray, period: int) -> float:
        return float(np.mean(values[-period:]))

    @staticmethod
    def _ema(values: np.ndarray, period: int) -> float:
        alpha = 2 / (period + 1)
        ema = values[0]
        for v in values[1:]:
            ema = alpha * v + (1 - alpha) * ema
        return float(ema)

    # ── Classification ─────────────────────────────────────────────────────────

    def _classify(
        self,
        vix_proxy: float,
        breadth_pct: float,
        sector_rotation: float,
        trend_score: float,
    ) -> tuple[Regime, float]:
        """Map 4 metrics to regime + confidence."""

        scores: dict[Regime, float] = {r: 0.0 for r in Regime}

        # VIX scoring
        if vix_proxy > self.VIX_HIGH:
            scores[Regime.RISK_OFF] += 2.0
            scores[Regime.VOLATILE] += 1.5
        elif vix_proxy > self.VIX_MED:
            scores[Regime.NEUTRAL] += 1.0
            scores[Regime.VOLATILE] += 0.5
        else:
            scores[Regime.RISK_ON] += 1.5
            scores[Regime.TRENDING] += 1.0

        # Breadth scoring
        if breadth_pct > self.BREADTH_STRONG:
            scores[Regime.RISK_ON] += 1.5
            scores[Regime.TRENDING] += 1.0
        elif breadth_pct < self.BREADTH_WEAK:
            scores[Regime.RISK_OFF] += 1.5
            scores[Regime.VOLATILE] += 0.5
        else:
            scores[Regime.NEUTRAL] += 1.0

        # Sector rotation scoring
        if sector_rotation > self.ROTATION_RISK_ON:
            scores[Regime.RISK_ON] += 1.0
            scores[Regime.TRENDING] += 0.5
        elif sector_rotation < self.ROTATION_RISK_OFF:
            scores[Regime.RISK_OFF] += 1.0
        else:
            scores[Regime.NEUTRAL] += 0.5

        # Trend scoring
        if trend_score > self.TREND_UP:
            scores[Regime.TRENDING] += 1.5
            scores[Regime.RISK_ON] += 0.5
        elif trend_score < self.TREND_DOWN:
            scores[Regime.RISK_OFF] += 1.0
        else:
            scores[Regime.NEUTRAL] += 0.5

        best = max(scores, key=lambda r: scores[r])
        best_score = scores[best]
        total_score = sum(scores.values()) or 1.0
        confidence = best_score / total_score

        return best, confidence


def detect_regime() -> dict:
    """Convenience wrapper for CLI / tests."""
    return RegimeDetector().detect().to_dict()
