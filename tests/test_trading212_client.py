"""
Unit tests for Trading212Client auth header construction and dry-run safety.

No real API calls are made. No real credentials are used.
The client is constructed with placeholder values against the demo URL.

Auth format confirmed: HTTP Basic Auth with base64(API_KEY:API_SECRET).
See docs/trading212-agent-skills-analysis.md §5b.
"""
import base64

import pytest

from trading_lab.config import Settings
from trading_lab.brokers.trading212 import Trading212Client


def _demo_settings(**overrides) -> Settings:
    """Return a safe demo Settings object. Override fields as needed per test."""
    defaults = dict(
        t212_env="demo",
        t212_api_key="test_key",
        t212_api_secret="test_secret",
        t212_allow_live=False,
        order_placement_enabled=False,
        t212_confirm_live="",
        db_path="./test.sqlite3",
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ── Auth header format ─────────────────────────────────────────────────────────

def test_auth_header_is_basic_base64_of_key_colon_secret():
    """_auth_header() must produce Authorization: Basic <base64(key:secret)>.

    This is the format confirmed by the official Trading 212 REST API docs.
    """
    client = Trading212Client(
        _demo_settings(t212_api_key="mykey", t212_api_secret="mysecret")
    )

    header = client._auth_header()

    expected_token = base64.b64encode(b"mykey:mysecret").decode("utf-8")
    assert header == {"Authorization": f"Basic {expected_token}"}


def test_auth_header_scheme_is_basic_not_bearer():
    """The Authorization scheme must be 'Basic', not 'Bearer' or a bare token."""
    client = Trading212Client(
        _demo_settings(t212_api_key="k", t212_api_secret="s")
    )

    header = client._auth_header()

    assert header["Authorization"].startswith("Basic ")


def test_auth_header_raises_when_api_key_missing():
    """_auth_header() must raise RuntimeError if T212_API_KEY is empty."""
    client = Trading212Client(
        _demo_settings(t212_api_key="", t212_api_secret="mysecret")
    )

    with pytest.raises(RuntimeError, match="Missing T212_API_KEY"):
        client._auth_header()


def test_auth_header_raises_when_api_secret_missing():
    """_auth_header() must raise RuntimeError if T212_API_SECRET is empty."""
    client = Trading212Client(
        _demo_settings(t212_api_key="mykey", t212_api_secret="")
    )

    with pytest.raises(RuntimeError, match="Missing T212_API_KEY"):
        client._auth_header()


# ── market_order dry-run safety ───────────────────────────────────────────────

def test_market_order_dry_run_returns_immediately_without_network_call():
    """market_order(dry_run=True) must return a dict and never call the API."""
    client = Trading212Client(_demo_settings())

    result = client.market_order(ticker="AAPL_US_EQ", quantity=1.0, dry_run=True)

    assert result["dry_run"] is True
    assert result["payload"]["ticker"] == "AAPL_US_EQ"
    assert result["payload"]["quantity"] == 1.0


def test_market_order_live_blocked_when_order_placement_disabled():
    """market_order(dry_run=False) must raise RuntimeError when can_place_orders is False."""
    client = Trading212Client(_demo_settings(order_placement_enabled=False))

    with pytest.raises(RuntimeError, match="Order placement is disabled"):
        client.market_order(ticker="AAPL_US_EQ", quantity=1.0, dry_run=False)
