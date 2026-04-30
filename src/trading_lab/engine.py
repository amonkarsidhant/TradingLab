from trading_lab.logger import SnapshotLogger
from trading_lab.models import Signal, OrderType, SignalAction
from trading_lab.risk import RiskPolicy


class ExecutionEngine:
    def __init__(
        self,
        broker,
        risk_policy: RiskPolicy,
        logger: SnapshotLogger | None = None,
    ) -> None:
        self.broker = broker
        self.risk_policy = risk_policy
        self.logger = logger

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

        return {
            "executed": not dry_run,
            "reason": reason,
            "broker_result": result,
            "signal": signal.__dict__,
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
