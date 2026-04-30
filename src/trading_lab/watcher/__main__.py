"""
Entry point: python -m trading_lab.watcher

Starts the dynamic position watcher daemon.
"""
from trading_lab.config import get_settings
from trading_lab.watcher.loop import run_watcher


def main() -> None:
    settings = get_settings()
    if not settings.watcher_enabled:
        print("Watcher is disabled. Set T212_WATCHER_ENABLED=true in .env")
        return
    if settings.watcher_autonomy_tier not in (1, 2, 3):
        print(f"Invalid autonomy tier: {settings.watcher_autonomy_tier}. Must be 1, 2, or 3.")
        return
    print(f"Starting watcher (tier={settings.watcher_autonomy_tier}, interval={settings.watcher_interval}s)")
    run_watcher(settings)


if __name__ == "__main__":
    main()
