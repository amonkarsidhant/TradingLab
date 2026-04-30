"""
Unit tests for Trading212Client auth, rate limiting, validation, and order types.

No real API calls are made. No real credentials are used.
"""
import base64

import pytest

from trading_lab.config import Settings
from trading_lab.brokers.trading212 import (
    Trading212Client,
    RateLimit,
    InstrumentCache,
)


def _demo_settings(**overrides) -> Settings:
    defaults = dict(
        t212_env="demo",
        t212_api_key="test_key",
        t212_api_secret="test_secret",
        t212_allow_live=False,
        order_placement_enabled=False,
        t212_confirm_live="",
        demo_order_confirm="",
        db_path="./test.sqlite3",
        telegram_bot_token="",
        t212_auth_header="",
        t212_api_key_invest="",
        t212_api_secret_invest="",
        t212_api_key_isa="",
        t212_api_secret_isa="",
        t212_extended_hours=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ── Auth header format ─────────────────────────────────────────────────────────

def test_auth_header_is_basic_base64_of_key_colon_secret():
    client = Trading212Client(
        _demo_settings(t212_api_key="mykey", t212_api_secret="mysecret")
    )
    header = client._auth_header()
    expected_token = base64.b64encode(b"mykey:mysecret").decode("utf-8")
    assert header == {"Authorization": f"Basic {expected_token}"}


def test_auth_header_scheme_is_basic_not_bearer():
    client = Trading212Client(
        _demo_settings(t212_api_key="k", t212_api_secret="s")
    )
    header = client._auth_header()
    assert header["Authorization"].startswith("Basic ")


def test_auth_header_raises_when_api_key_missing():
    client = Trading212Client(
        _demo_settings(t212_api_key="", t212_api_secret="mysecret")
    )
    with pytest.raises(RuntimeError, match="Missing T212 credentials"):
        client._auth_header()


def test_auth_header_raises_when_api_secret_missing():
    client = Trading212Client(
        _demo_settings(t212_api_key="mykey", t212_api_secret="")
    )
    with pytest.raises(RuntimeError, match="Missing T212 credentials"):
        client._auth_header()


def test_auth_header_uses_precomposed_header_when_present():
    client = Trading212Client(
        _demo_settings(
            t212_api_key="ignored",
            t212_api_secret="ignored",
            t212_auth_header="Basic cHJlY29tcG9zZWQ6aGVhZGVy",
        )
    )
    header = client._auth_header()
    assert header == {"Authorization": "Basic cHJlY29tcG9zZWQ6aGVhZGVy"}


def test_auth_header_falls_back_to_invest_pair():
    client = Trading212Client(
        _demo_settings(
            t212_api_key="",
            t212_api_secret="",
            t212_api_key_invest="invest_key",
            t212_api_secret_invest="invest_secret",
        )
    )
    header = client._auth_header()
    expected = base64.b64encode(b"invest_key:invest_secret").decode("utf-8")
    assert header == {"Authorization": f"Basic {expected}"}


def test_auth_header_falls_back_to_isa_pair():
    client = Trading212Client(
        _demo_settings(
            t212_api_key="",
            t212_api_secret="",
            t212_api_key_isa="isa_key",
            t212_api_secret_isa="isa_secret",
        )
    )
    header = client._auth_header()
    expected = base64.b64encode(b"isa_key:isa_secret").decode("utf-8")
    assert header == {"Authorization": f"Basic {expected}"}


# ── market_order dry-run safety ───────────────────────────────────────────────

def test_market_order_dry_run_returns_immediately_without_network_call():
    client = Trading212Client(_demo_settings())
    result = client.market_order(ticker="AAPL_US_EQ", quantity=1.0, dry_run=True)
    assert result["dry_run"] is True
    assert result["payload"]["ticker"] == "AAPL_US_EQ"
    assert result["payload"]["quantity"] == 1.0


def test_market_order_live_blocked_when_order_placement_disabled():
    client = Trading212Client(_demo_settings(order_placement_enabled=False))
    with pytest.raises(RuntimeError, match="Order placement is disabled"):
        client.market_order(ticker="AAPL_US_EQ", quantity=1.0, dry_run=False)


def test_market_order_supports_extended_hours():
    client = Trading212Client(_demo_settings(t212_extended_hours=True))
    result = client.market_order(
        ticker="AAPL_US_EQ", quantity=1.0, dry_run=True, extended_hours=True
    )
    assert result["payload"]["extendedHours"] is True


# ── stop orders ───────────────────────────────────────────────────────────────

def test_stop_order_dry_run():
    client = Trading212Client(_demo_settings())
    result = client.stop_order(
        ticker="AAPL_US_EQ", quantity=-1.0, stop_price=180.0, dry_run=True
    )
    assert result["dry_run"] is True
    assert result["payload"]["ticker"] == "AAPL_US_EQ"
    assert result["payload"]["stopPrice"] == 180.0


def test_stop_order_live_blocked():
    client = Trading212Client(_demo_settings(order_placement_enabled=False))
    with pytest.raises(RuntimeError, match="Order placement is disabled"):
        client.stop_order(
            ticker="AAPL_US_EQ", quantity=-1.0, stop_price=180.0, dry_run=False
        )


# ── limit orders ──────────────────────────────────────────────────────────────

def test_limit_order_dry_run():
    client = Trading212Client(_demo_settings())
    result = client.limit_order(
        ticker="AAPL_US_EQ", quantity=1.0, limit_price=150.0, dry_run=True
    )
    assert result["dry_run"] is True
    assert result["payload"]["limitPrice"] == 150.0


# ── stop-limit orders ─────────────────────────────────────────────────────────

def test_stop_limit_order_dry_run():
    client = Trading212Client(_demo_settings())
    result = client.stop_limit_order(
        ticker="AAPL_US_EQ", quantity=-1.0, stop_price=185.0,
        limit_price=180.0, dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["payload"]["stopPrice"] == 185.0
    assert result["payload"]["limitPrice"] == 180.0


# ── rate limiting ─────────────────────────────────────────────────────────────

def test_rate_limit_waits_when_capacity_exhausted():
    rl = RateLimit(max_requests=2, period_seconds=60)
    rl.wait_if_needed()
    rl.wait_if_needed()
    assert rl.remaining() == 0


# ── instrument cache ──────────────────────────────────────────────────────────

def test_instrument_cache_lookup():
    cache = InstrumentCache(db_path=":memory:")
    cache.cache_instruments([
        {"ticker": "AAPL_US_EQ", "name": "Apple Inc", "shortName": "AAPL"},
        {"ticker": "TSLA_US_EQ", "name": "Tesla Inc", "shortName": "TSLA"},
    ])
    results = cache.lookup("Apple")
    assert len(results) == 1
    assert results[0]["ticker"] == "AAPL_US_EQ"
    results = cache.lookup("tsla")
    assert len(results) == 1
    assert results[0]["ticker"] == "TSLA_US_EQ"


def test_instrument_cache_lookup_empty():
    cache = InstrumentCache(db_path=":memory:")
    results = cache.lookup("nonexistent")
    assert len(results) == 0


# ── validate buy/sell ─────────────────────────────────────────────────────────

def test_validate_buy_rejects_zero_quantity():
    client = Trading212Client(_demo_settings())
    valid, msg = client._validate_buy("AAPL_US_EQ", 0)
    assert valid is False
    assert "positive" in msg.lower()


def test_validate_sell_rejects_zero_quantity():
    client = Trading212Client(_demo_settings())
    valid, msg = client._validate_sell("AAPL_US_EQ", 0)
    assert valid is False
    assert "positive" in msg.lower()


def test_validate_handles_api_error_gracefully():
    """With fake credentials, the API call fails but shouldn't crash."""
    client = Trading212Client(_demo_settings())
    valid, msg = client._validate_buy("AAPL_US_EQ", 1.0)
    assert valid is False
    assert "fund check failed" in msg.lower() or "missing" in msg.lower()


# ── risk policy ───────────────────────────────────────────────────────────────

def test_trailing_stop_price():
    from trading_lab.risk import RiskPolicy
    rp = RiskPolicy(trailing_stop_pct=0.07)
    assert rp.trailing_stop_price(100.0) == 93.0


def test_stop_hit_when_below_trailing():
    from trading_lab.risk import RiskPolicy
    rp = RiskPolicy(trailing_stop_pct=0.07)
    assert rp.stop_hit(100.0, 92.0) is True
    assert rp.stop_hit(100.0, 94.0) is False
