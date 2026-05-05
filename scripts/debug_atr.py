"""Trace _atr shape mismatch — local debug script."""
import numpy as np

# ── Reproduce the exact helpers from features.py ──────────────────────────

def _sma(arr, window):
    if len(arr) < window:
        return np.full_like(arr, np.nan)
    cumsum = np.cumsum(np.insert(arr, 0, 0))
    raw = (cumsum[window:] - cumsum[:-window]) / window
    padded = np.full_like(arr, np.nan)
    padded[window - 1:] = raw
    return padded

def _atr_v1(high, low, close, window=14):  # current code on VPS
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

# ── Test with the exact array that fails ─────────────────────────────────

np.random.seed(42)
close = np.arange(100.0, 130.0) + np.random.normal(0, 0.5, 30)
open_ = close * 0.99
high = close * 1.01
low = close * 0.98

print(f"close length: {len(close)}")

tr1 = high[1:] - low[1:]
print(f"tr1 length: {len(tr1)}")

test_window = 14
print(f"\n--- window={test_window} ---")
print(f"len(close)={len(close)}, window+2={test_window+2}")
print(f"len(tr)={len(tr1)}, valid_start={test_window-1}, valid_count={len(tr1)-(test_window-1)}")

try:
    result = _atr_v1(high, low, close, test_window)
    print(f"Result length: {len(result)}, NaN count: {np.sum(np.isnan(result))}")
    print("OK")
except Exception as e:
    print(f"FAIL: {e}")

# ── Trace the exact shapes step by step ──────────────────────────────────

print("\n=== Detailed trace ===")
tr = np.maximum(np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1])), np.abs(low[1:] - close[:-1]))
print(f"tr shape: {tr.shape}")

atr = _sma(tr, test_window)
print(f"atr shape: {atr.shape}")
print(f"atr[0:5]: {atr[0:5]}")
print(f"atr NaN mask first 20: {np.isnan(atr[:20])}")

# What we need: padded array of len(close)=30, with valid ATR values starting at some index
# _sma(tr, 14) pads to len(tr)=29, valid from index 13
# So valid atr indices: 13..28  (16 values)
# We want them in padded[14..29] but padded only has 30 elements, so index 29 is last
# That means: padded[14:30] gets atr[13:29] — 16 values into 16 slots

print(f"\nManual alignment check:")
print(f"  atr[13:29] shape: {atr[13:29].shape}")
print(f"  padded[14:30] shape: {np.full_like(close, np.nan)[14:30].shape}")

# So the correct slice should be: padded[window : window + (len(tr) - (window-1))] = atr[window-1 :]
# Let's verify: window=14, len(tr)=29
# padded[14 : 14 + (29-13)] = padded[14:30] = 16 slots
# atr[13:] = 16 values
# MATCH!

print("\n=== Correct formula ===")
print(f"padded[{test_window} : {test_window} + {len(tr) - (test_window-1)}] = atr[{test_window-1}:]")
print(f"padded[{test_window}:{test_window + len(tr) - (test_window-1)}]  ({len(tr) - (test_window-1)} slots)")
print(f"atr[{test_window-1}:]  ({len(atr) - (test_window-1)} values)")
print(f"Slots == Values? {len(tr) - (test_window-1) == len(atr) - (test_window-1)}")
