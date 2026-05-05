"""Feature Engineering Pipeline — compute quantifiable features from OHLCV.

Phase 3 Milestone 2: Built-in indicators + LLM hypothesis formula evaluation.
Pure numpy implementation for speed and zero extra dependencies.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureSet:
    """A collection of computed features for a single ticker."""

    ticker: str
    features: dict[str, np.ndarray]  # feature_name -> array (same length as prices)

    def get(self, name: str) -> np.ndarray | None:
        return self.features.get(name)

    def latest(self, name: str) -> float:
        arr = self.features.get(name)
        if arr is None or len(arr) == 0:
            return 0.0
        return float(arr[-1])

    def names(self) -> list[str]:
        return list(self.features.keys())


# ── Built-in Feature Functions ──────────────────────────────────────────────


def _sma(arr: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average — padded to input length with NaN."""
    if len(arr) < window:
        return np.full_like(arr, np.nan)
    cumsum = np.cumsum(np.insert(arr, 0, 0))
    raw = (cumsum[window:] - cumsum[:-window]) / window
    # Pad to match original length
    padded = np.full_like(arr, np.nan)
    padded[window - 1 :] = raw
    return padded


def _ema(arr: np.ndarray, window: int) -> np.ndarray:
    """Exponential moving average — padded to input length with NaN."""
    if len(arr) < window:
        return np.full_like(arr, np.nan)
    alpha = 2.0 / (window + 1)
    ema = np.zeros_like(arr)
    ema[0] = arr[0]
    for i in range(1, len(arr)):
        ema[i] = alpha * arr[i] + (1 - alpha) * ema[i - 1]
    # Until window is reached, values are warmup / unreliable
    padded = np.full_like(arr, np.nan)
    padded[window - 1 :] = ema[window - 1 :]
    return padded


def _rsi(prices: np.ndarray, window: int = 14) -> np.ndarray:
    """Relative Strength Index — padded to input length with NaN."""
    if len(prices) < window + 1:
        return np.full_like(prices, np.nan)
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = _sma(gains, window)
    avg_loss = _sma(losses, window)
    rs = np.where(avg_loss == 0, 100, avg_gain / avg_loss)
    rsi = 100 - (100 / (1 + rs))
    # rsi has length len(prices)-1; pad to len(prices), aligning at index (window)
    padded = np.full_like(prices, np.nan)
    # Valid rsi starts at index (window-1) inside rsi array
    valid_rsi = rsi[window - 1 :]
    padded[window : window + len(valid_rsi)] = valid_rsi
    return padded


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> np.ndarray:
    """Average True Range aligned to close length."""
    if len(close) < window + 1:
        return np.full_like(close, np.nan)
    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    atr = _sma(tr, window)  # len(tr), valid from index (window-1)
    padded = np.full_like(close, np.nan)
    valid = atr[window - 1:]  # len = len(tr) - (window-1) = len(close) - window
    if len(valid) > 0:
        padded[window:] = valid  # len(padded[window:]) = len(close) - window → EXACT MATCH
    return padded


