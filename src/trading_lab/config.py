from typing import Any
from dataclasses import dataclass, field
import os
from dotenv import load_dotenv

load_dotenv()

import json

DEMO_BASE_URL = "https://demo.trading212.com/api/v0"
LIVE_BASE_URL = "https://live.trading212.com/api/v0"

CURRENT_CONFIG_VERSION = 2


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    config_version: int = 1
    t212_env: str = "demo"
    t212_api_key: str = ""
    t212_api_secret: str = ""
    t212_allow_live: bool = False
    order_placement_enabled: bool = False
    t212_confirm_live: str = ""
    demo_order_confirm: str = ""
    db_path: str = "./trading_lab.sqlite3"
    telegram_bot_token: str = ""
    t212_auth_header: str = ""
    t212_api_key_invest: str = ""
    t212_api_secret_invest: str = ""
    t212_api_key_isa: str = ""
    t212_api_secret_isa: str = ""
    t212_extended_hours: bool = False
    watcher_enabled: bool = False
    watcher_interval: int = 300
    watcher_autonomy_tier: int = 1
    watcher_fast_interval: int = 90
    watcher_drawdown_warn_pct: float = 0.80
    max_concentration_pct: float = 60.0
    max_same_direction_pct: float = 75.0
    tiered_stops: tuple[dict[str, Any], ...] | None = None
    earnings_block_missing: bool = False  # if True, skip trades when earnings data unavailable

    @property
    def base_url(self) -> str:
        if self.t212_env == "demo":
            return DEMO_BASE_URL

        if self.t212_env == "live":
            if not self.t212_allow_live:
                raise RuntimeError("Live Trading 212 environment requested but T212_ALLOW_LIVE=false.")
            if self.t212_confirm_live != "I_ACCEPT_REAL_MONEY_RISK":
                raise RuntimeError("Live trading requires T212_CONFIRM_LIVE=I_ACCEPT_REAL_MONEY_RISK.")
            return LIVE_BASE_URL

        raise ValueError("T212_ENV must be either 'demo' or 'live'.")

    @property
    def can_place_orders(self) -> bool:
        if not self.order_placement_enabled:
            return False
        if self.t212_env == "demo":
            return self.demo_order_confirm == "I_ACCEPT_DEMO_ORDER_TEST"
        if self.t212_env == "live":
            return (
                self.t212_allow_live
                and self.t212_confirm_live == "I_ACCEPT_REAL_MONEY_RISK"
            )
        return False


def get_settings() -> Settings:
    settings = Settings(
        config_version=int(os.getenv("CONFIG_VERSION", "1")),
        t212_env=os.getenv("T212_ENV", "demo").strip().lower(),
        t212_api_key=os.getenv("T212_API_KEY", ""),
        t212_api_secret=os.getenv("T212_API_SECRET", ""),
        t212_allow_live=_as_bool(os.getenv("T212_ALLOW_LIVE"), False),
        order_placement_enabled=_as_bool(os.getenv("ORDER_PLACEMENT_ENABLED"), False),
        t212_confirm_live=os.getenv("T212_CONFIRM_LIVE", ""),
        demo_order_confirm=os.getenv("DEMO_ORDER_CONFIRM", ""),
        db_path=os.getenv("TRADING_LAB_DB", "./trading_lab.sqlite3"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        t212_auth_header=os.getenv("T212_AUTH_HEADER", ""),
        t212_api_key_invest=os.getenv("T212_API_KEY_INVEST", ""),
        t212_api_secret_invest=os.getenv("T212_API_SECRET_INVEST", ""),
        t212_api_key_isa=os.getenv("T212_API_KEY_STOCKS_ISA", ""),
        t212_api_secret_isa=os.getenv("T212_API_SECRET_STOCKS_ISA", ""),
        t212_extended_hours=_as_bool(os.getenv("T212_EXTENDED_HOURS"), False),
        watcher_enabled=_as_bool(os.getenv("T212_WATCHER_ENABLED"), False),
        watcher_interval=int(os.getenv("T212_WATCHER_INTERVAL", "300")),
        watcher_autonomy_tier=int(os.getenv("T212_WATCHER_AUTONOMY_TIER", "1")),
        watcher_fast_interval=int(os.getenv("T212_WATCHER_FAST_INTERVAL", "90")),
        watcher_drawdown_warn_pct=float(os.getenv("T212_WATCHER_DRAWDOWN_WARN_PCT", "0.80")),
        max_concentration_pct=float(os.getenv("MAX_CONCENTRATION_PCT", "60.0")),
        max_same_direction_pct=float(os.getenv("MAX_SAME_DIRECTION_PCT", "75.0")),
        tiered_stops=None,
        earnings_block_missing=_as_bool(os.getenv("EARNINGS_BLOCK_MISSING"), False),
    )
    return _migrate_config(settings)


def _migrate_config(current: Settings) -> Settings:
    """Auto-migrate config to latest version. Returns a Settings object."""
    v = current.config_version
    if v >= CURRENT_CONFIG_VERSION:
        return current

    # Migration 1 -> 2
    if v == 1:
        # Add Phase 2 fields: fast interval, drawdown warn, concentration, tiered stops
        tiered_raw = os.getenv("T212_TIERED_STOPS", "")
        tiered = None
        if tiered_raw:
            try:
                parsed = json.loads(tiered_raw)
                if isinstance(parsed, list):
                    tiered = tuple(parsed)
            except json.JSONDecodeError:
                tiered = None
        new = {
            **current.__dict__,
            "config_version": 2,
            "watcher_fast_interval": int(os.getenv("T212_WATCHER_FAST_INTERVAL", "90")),
            "watcher_drawdown_warn_pct": float(os.getenv("T212_WATCHER_DRAWDOWN_WARN_PCT", "0.80")),
            "max_concentration_pct": float(os.getenv("MAX_CONCENTRATION_PCT", "60.0")),
            "max_same_direction_pct": float(os.getenv("MAX_SAME_DIRECTION_PCT", "75.0")),
            "tiered_stops": tiered,
        }
        current = Settings(**new)
        v = 2

    # Migration 2 -> 3
    # if v == 2:
    #     new_fields = {**current.__dict__, "new_field": "default"}
    #     current = Settings(**new_fields)
    #     v = 3

    return current
