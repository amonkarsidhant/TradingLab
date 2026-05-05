#!/usr/bin/env python3
"""Local ATR shape trace — verify the math before pushing."""
import sys
sys.path.insert(0, '/Users/sidhantamonkar/Documents/Projects/sid-trading-lab/src')

import numpy as np

# ── Exact helpers from features.py (current code) ─────────────────────────

def _sma(arr, window):
    if len(arr) < window:
        return np.full_like(arr, np.nan)
    cumsum = np.cumsum(np.insert(arr, 0, 0))
    raw = (cumsum[window:] - cumsum[:-window]) / window
    padded = np.full_like(arr, np.nan)
    padded[window - 1:] = raw
    return padded

# Current broken code (VPS has this)
def _atr_broken(high, low, close, window=14):
    if len(close) < window + 2:
        return np.full_like(close, np.nan)
    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    atr = _sma(tr, window)
    padded = np.full_like(close, np.nan)
    valid_start = window - 1
    valid_count = len(tr) - valid_start
    if valid_count > 0:
        padded[window : window + valid_count] = atr[valid_start : valid_start + valid_count]
    return padded

# Correct code
def _atr_fixed(high, low, close, window=14):
    if len(close) < window + 2:
        return np.full_like(close, np.nan)
    tr1 = high[1:] - low[1:]
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    tr = np.maximum(np.maximum(tr1, tr2), tr3)
    atr = _sma(tr, window)  # len(tr), valid from index (window-1)
    padded = np.full_like(close, np.nan)
    # Math proof:
    #   len(tr) = len(close) - 1
    #   valid = atr[window-1:] → length = len(tr)-(window-1) = len(close)-window
    #   dest  = padded[window:]  → length = len(close)-window
    #   → EXACT MATCH
    valid = atr[window - 1:]
    if len(valid) > 0:
        padded[window:window + len(valid)] = valid
    return padded

# ── Test ───────────────────────────────────────────────────────────────────

np.random.seed(42)
close   = np.arange(100.0, 130.0) + np.random.normal(0, 0.5, 30)
h       = close * 1.01
l       = close * 0.98

print(f"close length: {len(close)}")

tr = np.maximum(np.maximum(
    h[1:] - l[1:], np.abs(h[1:] - close[:-1])), np.abs(l[1:] - close[:-1]))
print(f"tr length:  {len(tr)}")

atr_sma = _sma(tr, 14)
print(f"atr length: {len(atr_sma)}  (same as tr because _sma pads)")
print(f"valid start: {14-1}, valid values: {len(atr_sma)-(14-1)}")
print(f"dest slots:  padded[{14}:{14}+{len(atr_sma)-(14-1)}] = {len(close)-14} slots")
print(f"match: {len(atr_sma)-(14-1) == len(close)-14}")

print("\n--- BROKEN ---")
try:
    r = _atr_broken(h, l, close, 14)
    print(f"OK, len={len(r)}, nans={np.sum(np.isnan(r))}")
except Exception as e:
    print(f"FAIL: {e}")

print("\n--- FIXED ---")
try:
    r = _atr_fixed(h, l, close, 14)
    print(f"OK, len={len(r)}, nans={np.sum(np.isnan(r))}")
    print(f"first non-nan: index {np.where(~np.isnan(r))[0][0]}")
    print(f"last value: {r[-1]:.4f}")
except Exception as e:
    print(f"FAIL: {e}")

# Quick simulation trace: 30-bar close array
print("\n--- Simulation scenario (100 bars) ---")
close100 = np.cumsum(np.random.randn(100)) + 100
for w in [14, 20]:
    r = _atr_fixed(close100*1.01, close100*0.98, close100, w)
    print(f"window={w}: len={len(r)}, nans={np.sum(np.isnan(r))}, first_valid={np.where(~np.isnan(r))[0][0] if np.any(~np.isnan(r)) else 'none'}")
