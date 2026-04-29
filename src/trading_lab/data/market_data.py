"""
Market data abstraction for Sid Trading Lab.

IMPORTANT: Trading 212 does not expose a general OHLC / candle historical
price endpoint. The Trading 212 API is used here only as the broker and
account API. Market price data must come from a separate source.

Current sources supported:
  static  — fixed deterministic prices for offline testing and CI
  csv     — local CSV file: data/market/prices/{ticker}.csv

Strategies must never call broker or data APIs directly.
They receive price lists from a MarketDataProvider.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd


# ── Protocol ──────────────────────────────────────────────────────────────────

class MarketDataProvider(Protocol):
    """Structural protocol for market data sources.

    Any class that implements get_prices() satisfies this protocol.
    Strategy classes must accept a MarketDataProvider, never a broker client.
    """

    def get_prices(self, ticker: str, lookback: int) -> list[float]:
        """Return the most recent closing prices in chronological order.

        Args:
            ticker:   Instrument identifier, e.g. 'AAPL_US_EQ'.
            lookback: Number of periods the strategy needs for calculation.
                      The provider returns lookback+1 prices so the strategy
                      has both a reference start point and a current end point.

        Returns:
            List of floats, oldest first. May be shorter than lookback+1 if
            insufficient data is available — the strategy will return HOLD.
        """
        ...


# ── StaticMarketDataProvider ──────────────────────────────────────────────────

# Deterministic upward-trending prices. Long enough for lookback up to 10.
_STATIC_PRICES: list[float] = [
    100.0, 101.0, 102.0, 103.0, 104.0,
    106.0, 107.5, 108.0, 109.2, 110.5, 112.0,
]


class StaticMarketDataProvider:
    """Returns a fixed deterministic price series. Ticker is ignored.

    Use for:
    - Offline development (no files or API keys needed)
    - CI pipelines where no external data is available
    - Demonstrating strategy logic in isolation

    Prices are intentionally upward-trending and will produce a BUY signal
    with SimpleMomentumStrategy at default settings (lookback=5, threshold=1%).
    """

    def get_prices(self, ticker: str, lookback: int) -> list[float]:
        n = lookback + 1
        if len(_STATIC_PRICES) >= n:
            return _STATIC_PRICES[-n:]
        return list(_STATIC_PRICES)


# ── CsvMarketDataProvider ─────────────────────────────────────────────────────

class CsvMarketDataProvider:
    """Loads close prices from a local CSV file.

    Expected CSV format
    -------------------
    date,close
    2026-04-20,100.0
    2026-04-21,101.2
    2026-04-22,102.1

    Default file location (when used via CLI):
        data/market/prices/{ticker}.csv

    Rows are sorted by date ascending so the most recent price is last.
    If fewer than lookback+1 rows are available the full list is returned
    and the strategy will emit a HOLD signal.
    """

    def __init__(self, file_path: str) -> None:
        self._file_path = Path(file_path)

    def get_prices(self, ticker: str, lookback: int) -> list[float]:
        if not self._file_path.exists():
            raise FileNotFoundError(
                f"Price file not found: {self._file_path}\n"
                f"Create a CSV with columns 'date,close' at that path.\n"
                f"Example default location: data/market/prices/{ticker}.csv"
            )

        df = pd.read_csv(self._file_path, parse_dates=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        closes: list[float] = df["close"].tolist()

        n = lookback + 1
        return closes[-n:] if len(closes) >= n else closes
