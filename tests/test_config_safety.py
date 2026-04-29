"""
Config-level safety tests for Sid Trading Lab.

These tests verify that the Settings class enforces all live-trading locks
correctly. No network calls are made. No API keys are used.

All tests use monkeypatch to isolate environment variables so they cannot
interfere with each other or with a real .env file on disk.
"""
import pytest

from trading_lab.config import get_settings, DEMO_BASE_URL, LIVE_BASE_URL


# ── 1. Demo base URL ──────────────────────────────────────────────────────────

def test_demo_env_resolves_to_demo_base_url(monkeypatch):
    """T212_ENV=demo must point at the demo base URL, never live."""
    monkeypatch.setenv("T212_ENV", "demo")
    monkeypatch.setenv("T212_ALLOW_LIVE", "false")
    monkeypatch.setenv("ORDER_PLACEMENT_ENABLED", "false")
    monkeypatch.setenv("T212_CONFIRM_LIVE", "")

    settings = get_settings()

    assert settings.base_url == DEMO_BASE_URL
    assert LIVE_BASE_URL not in settings.base_url


# ── 2. Live env blocked when T212_ALLOW_LIVE=false ────────────────────────────

def test_live_env_blocked_when_allow_live_false(monkeypatch):
    """T212_ENV=live must raise RuntimeError if T212_ALLOW_LIVE is not true."""
    monkeypatch.setenv("T212_ENV", "live")
    monkeypatch.setenv("T212_ALLOW_LIVE", "false")
    monkeypatch.setenv("T212_CONFIRM_LIVE", "I_ACCEPT_REAL_MONEY_RISK")

    settings = get_settings()

    with pytest.raises(RuntimeError, match="T212_ALLOW_LIVE=false"):
        _ = settings.base_url


# ── 3. Live env blocked when T212_CONFIRM_LIVE is missing ────────────────────

def test_live_env_blocked_when_confirm_live_missing(monkeypatch):
    """T212_ENV=live with T212_ALLOW_LIVE=true but no confirm string must raise."""
    monkeypatch.setenv("T212_ENV", "live")
    monkeypatch.setenv("T212_ALLOW_LIVE", "true")
    monkeypatch.delenv("T212_CONFIRM_LIVE", raising=False)

    settings = get_settings()

    with pytest.raises(RuntimeError, match="T212_CONFIRM_LIVE"):
        _ = settings.base_url


# ── 4. Live env blocked when T212_CONFIRM_LIVE is wrong ──────────────────────

def test_live_env_blocked_when_confirm_live_wrong(monkeypatch):
    """T212_ENV=live with a wrong confirmation string must raise."""
    monkeypatch.setenv("T212_ENV", "live")
    monkeypatch.setenv("T212_ALLOW_LIVE", "true")
    monkeypatch.setenv("T212_CONFIRM_LIVE", "yes_please")

    settings = get_settings()

    with pytest.raises(RuntimeError, match="T212_CONFIRM_LIVE"):
        _ = settings.base_url


# ── 5. can_place_orders=False when ORDER_PLACEMENT_ENABLED=false ──────────────

def test_can_place_orders_false_when_order_placement_disabled(monkeypatch):
    """ORDER_PLACEMENT_ENABLED=false must block orders regardless of environment."""
    monkeypatch.setenv("T212_ENV", "demo")
    monkeypatch.setenv("ORDER_PLACEMENT_ENABLED", "false")

    settings = get_settings()

    assert settings.can_place_orders is False


# ── 6. can_place_orders=False for live without full confirmation ───────────────

def test_can_place_orders_false_for_live_without_allow_live_flag(monkeypatch):
    """Live env with ORDER_PLACEMENT_ENABLED=true but T212_ALLOW_LIVE=false must
    still block order placement."""
    monkeypatch.setenv("T212_ENV", "live")
    monkeypatch.setenv("ORDER_PLACEMENT_ENABLED", "true")
    monkeypatch.setenv("T212_ALLOW_LIVE", "false")
    monkeypatch.setenv("T212_CONFIRM_LIVE", "I_ACCEPT_REAL_MONEY_RISK")

    settings = get_settings()

    assert settings.can_place_orders is False


def test_can_place_orders_false_for_live_with_wrong_confirm_string(monkeypatch):
    """Live env with T212_ALLOW_LIVE=true but wrong confirm string must still
    block order placement."""
    monkeypatch.setenv("T212_ENV", "live")
    monkeypatch.setenv("ORDER_PLACEMENT_ENABLED", "true")
    monkeypatch.setenv("T212_ALLOW_LIVE", "true")
    monkeypatch.setenv("T212_CONFIRM_LIVE", "WRONG_STRING")

    settings = get_settings()

    assert settings.can_place_orders is False


# ── 7. Invalid T212_ENV raises ValueError ─────────────────────────────────────

def test_invalid_t212_env_raises_value_error(monkeypatch):
    """An unrecognised T212_ENV value must raise ValueError, not silently default."""
    monkeypatch.setenv("T212_ENV", "sandbox")

    settings = get_settings()

    with pytest.raises(ValueError, match="T212_ENV must be either"):
        _ = settings.base_url
