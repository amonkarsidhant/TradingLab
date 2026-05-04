"""
Failure alert throttle for T212 API calls.

Inspired by go-trader's failure_alerts.go — throttles operator alerts so
repeated API errors don't spam Discord/Telegram.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _FailureEntry:
    count: int = 0
    last_notified_at: float = 0.0
    last_err_sig: str = ""


class FailureAlertThrottle:
    """
    Per-(endpoint, error_signature) throttle for API failure alerts.

    Rules (same as go-trader):
      1. Notify on first failure
      2. Notify every 10th consecutive failure
      3. Notify if >= 1 hour since last notification
    """

    _HOUR_SEC = 3600.0

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._entries: dict[str, _FailureEntry] = {}

    @staticmethod
    def _key(endpoint: str, err_sig: str) -> str:
        return f"{endpoint}|{err_sig[:120]}"

    def record(self, endpoint: str, err_msg: str) -> tuple[bool, int]:
        """Record a failure.  Returns (should_notify, failure_count)."""
        now = time.time()
        sig = err_msg[:120]
        key = self._key(endpoint, sig)

        with self._mu:
            e = self._entries.get(key)
            if e is None or sig != e.last_err_sig:
                # Fresh error signature → reset
                self._entries[key] = _FailureEntry(count=1, last_notified_at=now, last_err_sig=sig)
                return True, 1

            e.count += 1
            if e.count <= 1 or e.count % 10 == 0:
                e.last_notified_at = now
                return True, e.count
            if now - e.last_notified_at >= self._HOUR_SEC:
                e.last_notified_at = now
                return True, e.count
            return False, e.count

    def clear(self, endpoint: str, err_sig: str = "") -> None:
        """Call when a request succeeds so the next failure starts fresh."""
        with self._mu:
            self._entries.pop(self._key(endpoint, err_sig), None)

    def format_alert(self, endpoint: str, err_msg: str, count: int) -> str:
        """Build a throttled alert message."""
        note = f" (failure #{count})" if count > 1 else ""
        return f"**API FAILURE** [{endpoint}] {err_msg}{note}"
