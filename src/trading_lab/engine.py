from trading_lab.logger import SnapshotLogger
from trading_lab.models import Signal, OrderType, SignalAction, TimeValidity
from trading_lab.risk import RiskPolicy


class ExecutionEngine:
    def __init__(
        self,
        broker,
        risk_policy: RiskPolicy,
        logger: SnapshotLogger | None = None,
        auto_stop: bool = False,
    ) -> None:
        self.broker = broker
        self.risk_policy = risk_policy
        self.logger = logger
        self.auto_stop = auto_stop

    def handle_signal(self, signal: Signal, dry_run: bool = True):
        approved, reason = self.risk_policy.approve(signal)

        if self.logger is not None:
            self.logger.save_signal(
                signal,
                dry_run=dry_run,
                approved=approved,
                approval_reason=reason,
            )

        if not approved:
            return {
                "executed": False,
                "reason": reason,
                "signal": signal.__dict__,
            }

        result = self._dispatch_order(signal, dry_run)

        # Auto-place trailing stop on buy entries
        stop_result = None
        if (
            self.auto_stop
            and not dry_run
            and signal.action == SignalAction.BUY
            and signal.suggested_quantity > 0
        ):
            entry_price = self._estimate_entry_price(signal.ticker)
            if entry_price > 0:
                stop_price = entry_price * (1 - self.risk_policy.trailing_stop_pct)
                try:
                    stop_result = self.broker.stop_order(
                        ticker=signal.ticker,
                        quantity=-abs(signal.suggested_quantity),
                        stop_price=round(stop_price, 2),
                        dry_run=False,
                        time_validity=TimeValidity.GOOD_TILL_CANCEL.value,
                    )
                except Exception as e:
                    stop_result = {"error": str(e), "note": "Stop placement failed"}

        return {
            "executed": not dry_run,
            "reason": reason,
            "broker_result": result,
            "signal": signal.__dict__,
            "auto_stop_result": stop_result,
        }

    def _dispatch_order(self, signal: Signal, dry_run: bool) -> dict:
        ticker = signal.ticker
        quantity = signal.suggested_quantity
        order_type = signal.order_type

        if order_type == OrderType.LIMIT:
            return self.broker.limit_order(
                ticker=ticker,
                quantity=quantity,
                limit_price=signal.limit_price or 0,
                dry_run=dry_run,
                time_validity=signal.time_validity.value,
            )

        if order_type == OrderType.STOP:
            return self.broker.stop_order(
                ticker=ticker,
                quantity=quantity,
                stop_price=signal.stop_price or 0,
                dry_run=dry_run,
                time_validity=signal.time_validity.value,
            )

        if order_type == OrderType.STOP_LIMIT:
            return self.broker.stop_limit_order(
                ticker=ticker,
                quantity=quantity,
                stop_price=signal.stop_price or 0,
                limit_price=signal.limit_price or 0,
                dry_run=dry_run,
                time_validity=signal.time_validity.value,
            )

        return self.broker.market_order(
            ticker=ticker,
            quantity=quantity,
            dry_run=dry_run,
        )

    def _estimate_entry_price(self, ticker: str) -> float:
        """Current price for stop calculation.

        Delegates to the broker's price oracle so new tickers (not yet held)
        fall back to yfinance instead of returning 0 and producing a bogus
        zero-priced stop order.
        """
        getter = getattr(self.broker, "_get_current_price", None)
        if callable(getter):
            try:
                return float(getter(ticker) or 0)
            except Exception:
                return 0.0
        return 0.0
