"""
Tests for market data providers.

No network calls. No API keys. No Trading 212 API usage.
CSV tests use pytest's tmp_path fixture for throwaway files.
YFinance-like tests use in-memory SQLite cache — no real network calls.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from trading_lab.data.market_data import (
    ChainedMarketDataProvider,
    CsvMarketDataProvider,
    StaticMarketDataProvider,
    make_provider,
)
from trading_lab.data.price_cache import SqlitePriceCache
from trading_lab.models import SignalAction
from trading_lab.strategies.simple_momentum import SimpleMomentumStrategy


# ── Helpers ───────────────────────────────────────────────────────────────────

def write_csv(path: Path, rows: list[tuple[str, float]]) -> None:
    lines = ["date,close"] + [f"{d},{c}" for d, c in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── StaticMarketDataProvider ──────────────────────────────────────────────────

def test_static_provider_returns_deterministic_prices():
    """Same lookback must always return identical prices regardless of ticker."""
    provider = StaticMarketDataProvider()
    prices_a = provider.get_prices("AAPL_US_EQ", lookback=5)
    prices_b = provider.get_prices("TSLA_US_EQ", lookback=5)
    assert prices_a == prices_b


def test_static_provider_returns_lookback_plus_one_prices():
    """Provider must return exactly lookback+1 prices."""
    provider = StaticMarketDataProvider()
    for lookback in [3, 5, 7]:
        prices = provider.get_prices("TEST", lookback=lookback)
        assert len(prices) == lookback + 1, (
            f"Expected {lookback + 1} prices for lookback={lookback}, got {len(prices)}"
        )


def test_static_provider_returns_floats():
    """All returned values must be Python floats."""
    provider = StaticMarketDataProvider()
    prices = provider.get_prices("AAPL_US_EQ", lookback=5)
    assert all(isinstance(p, float) for p in prices)


def test_static_provider_prices_are_in_ascending_order():
    """Static prices must be ordered oldest-first (chronological)."""
    provider = StaticMarketDataProvider()
    prices = provider.get_prices("TEST", lookback=5)
    assert prices == sorted(prices)


def test_static_provider_produces_buy_signal_with_momentum_strategy():
    """Static prices are upward-trending — SimpleMomentumStrategy must emit BUY."""
    provider = StaticMarketDataProvider()
    prices = provider.get_prices("AAPL_US_EQ", lookback=5)

    signal = SimpleMomentumStrategy(lookback=5).generate_signal("AAPL_US_EQ", prices)

    assert signal.action == SignalAction.BUY


# ── CsvMarketDataProvider ─────────────────────────────────────────────────────

def test_csv_provider_loads_close_prices(tmp_path):
    """Provider must read close prices from a well-formed CSV."""
    csv_file = tmp_path / "AAPL_US_EQ.csv"
    write_csv(csv_file, [
        ("2026-04-20", 100.0),
        ("2026-04-21", 101.5),
        ("2026-04-22", 103.0),
    ])

    provider = CsvMarketDataProvider(str(csv_file))
    prices = provider.get_prices("AAPL_US_EQ", lookback=2)

    assert prices == [100.0, 101.5, 103.0]


def test_csv_provider_sorts_rows_by_date_ascending(tmp_path):
    """Rows in arbitrary date order must be sorted oldest-first on load."""
    csv_file = tmp_path / "TEST.csv"
    write_csv(csv_file, [
        ("2026-04-22", 103.0),
        ("2026-04-20", 100.0),
        ("2026-04-21", 101.5),
    ])

    provider = CsvMarketDataProvider(str(csv_file))
    prices = provider.get_prices("TEST", lookback=2)

    assert prices == [100.0, 101.5, 103.0]


def test_csv_provider_returns_only_last_lookback_plus_one_rows(tmp_path):
    """With more rows than needed, return only the most recent lookback+1."""
    csv_file = tmp_path / "TEST.csv"
    write_csv(csv_file, [(f"2026-04-{i:02d}", float(100 + i)) for i in range(1, 11)])

    provider = CsvMarketDataProvider(str(csv_file))
    prices = provider.get_prices("TEST", lookback=5)

    assert len(prices) == 6
    assert prices[-1] == pytest.approx(110.0)  # most recent date


def test_csv_provider_returns_all_prices_when_fewer_than_needed(tmp_path):
    """Insufficient rows must return all available; strategy will emit HOLD."""
    csv_file = tmp_path / "TEST.csv"
    write_csv(csv_file, [
        ("2026-04-20", 100.0),
        ("2026-04-21", 101.0),
    ])

    provider = CsvMarketDataProvider(str(csv_file))
    prices = provider.get_prices("TEST", lookback=5)

    assert prices == [100.0, 101.0]  # only 2 rows available, need 6


def test_csv_provider_raises_file_not_found_with_clear_message():
    """Missing CSV file must raise FileNotFoundError with a helpful message."""
    provider = CsvMarketDataProvider("/nonexistent/path/MISSING.csv")

    with pytest.raises(FileNotFoundError, match="Price file not found"):
        provider.get_prices("MISSING", lookback=5)


def test_csv_provider_with_strategy_produces_buy_signal(tmp_path):
    """End-to-end: CsvMarketDataProvider feeds upward prices into strategy → BUY.
    No network calls. No API credentials."""
    csv_file = tmp_path / "AAPL_US_EQ.csv"
    write_csv(csv_file, [
        ("2026-04-15", 100.0),
        ("2026-04-16", 101.0),
        ("2026-04-17", 102.0),
        ("2026-04-18", 104.0),
        ("2026-04-21", 106.0),
        ("2026-04-22", 108.0),
    ])

    provider = CsvMarketDataProvider(str(csv_file))
    prices = provider.get_prices("AAPL_US_EQ", lookback=5)

    signal = SimpleMomentumStrategy(lookback=5).generate_signal("AAPL_US_EQ", prices)

    assert signal.action == SignalAction.BUY


def test_csv_provider_with_strategy_produces_hold_when_insufficient_data(tmp_path):
    """Fewer rows than lookback+1 must result in HOLD from the strategy."""
    csv_file = tmp_path / "AAPL_US_EQ.csv"
    write_csv(csv_file, [
        ("2026-04-21", 100.0),
        ("2026-04-22", 101.0),
    ])

    provider = CsvMarketDataProvider(str(csv_file))
    prices = provider.get_prices("AAPL_US_EQ", lookback=5)

    signal = SimpleMomentumStrategy(lookback=5).generate_signal("AAPL_US_EQ", prices)

    assert signal.action == SignalAction.HOLD
    assert "Not enough price data" in signal.reason


# ── SqlitePriceCache ──────────────────────────────────────────────────────────

def test_cache_init_creates_table(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    cache = SqlitePriceCache(db)
    cache.put("TEST", [
        {"date": "2026-04-20", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0},
    ])
    # init was called in constructor; put succeeded → table exists.


def test_cache_put_and_get(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    cache = SqlitePriceCache(db)
    bars = [
        {"date": "2026-04-20", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1000},
        {"date": "2026-04-21", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 1100},
    ]
    cache.put("AAPL_US_EQ", bars)

    result = cache.get("AAPL_US_EQ", "2026-04-20", "2026-04-21")
    assert len(result) == 2
    assert result[0]["close"] == 101.0
    assert result[1]["close"] == 102.0


def test_cache_get_filters_by_date_range(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    cache = SqlitePriceCache(db)
    cache.put("TEST", [
        {"date": "2026-04-20", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0},
        {"date": "2026-04-21", "open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "volume": 0},
        {"date": "2026-04-22", "open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "volume": 0},
    ])

    result = cache.get("TEST", "2026-04-21", "2026-04-21")
    assert len(result) == 1
    assert result[0]["date"] == "2026-04-21"


def test_cache_last_date_returns_none_for_missing_ticker(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    cache = SqlitePriceCache(db)
    assert cache.last_date("MISSING") is None


def test_cache_last_date_returns_max_date(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    cache = SqlitePriceCache(db)
    cache.put("TEST", [
        {"date": "2026-04-20", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0},
        {"date": "2026-04-22", "open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "volume": 0},
    ])
    assert cache.last_date("TEST") == "2026-04-22"


def test_cache_put_overwrites_existing(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    cache = SqlitePriceCache(db)
    cache.put("TEST", [
        {"date": "2026-04-20", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0},
    ])
    cache.put("TEST", [
        {"date": "2026-04-20", "open": 999.0, "high": 999.0, "low": 999.0, "close": 999.0, "volume": 0},
    ])
    result = cache.get("TEST", "2026-04-20", "2026-04-20")
    assert len(result) == 1
    assert result[0]["close"] == 999.0


# ── ChainedMarketDataProvider ─────────────────────────────────────────────────

def test_chained_provider_tries_first_provider(tmp_path):
    """If the first provider returns data, use it."""
    csv_file = tmp_path / "TEST.csv"
    write_csv(csv_file, [
        ("2026-04-20", 100.0),
        ("2026-04-21", 101.0),
        ("2026-04-22", 102.0),
    ])

    chained = ChainedMarketDataProvider([
        CsvMarketDataProvider(str(csv_file)),
        StaticMarketDataProvider(),
    ])
    prices = chained.get_prices("TEST", lookback=2)
    assert prices == [100.0, 101.0, 102.0]


def test_chained_provider_falls_back_on_failure(tmp_path):
    """If the first provider fails, try the next."""
    chained = ChainedMarketDataProvider([
        CsvMarketDataProvider(str(tmp_path / "MISSING.csv")),
        StaticMarketDataProvider(),
    ])
    prices = chained.get_prices("TEST", lookback=2)
    assert len(prices) == 3
    assert isinstance(prices[0], float)


def test_chained_provider_requires_at_least_one():
    with pytest.raises(ValueError, match="At least one"):
        ChainedMarketDataProvider([])


# ── make_provider factory ─────────────────────────────────────────────────────

def test_make_provider_static():
    p = make_provider("static")
    assert isinstance(p, StaticMarketDataProvider)


def test_make_provider_csv(tmp_path):
    csv_file = tmp_path / "TEST.csv"
    write_csv(csv_file, [("2026-04-20", 100.0), ("2026-04-21", 101.0)])
    p = make_provider("csv", ticker="TEST", prices_file=str(csv_file))
    assert isinstance(p, CsvMarketDataProvider)


def test_make_provider_csv_defaults_path_from_ticker():
    p = make_provider("csv", ticker="AAPL_US_EQ")
    assert isinstance(p, CsvMarketDataProvider)


def test_make_provider_yfinance(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    p = make_provider("yfinance", cache_db=db)
    from trading_lab.data.market_data import YFinanceMarketDataProvider
    assert isinstance(p, YFinanceMarketDataProvider)


def test_make_provider_chained(tmp_path):
    db = str(tmp_path / "cache.sqlite3")
    p = make_provider("chained", cache_db=db)
    assert isinstance(p, ChainedMarketDataProvider)


def test_make_provider_unknown_raises():
    with pytest.raises(ValueError, match="Unknown data source"):
        make_provider("bloomberg")
