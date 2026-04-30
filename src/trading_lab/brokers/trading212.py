import base64
import hashlib
import json
import logging
import sqlite3
import threading
import time
from enum import Enum
from typing import Any

import requests

from trading_lab.config import Settings

logger = logging.getLogger(__name__)


def _t212_ticker_to_yf(ticker: str) -> str:
    """Convert T212 ticker (AAPL_US_EQ) to a yfinance symbol (AAPL).

    T212 format: {SYMBOL}_{EXCHANGE}_{TYPE}. yfinance uses the bare symbol for
    US tickers; LSE tickers need a `.L` suffix, but those are rare in this lab.
    """
    if "_" not in ticker:
        return ticker
    parts = ticker.split("_")
    symbol = parts[0]
    if len(parts) >= 2 and parts[1] == "UK":
        return f"{symbol}.L"
    return symbol


class RateLimit:
    """Tracks rate limits per endpoint category."""
    def __init__(self, max_requests: int, period_seconds: float):
        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def _remove_old(self, now: float) -> None:
        cutoff = now - self.period_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def wait_if_needed(self) -> None:
        with self._lock:
            now = time.time()
            self._remove_old(now)
            if len(self._timestamps) >= self.max_requests:
                sleep_time = self._timestamps[0] + self.period_seconds - now + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
                now = time.time()
                self._remove_old(now)
            self._timestamps.append(time.time())

    def remaining(self) -> int:
        with self._lock:
            self._remove_old(time.time())
            return self.max_requests - len(self._timestamps)


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class InstrumentCache:
    """In-memory + SQLite cache for T212 instrument metadata."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or "./trading_lab_cache.sqlite3"
        self._memory: dict[str, dict] = {}
        self._by_name: dict[str, str] = {}
        self._loaded = False
        self._last_fetch: float = 0.0

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS t212_instruments (
                ticker TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )
        """)
        conn.commit()

    def load_from_db(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                with sqlite3.connect(self.db_path) as conn:
                    self._ensure_table(conn)
                    rows = conn.execute(
                        "SELECT ticker, data FROM t212_instruments"
                    ).fetchall()
                    for ticker, raw in rows:
                        inst = json.loads(raw)
                        self._memory[ticker] = inst
                        name = inst.get("name", "")
                        short = inst.get("shortName", "")
                        if name:
                            self._by_name[name.lower()] = ticker
                        if short:
                            self._by_name[short.lower()] = ticker
                    self._loaded = True
            except Exception:
                self._loaded = True

    def cache_instruments(self, instruments: list[dict]) -> None:
        with self._lock:
            self._memory.clear()
            self._by_name.clear()
            self._last_fetch = time.time()
            now = time.time()
            try:
                with sqlite3.connect(self.db_path) as conn:
                    self._ensure_table(conn)
                    conn.execute("DELETE FROM t212_instruments")
                    rows = []
                    for inst in instruments:
                        ticker = inst.get("ticker", "")
                        if not ticker:
                            continue
                        self._memory[ticker] = inst
                        name = inst.get("name", "")
                        short = inst.get("shortName", "")
                        if name:
                            self._by_name[name.lower()] = ticker
                        if short:
                            self._by_name[short.lower()] = ticker
                        rows.append((ticker, json.dumps(inst), now))
                    conn.executemany(
                        "INSERT OR REPLACE INTO t212_instruments (ticker, data, fetched_at) VALUES (?, ?, ?)",
                        rows,
                    )
                    conn.commit()
                    self._loaded = True
            except Exception:
                self._loaded = True

    def get(self, ticker: str) -> dict | None:
        if not self._loaded:
            self.load_from_db()
        return self._memory.get(ticker)

    def lookup(self, query: str) -> list[dict]:
        if not self._loaded:
            self.load_from_db()
        query_lower = query.lower()
        results = []
        for ticker, inst in self._memory.items():
            if (query_lower in (inst.get("ticker", "").lower())
                    or query_lower in (inst.get("name", "").lower())
                    or query_lower in (inst.get("shortName", "").lower())):
                results.append(inst)
        return results

    def exact_by_name(self, name: str) -> str | None:
        if not self._loaded:
            self.load_from_db()
        return self._by_name.get(name.lower())

    @property
    def age_seconds(self) -> float:
        if self._last_fetch == 0:
            return float("inf")
        return time.time() - self._last_fetch

    @property
    def count(self) -> int:
        if not self._loaded:
            self.load_from_db()
        return len(self._memory)

    @staticmethod
    def _exchange_from_ticker(ticker: str) -> str:
        """T212 ticker layout: SYMBOL_EXCHANGE_TYPE → returns EXCHANGE."""
        parts = ticker.split("_")
        return parts[1] if len(parts) >= 2 else ""

    @staticmethod
    def _country_from_isin(isin: str) -> str:
        """ISIN first two chars are ISO country of the issuer."""
        return isin[:2].upper() if isin and len(isin) >= 2 else ""

    def filter(
        self,
        type: str = "",
        currency: str = "",
        exchange: str = "",
        country: str = "",
        search: str = "",
        limit: int = 0,
    ) -> list[dict]:
        """Filter cached instruments by any combination of attributes.

        All filters are case-insensitive and ANDed together. Empty filter
        means 'no constraint'.
        """
        if not self._loaded:
            self.load_from_db()
        type_l = type.upper()
        currency_l = currency.upper()
        exchange_l = exchange.upper()
        country_l = country.upper()
        search_l = search.lower()

        results: list[dict] = []
        for inst in self._memory.values():
            if type_l and inst.get("type", "").upper() != type_l:
                continue
            if currency_l and inst.get("currencyCode", "").upper() != currency_l:
                continue
            if exchange_l and self._exchange_from_ticker(inst.get("ticker", "")).upper() != exchange_l:
                continue
            if country_l and self._country_from_isin(inst.get("isin", "")) != country_l:
                continue
            if search_l:
                hay = " ".join([
                    inst.get("ticker", ""),
                    inst.get("name", ""),
                    inst.get("shortName", ""),
                ]).lower()
                if search_l not in hay:
                    continue
            results.append(inst)
            if limit and len(results) >= limit:
                break
        return results

    def stats(self) -> dict[str, dict[str, int]]:
        """Aggregate counts of the cached universe."""
        if not self._loaded:
            self.load_from_db()
        by_type: dict[str, int] = {}
        by_currency: dict[str, int] = {}
        by_exchange: dict[str, int] = {}
        by_country: dict[str, int] = {}
        for inst in self._memory.values():
            by_type[inst.get("type", "?")] = by_type.get(inst.get("type", "?"), 0) + 1
            cur = inst.get("currencyCode", "?") or "?"
            by_currency[cur] = by_currency.get(cur, 0) + 1
            exch = self._exchange_from_ticker(inst.get("ticker", "")) or "?"
            by_exchange[exch] = by_exchange.get(exch, 0) + 1
            ctry = self._country_from_isin(inst.get("isin", "")) or "?"
            by_country[ctry] = by_country.get(ctry, 0) + 1
        return {
            "total": {"all": len(self._memory)},
            "by_type": by_type,
            "by_currency": by_currency,
            "by_exchange": by_exchange,
            "by_country": by_country,
        }


class Trading212Client:
    """Trading 212 REST client with per-endpoint rate limiting, retry, and caching."""

    ENDPOINT_LIMITS = {
        "account/summary": RateLimit(1, 5),
        "positions": RateLimit(1, 1),
        "instruments": RateLimit(1, 50),
        "market_order": RateLimit(50, 60),
        "limit_order": RateLimit(1, 2),
        "stop_order": RateLimit(1, 2),
        "stop_limit_order": RateLimit(1, 2),
        "orders_list": RateLimit(1, 5),
        "orders_get": RateLimit(1, 1),
        "orders_cancel": RateLimit(50, 60),
        "history_orders": RateLimit(50, 60),
        "history_dividends": RateLimit(50, 60),
        "history_transactions": RateLimit(50, 60),
        "exchanges": RateLimit(1, 30),
        "exports": RateLimit(1, 30),
        "default": RateLimit(5, 60),
    }

    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 1.5
    IDEMPOTENCY_TTL_SECONDS = 60.0
    _IDEMPOTENT_PATHS = (
        "/equity/orders/market",
        "/equity/orders/limit",
        "/equity/orders/stop",
        "/equity/orders/stop_limit",
    )

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")
        self._instrument_cache = InstrumentCache(
            db_path=settings.db_path.replace(".sqlite3", "_cache.sqlite3")
        )
        self._idempotency_cache: dict[str, tuple[float, Any]] = {}
        self._idempotency_lock = threading.Lock()

    def _idempotency_key(self, method: str, path: str, json_body: Any) -> str:
        body = json.dumps(json_body, sort_keys=True, default=str) if json_body else ""
        h = hashlib.sha256(f"{method}|{path}|{body}".encode("utf-8")).hexdigest()
        return h

    def _idempotency_get(self, key: str) -> Any | None:
        with self._idempotency_lock:
            entry = self._idempotency_cache.get(key)
            if not entry:
                return None
            ts, value = entry
            if time.time() - ts > self.IDEMPOTENCY_TTL_SECONDS:
                del self._idempotency_cache[key]
                return None
            return value

    def _idempotency_put(self, key: str, value: Any) -> None:
        now = time.time()
        with self._idempotency_lock:
            self._idempotency_cache[key] = (now, value)
            stale = [k for k, (ts, _) in self._idempotency_cache.items()
                     if now - ts > self.IDEMPOTENCY_TTL_SECONDS]
            for k in stale:
                del self._idempotency_cache[k]

    def _resolve_limit(self, endpoint: str) -> RateLimit:
        for key, limit in self.ENDPOINT_LIMITS.items():
            if key in endpoint:
                return limit
        return self.ENDPOINT_LIMITS["default"]

    def _auth_header(self) -> dict[str, str]:
        auth_header = self.settings.t212_auth_header
        if auth_header:
            return {"Authorization": auth_header}

        api_key = self.settings.t212_api_key
        api_secret = self.settings.t212_api_secret

        if not api_key or not api_secret:
            if self.settings.t212_api_key_invest and self.settings.t212_api_secret_invest:
                api_key = self.settings.t212_api_key_invest
                api_secret = self.settings.t212_api_secret_invest
            elif self.settings.t212_api_key_isa and self.settings.t212_api_secret_isa:
                api_key = self.settings.t212_api_key_isa
                api_secret = self.settings.t212_api_secret_isa

        if not api_key or not api_secret:
            raise RuntimeError(
                "Missing T212 credentials. Set T212_API_KEY + T212_API_SECRET "
                "or T212_AUTH_HEADER in environment."
            )

        raw = f"{api_key}:{api_secret}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        endpoint_key = path.split("?")[0].strip("/")
        rate_limit = self._resolve_limit(endpoint_key)

        idem_key: str | None = None
        if method.upper() == "POST" and any(p in path for p in self._IDEMPOTENT_PATHS):
            idem_key = self._idempotency_key(method, path, kwargs.get("json"))
            cached = self._idempotency_get(idem_key)
            if cached is not None:
                logger.warning(
                    "Idempotency dedupe hit for %s %s — returning cached response",
                    method, path,
                )
                return cached

        rate_limit.wait_if_needed()

        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            response = requests.request(
                method=method,
                url=url,
                headers=self._auth_header(),
                timeout=30,
                **kwargs,
            )

            if response.ok:
                result = response.json() if response.text.strip() else None
                if idem_key is not None:
                    self._idempotency_put(idem_key, result)
                return result

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_time = float(retry_after)
                    except ValueError:
                        sleep_time = self.RETRY_BACKOFF_BASE ** attempt
                else:
                    sleep_time = self.RETRY_BACKOFF_BASE ** attempt
                sleep_time = min(sleep_time, 60)
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(sleep_time)
                    continue

            if response.status_code in (401, 403, 404, 422):
                response.raise_for_status()

            last_error = response
            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_BACKOFF_BASE ** attempt)

        if last_error is not None:
            last_error.raise_for_status()
        raise RuntimeError(f"Request failed after {self.MAX_RETRIES} retries")

    def _paginate(self, method: str, initial_path: str, **kwargs: Any) -> list[dict]:
        items: list[dict] = []
        next_path: str | None = initial_path
        while next_path:
            page = self._request(method, next_path, **kwargs)
            if page is None:
                break
            items.extend(page.get("items", []))
            next_path = page.get("nextPagePath")
            if next_path:
                time.sleep(1.0)
        return items

    def _validate_buy(self, ticker: str, quantity: float) -> tuple[bool, str]:
        if quantity <= 0:
            return False, "Buy quantity must be positive."
        try:
            summary = self.account_summary()
            available = summary.get("cash", {}).get("availableToTrade", 0)
            est_price = self._get_current_price(ticker)
            if est_price <= 0:
                return False, (
                    f"Cannot estimate cost for {ticker}: no price available "
                    f"(not in positions, no yfinance quote). Funds check skipped."
                )
            est_cost = quantity * est_price
            if est_cost > available:
                return False, (
                    f"Insufficient funds: need ~{est_cost:.2f}, "
                    f"have {available:.2f} available to trade."
                )
        except Exception as e:
            return False, f"Fund check failed: {e}"
        return True, f"Funds OK (est cost {quantity * est_price:.2f})."

    def _validate_sell(self, ticker: str, quantity: float) -> tuple[bool, str]:
        if quantity <= 0:
            return False, "Sell quantity must be positive."
        try:
            positions = self.positions()
            for p in positions:
                if p.get("instrument", {}).get("ticker") == ticker:
                    available = p.get("quantityAvailableForTrading", 0)
                    if quantity > available:
                        return False, (
                            f"Insufficient shares: requested {quantity}, "
                            f"available {available} (some may be in pies)."
                        )
                    return True, "Shares OK."
            return False, f"No position found for {ticker}."
        except Exception as e:
            return False, f"Position check failed: {e}"
        return True, ""

    def _get_current_price(self, ticker: str) -> float:
        """Best-effort current price.

        Order of precedence:
          1. T212 positions() — exact, but only for held tickers.
          2. yfinance — last close for non-held tickers (~15min delayed).
        Returns 0 if nothing works.
        """
        try:
            for p in self.positions():
                if p.get("instrument", {}).get("ticker") == ticker:
                    return float(p.get("currentPrice", 0) or 0)
        except Exception:
            pass

        try:
            import yfinance as yf
            yf_symbol = _t212_ticker_to_yf(ticker)
            tk = yf.Ticker(yf_symbol)
            hist = tk.history(period="5d", auto_adjust=True)
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as exc:
            logger.debug("yfinance price fallback failed for %s: %s", ticker, exc)
        return 0.0

    # ── Account ───────────────────────────────────────────────────────────

    def account_summary(self) -> Any:
        return self._request("GET", "/equity/account/summary")

    # ── Positions ──────────────────────────────────────────────────────────

    def positions(self, ticker: str = "") -> Any:
        path = "/equity/positions"
        if ticker:
            path += f"?ticker={ticker}"
        return self._request("GET", path)

    # ── Instruments with caching ───────────────────────────────────────────

    def instruments(self, force_refresh: bool = False) -> Any:
        cache = self._instrument_cache
        if not force_refresh and cache.count > 0:
            return [cache.get(t) for t in cache._memory if cache.get(t) is not None]
        data = self._request("GET", "/equity/metadata/instruments")
        if isinstance(data, list):
            cache.cache_instruments(data)
            return data
        return []

    def lookup_ticker(self, query: str) -> list[dict]:
        self._instrument_cache.load_from_db()
        results = self._instrument_cache.lookup(query)
        if not results:
            self.instruments(force_refresh=True)
            results = self._instrument_cache.lookup(query)
        return results

    def resolve_ticker(self, query: str) -> str | None:
        cached = self._instrument_cache.exact_by_name(query)
        if cached:
            return cached
        results = self.lookup_ticker(query)
        if results:
            return results[0].get("ticker")
        return None

    # ── Exchange metadata ──────────────────────────────────────────────────

    def exchanges(self) -> Any:
        return self._request("GET", "/equity/metadata/exchanges")

    # ── Order placement ────────────────────────────────────────────────────

    def market_order(
        self,
        ticker: str,
        quantity: float,
        dry_run: bool = True,
        extended_hours: bool = False,
    ) -> dict[str, Any]:
        payload: dict = {"ticker": ticker, "quantity": quantity}
        if extended_hours:
            payload["extendedHours"] = True

        if dry_run:
            if quantity > 0:
                valid, msg = self._validate_buy(ticker, quantity)
                if not valid:
                    return {"dry_run": True, "message": msg, "payload": payload}
            else:
                valid, msg = self._validate_sell(ticker, abs(quantity))
                if not valid:
                    return {"dry_run": True, "message": msg, "payload": payload}
            return {"dry_run": True, "message": "Market order not sent.", "payload": payload}

        if not self.settings.can_place_orders:
            raise RuntimeError(
                "Order placement is disabled. Keep it disabled during the 30-day trading sprint."
            )

        return self._request("POST", "/equity/orders/market", json=payload)

    def limit_order(
        self,
        ticker: str,
        quantity: float,
        limit_price: float,
        dry_run: bool = True,
        time_validity: str = "DAY",
    ) -> dict[str, Any]:
        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "limitPrice": limit_price,
            "timeValidity": time_validity,
        }

        if dry_run:
            return {"dry_run": True, "message": "Limit order not sent.", "payload": payload}

        if not self.settings.can_place_orders:
            raise RuntimeError("Order placement is disabled.")

        return self._request("POST", "/equity/orders/limit", json=payload)

    def stop_order(
        self,
        ticker: str,
        quantity: float,
        stop_price: float,
        dry_run: bool = True,
        time_validity: str = "GOOD_TILL_CANCEL",
    ) -> dict[str, Any]:
        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "stopPrice": stop_price,
            "timeValidity": time_validity,
        }

        if dry_run:
            return {"dry_run": True, "message": "Stop order not sent.", "payload": payload}

        if not self.settings.can_place_orders:
            raise RuntimeError("Order placement is disabled.")

        return self._request("POST", "/equity/orders/stop", json=payload)

    def stop_limit_order(
        self,
        ticker: str,
        quantity: float,
        stop_price: float,
        limit_price: float,
        dry_run: bool = True,
        time_validity: str = "DAY",
    ) -> dict[str, Any]:
        payload = {
            "ticker": ticker,
            "quantity": quantity,
            "stopPrice": stop_price,
            "limitPrice": limit_price,
            "timeValidity": time_validity,
        }

        if dry_run:
            return {"dry_run": True, "message": "Stop-limit order not sent.", "payload": payload}

        if not self.settings.can_place_orders:
            raise RuntimeError("Order placement is disabled.")

        return self._request("POST", "/equity/orders/stop_limit", json=payload)

    # ── Order management ───────────────────────────────────────────────────

    def pending_orders(self) -> Any:
        return self._request("GET", "/equity/orders")

    def get_order(self, order_id: int) -> Any:
        return self._request("GET", f"/equity/orders/{order_id}")

    def cancel_order(self, order_id: int) -> Any:
        return self._request("DELETE", f"/equity/orders/{order_id}")

    # ── History ────────────────────────────────────────────────────────────

    def history_orders(self, ticker: str = "", limit: int = 50) -> list[dict]:
        path = f"/equity/history/orders?limit={limit}"
        if ticker:
            path += f"&ticker={ticker}"
        return self._paginate("GET", path)

    def history_dividends(self, ticker: str = "", limit: int = 50) -> list[dict]:
        path = f"/equity/history/dividends?limit={limit}"
        if ticker:
            path += f"&ticker={ticker}"
        return self._paginate("GET", path)

    def history_transactions(self, limit: int = 50) -> list[dict]:
        return self._paginate("GET", f"/equity/history/transactions?limit={limit}")

    # ── CSV exports ────────────────────────────────────────────────────────

    def request_export(
        self,
        time_from: str,
        time_to: str,
        include_dividends: bool = True,
        include_interest: bool = True,
        include_orders: bool = True,
        include_transactions: bool = True,
    ) -> dict[str, Any]:
        """Request a CSV report. time_from / time_to are ISO 8601 strings."""
        payload = {
            "dataIncluded": {
                "includeDividends": include_dividends,
                "includeInterest": include_interest,
                "includeOrders": include_orders,
                "includeTransactions": include_transactions,
            },
            "timeFrom": time_from,
            "timeTo": time_to,
        }
        return self._request("POST", "/equity/history/exports", json=payload)

    def list_exports(self) -> Any:
        """Check status / download links for previously requested exports."""
        return self._request("GET", "/equity/history/exports")

    # ── Composite order helpers ────────────────────────────────────────────

    def replace_order(
        self,
        order_id: int,
        order_type: OrderType,
        ticker: str,
        quantity: float,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_validity: str = "DAY",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Cancel an existing order and place a replacement.

        T212 has no native edit endpoint — this is cancel + re-place. If the
        cancel succeeds but the re-place fails, the position is left flat
        and the failure is surfaced to the caller (no auto-retry).
        """
        if dry_run:
            return {
                "dry_run": True,
                "message": f"Would cancel order {order_id} and place replacement.",
                "order_id": order_id,
                "new_payload": {
                    "type": order_type.value, "ticker": ticker, "quantity": quantity,
                    "limitPrice": limit_price, "stopPrice": stop_price,
                    "timeValidity": time_validity,
                },
            }

        cancel_result = self.cancel_order(order_id)

        try:
            if order_type == OrderType.LIMIT:
                if limit_price is None:
                    raise ValueError("limit_price required for LIMIT replacement.")
                new_order = self.limit_order(
                    ticker, quantity, limit_price,
                    dry_run=False, time_validity=time_validity,
                )
            elif order_type == OrderType.STOP:
                if stop_price is None:
                    raise ValueError("stop_price required for STOP replacement.")
                new_order = self.stop_order(
                    ticker, quantity, stop_price,
                    dry_run=False, time_validity=time_validity,
                )
            elif order_type == OrderType.STOP_LIMIT:
                if stop_price is None or limit_price is None:
                    raise ValueError("stop_price and limit_price required for STOP_LIMIT.")
                new_order = self.stop_limit_order(
                    ticker, quantity, stop_price, limit_price,
                    dry_run=False, time_validity=time_validity,
                )
            elif order_type == OrderType.MARKET:
                new_order = self.market_order(ticker, quantity, dry_run=False)
            else:
                raise ValueError(f"Unsupported order_type: {order_type}")
        except Exception as exc:
            return {
                "cancelled": cancel_result,
                "replacement_error": str(exc),
                "warning": "Original order cancelled; replacement FAILED. Position is unprotected.",
            }

        return {"cancelled": cancel_result, "replacement": new_order}

    def bracket_order(
        self,
        ticker: str,
        quantity: float,
        stop_price: float,
        take_profit_price: float,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Market entry + protective stop + take-profit limit.

        Best-effort: places legs sequentially. If a protective leg fails after
        the entry fills, returns a warning rather than rolling back the entry
        (T212 has no atomic bracket endpoint and partial fills can't be undone).
        Caller should monitor 'warnings' and decide whether to manually cover.
        """
        if quantity <= 0:
            raise ValueError("bracket_order requires a positive entry quantity (long-only).")

        if dry_run:
            return {
                "dry_run": True,
                "entry": {"type": "MARKET", "ticker": ticker, "quantity": quantity},
                "stop_loss": {"type": "STOP", "ticker": ticker, "quantity": -quantity, "stopPrice": stop_price},
                "take_profit": {"type": "LIMIT", "ticker": ticker, "quantity": -quantity, "limitPrice": take_profit_price},
            }

        warnings: list[str] = []
        entry = self.market_order(ticker, quantity, dry_run=False)

        try:
            stop = self.stop_order(
                ticker, -quantity, stop_price,
                dry_run=False, time_validity="GOOD_TILL_CANCEL",
            )
        except Exception as exc:
            stop = {"error": str(exc)}
            warnings.append(f"Stop-loss leg failed: {exc}. Position UNPROTECTED.")

        try:
            tp = self.limit_order(
                ticker, -quantity, take_profit_price,
                dry_run=False, time_validity="GOOD_TILL_CANCEL",
            )
        except Exception as exc:
            tp = {"error": str(exc)}
            warnings.append(f"Take-profit leg failed: {exc}.")

        return {"entry": entry, "stop_loss": stop, "take_profit": tp, "warnings": warnings}
