import base64
import time
from typing import Any

import requests

from trading_lab.config import Settings


class Trading212Client:
    """Trading 212 REST client with built-in rate limiting.

    Rate limits (from T212 docs):
    - account/summary: 1 req / 5s
    - positions: 1 req / 5s
    - instruments: 1 req / 50s
    - orders/market: 50 req / min
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.base_url.rstrip("/")
        self._last_request_time: float = 0.0
        self._min_delay: float = 6.0  # seconds between any two requests

    def _auth_header(self) -> dict[str, str]:
        if not self.settings.t212_api_key or not self.settings.t212_api_secret:
            raise RuntimeError("Missing T212_API_KEY or T212_API_SECRET. Add demo credentials to .env.")

        raw = f"{self.settings.t212_api_key}:{self.settings.t212_api_secret}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        # Rate limiting
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)

        url = f"{self.base_url}{path}"
        response = requests.request(
            method=method,
            url=url,
            headers=self._auth_header(),
            timeout=20,
            **kwargs,
        )
        self._last_request_time = time.time()
        response.raise_for_status()

        if response.text.strip():
            return response.json()
        return None

    def account_summary(self) -> Any:
        return self._request("GET", "/equity/account/summary")

    def positions(self) -> Any:
        return self._request("GET", "/equity/positions")

    def instruments(self) -> Any:
        return self._request("GET", "/equity/metadata/instruments")

    def market_order(self, ticker: str, quantity: float, dry_run: bool = True) -> dict[str, Any]:
        payload = {"ticker": ticker, "quantity": quantity}

        if dry_run:
            return {
                "dry_run": True,
                "message": "Market order not sent.",
                "payload": payload,
            }

        if not self.settings.can_place_orders:
            raise RuntimeError(
                "Order placement is disabled. Keep it disabled during the 30-day trading sprint."
            )

        return self._request("POST", "/equity/orders/market", json=payload)
