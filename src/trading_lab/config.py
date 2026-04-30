from dataclasses import dataclass, field
import os
from dotenv import load_dotenv

load_dotenv()

DEMO_BASE_URL = "https://demo.trading212.com/api/v0"
LIVE_BASE_URL = "https://live.trading212.com/api/v0"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    t212_env: str
    t212_api_key: str
    t212_api_secret: str
    t212_allow_live: bool
    order_placement_enabled: bool
    t212_confirm_live: str
    demo_order_confirm: str
    db_path: str
    telegram_bot_token: str
    t212_auth_header: str = ""
    t212_api_key_invest: str = ""
    t212_api_secret_invest: str = ""
    t212_api_key_isa: str = ""
    t212_api_secret_isa: str = ""
    t212_extended_hours: bool = False
    watcher_enabled: bool = False
    watcher_interval: int = 300
    watcher_autonomy_tier: int = 1

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
    return Settings(
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
    )
