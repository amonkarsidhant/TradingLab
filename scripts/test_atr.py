import numpy as np
from trading_lab.alpha.features import _atr

np.random.seed(42)
close = np.arange(100.0, 130.0) + np.random.normal(0, 0.5, 30)
h = close * 1.01
l = close * 0.98

r = _atr(h, l, close, 14)
print("len=%d, nans=%d, last=%.4f" % (len(r), np.sum(np.isnan(r)), r[-1]))
print("first_valid=%d" % np.where(~np.isnan(r))[0][0])
print("OK")
