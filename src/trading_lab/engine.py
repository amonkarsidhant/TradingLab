from trading_lab.logger import SnapshotLogger
from trading_lab.models import Signal
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

        result = self.broker.market_order(
            ticker=signal.ticker,
            quantity=signal.suggested_quantity,
            dry_run=dry_run,
        )

        return {
            "executed": not dry_run,
            "reason": reason,
            "broker_result": result,
            "signal": signal.__dict__,
        }
