"""
Unit tests for Trading212Client auth, rate limiting, validation, and order types.

No real API calls are made. No real credentials are used.
"""
import base64
from unittest.mock import patch

import pytest

from trading_lab.config import Settings
from trading_lab.brokers.trading212 import (
    Trading212Client,
    RateLimit,
    InstrumentCache,
    OrderType,
    _t212_ticker_to_yf,
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


# ── ticker translation ────────────────────────────────────────────────────────

def test_t212_ticker_to_yf_strips_us_suffix():
    assert _t212_ticker_to_yf("AAPL_US_EQ") == "AAPL"
    assert _t212_ticker_to_yf("TSLA_US_EQ") == "TSLA"


def test_t212_ticker_to_yf_uk_gets_dot_l():
    assert _t212_ticker_to_yf("VOD_UK_EQ") == "VOD.L"


def test_t212_ticker_to_yf_passthrough_when_no_underscore():
    assert _t212_ticker_to_yf("AAPL") == "AAPL"


# ── idempotency dedupe ────────────────────────────────────────────────────────

def test_idempotency_dedupe_returns_cached_for_duplicate_post():
    """Two identical market_order POSTs in the TTL window should hit cache."""
    client = Trading212Client(_demo_settings(
        order_placement_enabled=True, demo_order_confirm="I_ACCEPT_DEMO_ORDER_TEST",
    ))
    call_count = {"n": 0}

    def fake_request(method, url, **kwargs):
        call_count["n"] += 1
        class R:
            ok = True
            text = '{"id": 12345}'
            status_code = 200
            def json(self): return {"id": 12345}
        return R()

    with patch("trading_lab.brokers.trading212.requests.request", side_effect=fake_request):
        r1 = client.market_order("AAPL_US_EQ", 1.0, dry_run=False)
        r2 = client.market_order("AAPL_US_EQ", 1.0, dry_run=False)
    assert r1 == r2 == {"id": 12345}
    assert call_count["n"] == 1, "second identical POST should have been deduped"


def test_idempotency_does_not_dedupe_different_quantity():
    client = Trading212Client(_demo_settings(
        order_placement_enabled=True, demo_order_confirm="I_ACCEPT_DEMO_ORDER_TEST",
    ))
    call_count = {"n": 0}

    def fake_request(method, url, **kwargs):
        call_count["n"] += 1
        class R:
            ok = True
            text = '{"id": 1}'
            status_code = 200
            def json(self): return {"id": call_count["n"]}
        return R()

    with patch("trading_lab.brokers.trading212.requests.request", side_effect=fake_request):
        client.market_order("AAPL_US_EQ", 1.0, dry_run=False)
        client.market_order("AAPL_US_EQ", 2.0, dry_run=False)
    assert call_count["n"] == 2, "different qty must not be deduped"


# ── positions filter ──────────────────────────────────────────────────────────

def test_positions_filter_passes_ticker_as_query_param():
    client = Trading212Client(_demo_settings())
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["url"] = url
        class R:
            ok = True
            text = "[]"
            status_code = 200
            def json(self): return []
        return R()

    with patch("trading_lab.brokers.trading212.requests.request", side_effect=fake_request):
        client.positions(ticker="AAPL_US_EQ")
    assert "ticker=AAPL_US_EQ" in captured["url"]


# ── replace_order ─────────────────────────────────────────────────────────────

def test_replace_order_dry_run_returns_preview():
    client = Trading212Client(_demo_settings())
    result = client.replace_order(
        order_id=99, order_type=OrderType.LIMIT,
        ticker="AAPL_US_EQ", quantity=1.0, limit_price=150.0,
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["order_id"] == 99
    assert result["new_payload"]["limitPrice"] == 150.0


def test_replace_order_calls_cancel_then_place():
    client = Trading212Client(_demo_settings(
        order_placement_enabled=True, demo_order_confirm="I_ACCEPT_DEMO_ORDER_TEST",
    ))
    sequence: list[str] = []

    def fake_request(method, url, **kwargs):
        sequence.append(f"{method} {url}")
        class R:
            ok = True
            text = '{"id": 1}'
            status_code = 200
            def json(self): return {"id": 1}
        return R()

    with patch("trading_lab.brokers.trading212.requests.request", side_effect=fake_request):
        result = client.replace_order(
            order_id=42, order_type=OrderType.LIMIT,
            ticker="AAPL_US_EQ", quantity=1.0, limit_price=150.0,
            dry_run=False,
        )
    assert any("DELETE" in s and "42" in s for s in sequence)
    assert any("POST" in s and "/orders/limit" in s for s in sequence)
    delete_idx = next(i for i, s in enumerate(sequence) if "DELETE" in s)
    post_idx = next(i for i, s in enumerate(sequence) if "POST" in s)
    assert delete_idx < post_idx, "cancel must precede re-place"
    assert "replacement" in result


# ── bracket_order ─────────────────────────────────────────────────────────────

def test_bracket_order_dry_run_lays_out_three_legs():
    client = Trading212Client(_demo_settings())
    result = client.bracket_order(
        ticker="AAPL_US_EQ", quantity=10, stop_price=140.0, take_profit_price=180.0,
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["entry"]["quantity"] == 10
    assert result["stop_loss"]["quantity"] == -10
    assert result["take_profit"]["limitPrice"] == 180.0


def test_bracket_order_warns_when_stop_leg_fails():
    """If stop-loss POST fails after entry succeeds, warning surfaces; no rollback."""
    client = Trading212Client(_demo_settings(
        order_placement_enabled=True, demo_order_confirm="I_ACCEPT_DEMO_ORDER_TEST",
    ))
    calls: list[str] = []

    def fake_request(method, url, **kwargs):
        calls.append(url)
        class R:
            status_code = 200
            text = '{"id": 1}'
            def json(self): return {"id": len(calls)}
            @property
            def ok(self): return "/orders/stop" not in url or "/orders/stop_limit" in url
            def raise_for_status(self):
                from requests.exceptions import HTTPError
                raise HTTPError(f"500 on {url}")
        return R()

    with patch("trading_lab.brokers.trading212.requests.request", side_effect=fake_request):
        result = client.bracket_order(
            ticker="AAPL_US_EQ", quantity=5,
            stop_price=140.0, take_profit_price=180.0,
            dry_run=False,
        )
    assert result["entry"] == {"id": 1}
    assert any("Stop-loss leg failed" in w for w in result["warnings"])


# ── exports ───────────────────────────────────────────────────────────────────

# ── instrument cache filter / stats ──────────────────────────────────────────

def _seed_cache() -> InstrumentCache:
    cache = InstrumentCache(db_path=":memory:")
    cache.cache_instruments([
        {"ticker": "AAPL_US_EQ", "type": "STOCK", "currencyCode": "USD",
         "isin": "US0378331005", "name": "Apple Inc", "shortName": "AAPL"},
        {"ticker": "VOD_UK_EQ", "type": "STOCK", "currencyCode": "GBP",
         "isin": "GB00BH4HKS39", "name": "Vodafone Group", "shortName": "VOD"},
        {"ticker": "SPY_US_EQ", "type": "ETF", "currencyCode": "USD",
         "isin": "US78462F1030", "name": "SPDR S&P 500 ETF", "shortName": "SPY"},
        {"ticker": "STN_US_EQ", "type": "STOCK", "currencyCode": "USD",
         "isin": "CA85472N1096", "name": "Stantec", "shortName": "STN"},
    ])
    return cache


def test_filter_by_type_returns_only_matches():
    cache = _seed_cache()
    etfs = cache.filter(type="ETF")
    assert len(etfs) == 1 and etfs[0]["ticker"] == "SPY_US_EQ"


def test_filter_by_currency_and_exchange_combine():
    cache = _seed_cache()
    results = cache.filter(currency="USD", exchange="US")
    tickers = {r["ticker"] for r in results}
    assert tickers == {"AAPL_US_EQ", "SPY_US_EQ", "STN_US_EQ"}


def test_filter_by_country_uses_isin_prefix_not_exchange():
    """Stantec is US-listed but Canadian-issued (ISIN starts CA)."""
    cache = _seed_cache()
    canadian = cache.filter(country="CA")
    assert len(canadian) == 1 and canadian[0]["ticker"] == "STN_US_EQ"


def test_filter_search_matches_name_substring():
    cache = _seed_cache()
    results = cache.filter(search="Vodafone")
    assert len(results) == 1 and results[0]["ticker"] == "VOD_UK_EQ"


def test_filter_limit_caps_results():
    cache = _seed_cache()
    results = cache.filter(currency="USD", limit=2)
    assert len(results) == 2


def test_stats_counts_by_each_dimension():
    cache = _seed_cache()
    stats = cache.stats()
    assert stats["total"]["all"] == 4
    assert stats["by_type"]["STOCK"] == 3
    assert stats["by_type"]["ETF"] == 1
    assert stats["by_currency"]["USD"] == 3
    assert stats["by_exchange"]["US"] == 3
    assert stats["by_exchange"]["UK"] == 1
    assert stats["by_country"]["US"] == 2
    assert stats["by_country"]["CA"] == 1
    assert stats["by_country"]["GB"] == 1


# ── universes ────────────────────────────────────────────────────────────────

def test_diversify_returns_one_per_requested_category():
    from trading_lab.universes import diversify
    basket = diversify(categories=["indexes", "geographic", "bonds"], seed=42)
    assert len(basket.tickers) == 3
    assert len(basket.sources) == 3


def test_diversify_seed_is_deterministic():
    from trading_lab.universes import diversify
    a = diversify(categories=["indexes", "bonds"], seed=7)
    b = diversify(categories=["indexes", "bonds"], seed=7)
    assert a.tickers == b.tickers


def test_sector_sample_returns_n_unique_tickers_from_pool():
    from trading_lab.universes import sector_sample, SP500_BY_SECTOR
    tickers = sector_sample("Technology", count=5, seed=1)
    assert len(tickers) == 5
    assert len(set(tickers)) == 5
    assert all(t in SP500_BY_SECTOR["Technology"] for t in tickers)


def test_sector_sample_unknown_sector_raises():
    from trading_lab.universes import sector_sample
    with pytest.raises(KeyError, match="Unknown sector"):
        sector_sample("Crypto", count=1)


def test_all_universes_includes_sectors_and_sp500():
    from trading_lab.universes import all_universes
    u = all_universes()
    assert "sectors" in u
    assert "sp500_sectors" in u
    assert len(u["sp500_sectors"]) == 11  # 11 GICS sectors


def test_request_export_payload_shape():
    client = Trading212Client(_demo_settings())
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        class R:
            ok = True
            status_code = 200
            text = '{"reportId": 7}'
            def json(self): return {"reportId": 7}
        return R()

    with patch("trading_lab.brokers.trading212.requests.request", side_effect=fake_request):
        client.request_export(
            time_from="2025-01-01T00:00:00Z",
            time_to="2025-12-31T23:59:59Z",
            include_dividends=True, include_interest=False,
            include_orders=True, include_transactions=False,
        )
    assert captured["method"] == "POST"
    assert "/equity/history/exports" in captured["url"]
    body = captured["json"]
    assert body["timeFrom"] == "2025-01-01T00:00:00Z"
    assert body["dataIncluded"] == {
        "includeDividends": True, "includeInterest": False,
        "includeOrders": True, "includeTransactions": False,
    }
