"""
Dynamic Observer — position watcher event loop.

Runs as a daemon, polls T212 positions continuously during market hours,
evaluates drawdown thresholds, places stops, and triggers kill switch.
"""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime, timezone

from trading_lab.brokers.trading212 import Trading212Client
from trading_lab.config import Settings
from trading_lab.logger import SnapshotLogger
from trading_lab.watcher.concentration import ConcentrationGuard
from trading_lab.watcher.guardrails import ALERT_THRESHOLDS, GuardrailEnforcer
from trading_lab.watcher.kill_switch import KillSwitch, KillSwitchState
from trading_lab.watcher.strategies import DeterministicStrategyRunner
from trading_lab.watcher.tiered_stops import TieredStopLoss
from trading_lab.watcher.tiers import AutonomyRouter

_RUNNING = True


class PositionWatcher:
    """Continuously monitors positions and acts on drawdown."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.broker = Trading212Client(settings)
        self.logger = SnapshotLogger(settings.db_path)
        self.guardrails = GuardrailEnforcer()
        self.autonomy = AutonomyRouter(settings.watcher_autonomy_tier)
        self.kill_switch = KillSwitch(self.logger)
        self.det_strategies = DeterministicStrategyRunner(settings.db_path)
        self._interval = max(settings.watcher_interval, 60)
        self._fast_interval = max(getattr(settings, "watcher_fast_interval", 90), 30)
        self._warn_threshold = getattr(settings, "watcher_drawdown_warn_pct", 0.80)
        self._alerted: dict[str, set[float]] = {}
        self._peak_value: float = 0.0
        self._concentration = ConcentrationGuard(
            max_concentration_pct=getattr(settings, "max_concentration_pct", 60.0),
            max_same_direction_pct=getattr(settings, "max_same_direction_pct", 75.0),
            block_on_warning=False,
        )
        self._tiered_stops = TieredStopLoss(
            tiers=getattr(settings, "tiered_stops", None)
        )

    def run(self) -> None:
        self.kill_switch.load_state()
        self._log("info", f"Watcher starting (tier={self.autonomy.tier.value}, interval={self._interval}s)")

        while _RUNNING:
            try:
                self._tick()
            except Exception as exc:
                self._log("error", f"Tick failed: {exc}")

            for _ in range(self._interval):
                if not _RUNNING:
                    break
                time.sleep(1)

        self._log("info", "Watcher stopped.")

    def _tick(self) -> None:
        if not self._is_market_hours():
            self._log("debug", "Outside market hours, skipping.")
            return

        summary = self.broker.account_summary()
        positions_raw = self.broker.positions()

        total_value = summary.get("totalValue", 0)
        if total_value > self._peak_value:
            self._peak_value = total_value
            self.logger.save_watcher_state("peak_value", str(total_value))

        cash = summary.get("cash", {}).get("availableToTrade", 0)
        cash_pct = cash / max(total_value, 1)

        # Kill switch check
        portfolio_dd = self.kill_switch.portfolio_drawdown(
            total_value, max(self._peak_value, total_value)
        )
        if self.kill_switch.evaluate(portfolio_dd):
            self._log("alert", f"KILL SWITCH: portfolio drawdown {portfolio_dd*100:.1f}%")
            if self.autonomy.can_auto_sell():
                results = self.kill_switch.fire(self.broker, positions_raw)
                for r in results:
                    self._log("alert", f"  {r['ticker']}: {r['status']}")
            return

        if self.kill_switch.is_fired():
            return

        # --- Portfolio-level concentration check (once per tick) ---
        conc_ok, conc_warnings = self._concentration.check(
            positions_raw,
            {p["instrument"]["ticker"]: p.get("currentPrice", 0) for p in positions_raw if p.get("instrument")},
        )
        if conc_warnings:
            for w in conc_warnings:
                self._log("warning", f"Concentration: {w}")
        if not conc_ok:
            self._log("alert", f"🚫 Portfolio blocked — concentration breach ({conc_warnings[0]})")
            for p in positions_raw:
                ticker = p.get("instrument", {}).get("ticker", "?")
                self.logger.save_watcher_event(
                    ticker=ticker,
                    drawdown_pct=0,
                    action_taken="blocked_concentration",
                    details="; ".join(conc_warnings),
                )
            # Still evaluate individual positions for logging, but skip buys

        # Track max drawdown for interval acceleration
        max_drawdown = 0.0

        # Per-position evaluation
        for p in positions_raw:
            inst = p.get("instrument", {})
            ticker = inst.get("ticker", "?")
            current_price = p.get("currentPrice", 0)
            avg_price = p.get("averagePricePaid", 0)

            if avg_price <= 0:
                continue

            pnl_pct = (current_price - avg_price) / avg_price
            drawdown = abs(min(pnl_pct, 0))
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            # Skip further checks if concentration blocked (but still log)
            if not conc_ok:
                self.logger.save_watcher_event(
                    ticker=ticker,
                    drawdown_pct=drawdown,
                    action_taken="monitored_conc_blocked",
                )
                continue

            # --- Tiered stop evaluation ---
            qty = float(p.get("quantity", p.get("filledQuantity", 0)))
            tiers = getattr(self._tiered_stops, "tiers", [])
            if qty > 0 and tiers and drawdown >= tiers[0].drawdown_pct:
                tier = self._tiered_stops.evaluate(ticker, drawdown, qty)
                if tier is not None:
                    close_qty = qty * tier.close_fraction
                    if self.autonomy.can_auto_sell():
                        self._log(
                            "action",
                            f"🔻 {ticker} tiered stop at {drawdown*100:.1f}% — "
                            f"closing {tier.close_fraction*100:.0f}% ({close_qty:.2f} shares)",
                        )
                        self.logger.save_watcher_event(
                            ticker=ticker,
                            drawdown_pct=drawdown,
                            action_taken="tiered_stop",
                            details=f"closed {tier.close_fraction} at {drawdown*100:.1f}%",
                        )
                        # Execute the partial close (demo-mode only)
                        if self.autonomy.can_auto_sell():
                            try:
                                self.broker.market_order(
                                    ticker=ticker,
                                    quantity=-round(close_qty, 4),
                                    dry_run=True,
                                )
                            except Exception as e:
                                self._log("error", f"Tiered stop failed: {e}")
                    else:
                        self._log(
                            "alert",
                            f"🔻 {ticker} tiered stop at {drawdown*100:.1f}% — "
                            f"{tier.close_fraction*100:.0f}% exit needed",
                        )

            # --- Normal drawdown alert chain (legacy) ---
            self._evaluate_position(ticker, drawdown, cash_pct, len(positions_raw))

        # --- Interval acceleration ---
        new_interval = self._accelerate_interval(drawdown)
        if new_interval != self._interval:
            self._interval = new_interval
            self._log("info", f"Accelerated watcher interval to {new_interval}s")

        # Deterministic strategy check
        try:
            det_results = self.det_strategies.run_and_compare()
            if det_results:
                self._log("debug", f"Deterministic signals: { {k: v['action'] for k, v in det_results.items()} }")
        except Exception as e:
            self._log("debug", f"Deterministic strategy check skipped: {e}")

    def _evaluate_position(
        self, ticker: str, drawdown: float, cash_pct: float, pos_count: int
    ) -> None:
        if drawdown < 0.01:
            return

        # Check thresholds from highest to lowest
        triggered = False
        for threshold in ALERT_THRESHOLDS:
            if drawdown >= threshold:
                already = self._was_alerted(ticker, threshold)
                if not already:
                    self._fire_alert(ticker, drawdown, threshold)
                    self._mark_alerted(ticker, threshold)
                triggered = True
                break

        if not triggered and ticker in self._alerted:
            del self._alerted[ticker]

        self.logger.save_watcher_event(
            ticker=ticker,
            drawdown_pct=drawdown,
            action_taken="monitored" if not triggered else "alerted",
        )

    def _fire_alert(self, ticker: str, drawdown: float, threshold: float) -> None:
        if threshold >= 0.07 and self.autonomy.can_place_stops():
            self._log("action", f"🛑 {ticker} at {drawdown*100:.1f}% — placing stop")
            self.logger.save_watcher_event(
                ticker=ticker,
                drawdown_pct=drawdown,
                action_taken="stop_placed",
                details=f"Auto stop at {drawdown*100:.1f}% drawdown (tier={self.autonomy.tier.value})",
            )
        elif threshold >= 0.07:
            self._log("alert", f"🛑 {ticker} at {drawdown*100:.1f}% — stop required")
        elif threshold >= 0.05:
            self._log("alert", f"🔶 {ticker} at {drawdown*100:.1f}% — decision needed")
        else:
            self._log("alert", f"⚠️ {ticker} at {drawdown*100:.1f}% — check thesis")

    def _was_alerted(self, ticker: str, threshold: float) -> bool:
        return threshold in self._alerted.get(ticker, set())

    def _accelerate_interval(self, max_drawdown: float) -> int:
        """Speed up watcher polls when drawdown enters warning band."""
        warn_pct = self._warn_threshold
        if warn_pct <= 0 or max_drawdown <= 0:
            return self.settings.watcher_interval
        # When drawdown exceeds warn threshold, switch to fast interval
        if max_drawdown >= warn_pct:
            return self._fast_interval
        return self.settings.watcher_interval

    def _mark_alerted(self, ticker: str, threshold: float) -> None:
        if ticker not in self._alerted:
            self._alerted[ticker] = set()
        self._alerted[ticker].add(threshold)

    @staticmethod
    def _is_market_hours() -> bool:
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:
            return False
        et_offset = -4 if time.localtime().tm_isdst else -5
        et_hour = now.hour + et_offset
        return 9 <= et_hour <= 15

    def _log(self, level: str, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] [{level.upper()}] {msg}", flush=True)

    def status(self) -> dict:
        return {
            "running": _RUNNING,
            "tier": self.autonomy.tier.value,
            "interval": self._interval,
            "kill_switch_state": self.kill_switch.state,
            "open_alerts": {t: list(t) for t, alerts in self._alerted.items() for t in [next(iter(alerts))]} if self._alerted else {},
        }


def _signal_handler(signum: int, frame) -> None:
    global _RUNNING
    _RUNNING = False


def run_watcher(settings: Settings) -> None:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    watcher = PositionWatcher(settings)
    watcher.run()
