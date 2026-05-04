"""
Market data abstraction for Sid Trading Lab.

IMPORTANT: Trading 212 does not expose a general OHLC / candle historical
price endpoint. The Trading 212 API is used here only as the broker and
account API. Market price data must come from a separate source.

Current sources supported:
  static   — fixed deterministic prices for offline testing and CI
  csv      — local CSV file: data/market/prices/{ticker}.csv
  yfinance — free Yahoo Finance data (OHLCV + cache)
  chained  — tries yfinance → CSV → static in order (auto-fallback)

Strategies must never call broker or data APIs directly.
They receive price lists from a MarketDataProvider.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import pandas as pd

from trading_lab.data.price_cache import SqlitePriceCache
from trading_lab.brokers.trading212 import _t212_ticker_to_yf

logger = logging.getLogger(__name__)


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


# ── YFinanceMarketDataProvider ─────────────────────────────────────────────────

class YFinanceMarketDataProvider:
    """Fetches daily OHLCV bars from Yahoo Finance via the yfinance library.

    Closes are extracted and returned as a list[float] via get_prices()
    for strategy compatibility.  Raw OHLCV DataFrames are available via
    get_ohlcv() for the backtest engine and other consumers that need
    full bar data.

    Results are cached in a local SQLite database so repeated queries
    for the same ticker never hit the network.
    """

    def __init__(self, cache: SqlitePriceCache | None = None) -> None:
        self._cache = cache or SqlitePriceCache("./trading_lab_cache.sqlite3")

    def get_prices(self, ticker: str, lookback: int) -> list[float]:
        df = self._fetch(ticker, lookback)
        if df.empty:
            return []
        closes: list[float] = df["close"].tolist()
        n = lookback + 1
        return closes[-n:] if len(closes) >= n else closes

    def get_ohlcv(self, ticker: str, lookback: int) -> pd.DataFrame:
        """Return full OHLCV DataFrame for the given lookback window."""
        return self._fetch(ticker, lookback)

    def _fetch(self, ticker: str, lookback: int) -> pd.DataFrame:
        import yfinance as yf

        # Request more history than lookback so we have buffer for weekends.
        # yfinance uses start/end dates; we over-request by 2× to be safe.
        end = pd.Timestamp.today(tz="UTC")
        start = end - pd.Timedelta(days=lookback * 4 + 14)

        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        # Check cache first.
        cached = self._cache.get(ticker, start_str, end_str)
        if cached and len(cached) >= lookback + 1:
            logger.debug("Price cache hit for %s (%d rows)", ticker, len(cached))
            return pd.DataFrame(cached)[["date", "open", "high", "low", "close", "volume"]]

        yf_symbol = _t212_ticker_to_yf(ticker)
        logger.info("Fetching %s from Yahoo Finance (yf: %s, %s → %s)", ticker, yf_symbol, start_str, end_str)
        try:
            raw: pd.DataFrame = yf.download(
                yf_symbol, start=start_str, end=end_str, progress=False, auto_adjust=True
            )
        except Exception as exc:
            logger.warning("yfinance download failed for %s: %s", ticker, exc)
            return pd.DataFrame()

        if raw.empty:
            return pd.DataFrame()

        # yfinance returns a MultiIndex DataFrame; flatten it.
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        df = raw.reset_index()
        df.columns = [c.lower() for c in df.columns]
        col_map = {c: c for c in df.columns}
        df = df.rename(columns=col_map)

        # Normalise column names.
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = float("nan")

        # Cache every bar individually.
        bars: list[dict] = []
        for _, row in df.iterrows():
            d = row.get("date", row.get("Date", None))
            if d is None:
                continue
            bars.append({
                "date": str(pd.Timestamp(d).date()),
                "open": float(row.get("open", float("nan"))),
                "high": float(row.get("high", float("nan"))),
                "low": float(row.get("low", float("nan"))),
                "close": float(row.get("close", float("nan"))),
                "volume": float(row.get("volume", 0)),
            })
        if bars:
            self._cache.put(ticker, bars)

        out_cols = ["date", "open", "high", "low", "close", "volume"]
        return pd.DataFrame(bars)[[c for c in out_cols if c in pd.DataFrame(bars).columns]]


# ── ChainedMarketDataProvider ──────────────────────────────────────────────────

class ChainedMarketDataProvider:
    """Tries providers in order. The first one that returns data wins.

    Providers are tried in sequence:
      1. yfinance (network + local cache)
      2. CSV (local file)
      3. static (deterministic, always works)
    """

    def __init__(self, providers: list[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("At least one provider is required.")
        self._providers = providers

    def get_prices(self, ticker: str, lookback: int) -> list[float]:
        for i, provider in enumerate(self._providers):
            try:
                prices = provider.get_prices(ticker, lookback)
                if prices:
                    return prices
            except Exception:
                if i == len(self._providers) - 1:
                    raise
                logger.debug("Provider %d failed, trying next", i + 1, exc_info=True)
        return []


# ── Factory ────────────────────────────────────────────────────────────────────

def make_provider(
    source: str,
    ticker: str = "",
    prices_file: str = "",
    cache_db: str = "",
) -> MarketDataProvider:
    """Build a MarketDataProvider from a source name.

    Sources:
      static   — offline deterministic prices
      csv      — local CSV file
      yfinance — Yahoo Finance with SQLite cache
      chained  — yfinance → csv → static (auto-fallback)
    """
    if source == "static":
        return StaticMarketDataProvider()

    if source == "csv":
        path = prices_file or f"data/market/prices/{ticker}.csv"
        return CsvMarketDataProvider(path)

    if source == "yfinance":
        cache = SqlitePriceCache(cache_db or "./trading_lab_cache.sqlite3")
        return YFinanceMarketDataProvider(cache=cache)

    if source == "chained":
        cache = SqlitePriceCache(cache_db or "./trading_lab_cache.sqlite3")
        return ChainedMarketDataProvider([
            YFinanceMarketDataProvider(cache=cache),
            CsvMarketDataProvider(prices_file or f"data/market/prices/{ticker}.csv"),
            StaticMarketDataProvider(),
        ])

    raise ValueError(
        f"Unknown data source '{source}'. Use 'static', 'csv', 'yfinance', or 'chained'."
    )