def _bbands(prices: np.ndarray, window: int = 20, num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: upper, middle, lower."""
    if len(prices) < window:
        return (
            np.full_like(prices, np.nan),
            np.full_like(prices, np.nan),
            np.full_like(prices, np.nan),
        )
    middle = _sma(prices, window)
    std = np.array([np.std(prices[i : i + window]) for i in range(len(prices) - window + 1)])
    upper = middle + num_std * std
    lower = middle - num_std * std
    # Pad to match input length
    pad_upper = np.full_like(prices, np.nan)
    pad_middle = np.full_like(prices, np.nan)
    pad_lower = np.full_like(prices, np.nan)
    pad_upper[window - 1 :] = upper
    pad_middle[window - 1 :] = middle
    pad_lower[window - 1 :] = lower
    return pad_upper, pad_middle, pad_lower


def _bbands_width(prices: np.ndarray, window: int = 20, num_std: float = 2.0) -> np.ndarray:
    """Bollinger Band width: (upper - lower) / middle."""
    upper, middle, lower = _bbands(prices, window, num_std)
    return np.where(middle != 0, (upper - lower) / middle, np.nan)


def _volume_ma(volume: np.ndarray, window: int = 20) -> np.ndarray:
    """Volume moving average."""
    return _sma(volume, window)


def _volume_zscore(volume: np.ndarray, window: int = 20) -> np.ndarray:
    """Volume z-score over window."""
    if len(volume) < window:
        return np.full_like(volume, np.nan)
    z = np.full_like(volume, np.nan)
    for i in range(window - 1, len(volume)):
        window_data = volume[i - window + 1 : i + 1]
        mean = np.mean(window_data)
        std = np.std(window_data)
        z[i] = (volume[i] - mean) / std if std > 0 else 0.0
    return z


def _momentum(prices: np.ndarray, lookback: int) -> np.ndarray:
    """Price momentum over lookback periods."""
    if len(prices) <= lookback:
        return np.full_like(prices, np.nan)
    mom = (prices[lookback:] - prices[:-lookback]) / prices[:-lookback]
    padded = np.full_like(prices, np.nan)
    padded[lookback:] = mom
    return padded


def _atr_rank(atr: np.ndarray, window: int = 20) -> np.ndarray:
    """ATR percentile rank over window."""
    if len(atr) < window:
        return np.full_like(atr, np.nan)
    ranks = np.full_like(atr, np.nan)
    for i in range(window - 1, len(atr)):
        window_data = atr[i - window + 1 : i + 1]
        valid = window_data[~np.isnan(window_data)]
        if len(valid) == 0 or np.isnan(atr[i]):
            ranks[i] = np.nan
        else:
            ranks[i] = np.sum(valid < atr[i]) / len(valid)
    return ranks


# ── Feature Engine ──────────────────────────────────────────────────────────


class FeatureEngine:
    """Compute built-in and custom features from OHLCV arrays."""

    BUILT_IN: dict[str, Callable[..., np.ndarray]] = {
        "rsi_14": lambda o, h, l, c, v: _rsi(c, 14),
        "sma_20": lambda o, h, l, c, v: _sma(c, 20),
        "sma_50": lambda o, h, l, c, v: _sma(c, 50),
        "ema_12": lambda o, h, l, c, v: _ema(c, 12),
        "ema_26": lambda o, h, l, c, v: _ema(c, 26),
        "atr_14": lambda o, h, l, c, v: _atr(h, l, c, 14),
        "atr_14_pct": lambda o, h, l, c, v: _atr(h, l, c, 14) / c,
        "atr_rank_20": lambda o, h, l, c, v: _atr_rank(_atr(h, l, c, 14), 20),
        "bb_upper": lambda o, h, l, c, v: _bbands(c, 20, 2.0)[0],
        "bb_middle": lambda o, h, l, c, v: _bbands(c, 20, 2.0)[1],
        "bb_lower": lambda o, h, l, c, v: _bbands(c, 20, 2.0)[2],
        "bb_width": lambda o, h, l, c, v: _bbands_width(c, 20, 2.0),
        "price_vs_sma_20": lambda o, h, l, c, v: (c - _sma(c, 20)) / _sma(c, 20),
        "price_vs_sma_50": lambda o, h, l, c, v: (c - _sma(c, 50)) / _sma(c, 50),
        "volume_ma_20": lambda o, h, l, c, v: _volume_ma(v, 20),
        "volume_zscore_20": lambda o, h, l, c, v: _volume_zscore(v, 20),
        "momentum_5d": lambda o, h, l, c, v: _momentum(c, 5),
        "momentum_20d": lambda o, h, l, c, v: _momentum(c, 20),
    }

    def __init__(self, custom_features: dict[str, str] | None = None):
        """
        custom_features: dict of feature_name -> formula string.
        Formula can use: open, high, low, close, volume, np, math,
        and any built-in function (rsi, sma, ema, atr, bbands, etc.).
        """
        self.custom = custom_features or {}

    def compute(
        self,
        ticker: str,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        feature_names: list[str] | None = None,
    ) -> FeatureSet:
        """Compute all requested features. If None, compute all built-in + custom."""
        names = feature_names or list(self.BUILT_IN.keys()) + list(self.custom.keys())
        features: dict[str, np.ndarray] = {}

        # Pre-compute common intermediates
        rsi_14 = _rsi(close, 14)
        sma_20 = _sma(close, 20)
        sma_50 = _sma(close, 50)
        atr_14 = _atr(high, low, close, 14)
        bb_upper, bb_middle, bb_lower = _bbands(close, 20, 2.0)
        vol_ma_20 = _volume_ma(volume, 20)

        for name in names:
            if name in self.BUILT_IN:
                try:
                    if name == "bb_upper":
                        features[name] = bb_upper
                    elif name == "bb_middle":
                        features[name] = bb_middle
                    elif name == "bb_lower":
                        features[name] = bb_lower
                    elif name == "bb_width":
                        features[name] = np.where(bb_middle != 0, (bb_upper - bb_lower) / bb_middle, np.nan)
                    elif name == "rsi_14":
                        features[name] = rsi_14
                    elif name == "sma_20":
                        features[name] = sma_20
                    elif name == "sma_50":
                        features[name] = sma_50
                    elif name == "atr_14":
                        features[name] = atr_14
                    elif name == "atr_14_pct":
                        features[name] = np.where(close != 0, atr_14 / close, np.nan)
                    elif name == "atr_rank_20":
                        features[name] = _atr_rank(atr_14, 20)
                    elif name == "price_vs_sma_20":
                        features[name] = np.where(sma_20 != 0, (close - sma_20) / sma_20, np.nan)
                    elif name == "price_vs_sma_50":
                        features[name] = np.where(sma_50 != 0, (close - sma_50) / sma_50, np.nan)
                    elif name == "volume_ma_20":
                        features[name] = vol_ma_20
                    elif name == "volume_zscore_20":
                        features[name] = _volume_zscore(volume, 20)
                    elif name == "momentum_5d":
                        features[name] = _momentum(close, 5)
                    elif name == "momentum_20d":
                        features[name] = _momentum(close, 20)
                    else:
                        # Generic call via lambda
                        features[name] = self.BUILT_IN[name](open_, high, low, close, volume)
                except Exception as exc:
                    logger.warning("Feature %s failed: %s", name, exc)
                    features[name] = np.full_like(close, np.nan)
            elif name in self.custom:
                try:
                    features[name] = self._eval_formula(
                        self.custom[name], open_, high, low, close, volume
                    )
                except Exception as exc:
                    logger.warning("Custom feature %s failed: %s", name, exc)
                    features[name] = np.full_like(close, np.nan)
            else:
                logger.warning("Unknown feature: %s", name)
                features[name] = np.full_like(close, np.nan)

        return FeatureSet(ticker=ticker, features=features)

    def _eval_formula(
        self,
        formula: str,
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
    ) -> np.ndarray:
        """Evaluate a custom formula in a restricted namespace.

        Safe because only numpy + math + pre-defined arrays are available.
        No os, sys, subprocess, open, eval, exec.
        """
        namespace = {
            "np": np,
            "math": math,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            # Built-in helpers
            "rsi": _rsi,
            "sma": _sma,
            "ema": _ema,
            "atr": _atr,
            "bbands": _bbands,
            "volume_ma": _volume_ma,
            "volume_zscore": _volume_zscore,
            "momentum": _momentum,
            "atr_rank": _atr_rank,
        }
        result = eval(formula, {"__builtins__": {}}, namespace)
        if not isinstance(result, np.ndarray):
            raise ValueError(f"Formula must return np.ndarray, got {type(result)}")
        if len(result) != len(close):
            raise ValueError(f"Result length {len(result)} != close length {len(close)}")
        return result

    @classmethod
    def list_built_in(cls) -> list[str]:
        return list(cls.BUILT_IN.keys())


# ── Batch computation ─────────────────────────────────────────────────────────


def compute_features_for_tickers(
    ticker_data: dict[str, dict[str, np.ndarray]],
    feature_names: list[str] | None = None,
    custom_features: dict[str, str] | None = None,
) -> dict[str, FeatureSet]:
    """Compute features for multiple tickers at once.

    ticker_data: dict of ticker -> {"open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}
    Returns: dict of ticker -> FeatureSet
    """
    engine = FeatureEngine(custom_features=custom_features)
    results: dict[str, FeatureSet] = {}
    for ticker, data in ticker_data.items():
        fs = engine.compute(
            ticker=ticker,
            open_=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            feature_names=feature_names,
        )
        results[ticker] = fs
    return results
