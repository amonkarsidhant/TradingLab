"""Adoption Manager — git commit + swap active strategy + rollback support.

Phase 2 Milestone 4: Auto-adopt variants that pass validation, with git tags
for rollback points.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_lab.meta.variant_validator import VariantValidationResult
from trading_lab.registry.performance import StrategyPerformanceRegistry
from trading_lab.strategies import get_strategy, list_strategies, register_strategy
from trading_lab.strategies.base import Strategy

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class AdoptionResult:
    success: bool
    strategy_id: str
    action: str  # 'adopted', 'rollbacked', 'failed'
    git_commit: str | None
    pre_adopt_tag: str | None
    error: str | None


class AdoptionManager:
    """Manages strategy adoption lifecycle: adopt → observe → rollback."""

    VARIANTS_DIR = PROJECT_DIR / "variants"
    STRATEGIES_DIR = PROJECT_DIR / "src" / "trading_lab" / "strategies"

    def __init__(self) -> None:
        self.VARIANTS_DIR.mkdir(exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────────────

    def adopt(
        self,
        variant_source: str,
        variant_name: str,
        baseline_id: str,
        validation: VariantValidationResult,
        dry_run: bool = False,
    ) -> AdoptionResult:
        """Adopt a validated variant into the active strategy set.

        Steps:
        1. Save variant to variants/{name}_{ts}.py
        2. Git commit + tag pre-adoption baseline
        3. Copy to strategies/ dir
        4. Register in strategy registry
        5. Log to strategy_change_log
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pre_tag = f"pre-adopt-{baseline_id}-{ts}"
        commit_hash: str | None = None

        try:
            # 1. Save variant file
            variant_file = self.VARIANTS_DIR / f"{variant_name}_{ts}.py"
            variant_file.write_text(variant_source)

            if dry_run:
                return AdoptionResult(
                    success=True,
                    strategy_id=variant_name,
                    action="dry_run",
                    git_commit=None,
                    pre_adopt_tag=pre_tag,
                    error=None,
                )

            # 2. Git operations
            self._git_stage_all()
            self._git_tag(pre_tag)
            commit_hash = self._git_commit(
                f"feat(strategy): auto-adopt {variant_name}\n\n"
                f"- Baseline: {baseline_id}\n"
                f"- Sharpe diff: {validation.sharpe_diff:+.3f}\n"
                f"- Win rate diff: {validation.win_rate_diff:+.1%}\n"
                f"- Max DD delta: {validation.dd_delta:+.2f}%\n"
                f"- p-value: {validation.p_value}\n"
                f"- Composite score: {validation.composite_score:.3f}\n"
                f"- Pre-adoption tag: {pre_tag}"
            )

            # 3. Copy to strategies dir
            strategy_file = self.STRATEGIES_DIR / f"{variant_name}.py"
            strategy_file.write_text(variant_source)

            # 4. Register (requires import — done via CLI reload or restart)
            # We can't hot-reload in pure Python without importlib tricks,
            # so we write the file and rely on the next CLI invocation to pick it up.
            # For immediate use, we exec the source in a fresh namespace and register.
            self._register_variant(variant_source, variant_name)

            # 5. Log to strategy_change_log
            self._log_change(
                strategy_id=variant_name,
                action="adopt",
                baseline_id=baseline_id,
                validation=validation,
                commit_hash=commit_hash,
                pre_tag=pre_tag,
            )

            logger.info(
                "Adopted %s (commit=%s, tag=%s)", variant_name, commit_hash, pre_tag
            )
            return AdoptionResult(
                success=True,
                strategy_id=variant_name,
                action="adopted",
                git_commit=commit_hash,
                pre_adopt_tag=pre_tag,
                error=None,
            )

        except Exception as exc:
            logger.exception("Adoption failed for %s", variant_name)
            return AdoptionResult(
                success=False,
                strategy_id=variant_name,
                action="failed",
                git_commit=commit_hash,
                pre_adopt_tag=pre_tag,
                error=str(exc),
            )

    def rollback(
        self,
        variant_id: str,
        baseline_id: str,
        reason: str = "live_performance_degraded",
    ) -> AdoptionResult:
        """Rollback to baseline strategy.

        1. Git checkout pre-adoption tag
        2. Remove variant from strategies dir
        3. Git commit rollback
        4. Log to strategy_change_log
        """
        try:
            # Find pre-adoption tag
            tags = self._git_list_tags(f"pre-adopt-{baseline_id}-*")
            if not tags:
                return AdoptionResult(
                    success=False,
                    strategy_id=variant_id,
                    action="failed",
                    git_commit=None,
                    pre_adopt_tag=None,
                    error=f"No pre-adoption tag found for {baseline_id}",
                )
            latest_tag = sorted(tags)[-1]

            # Git checkout to rollback
            self._git_checkout_tag(latest_tag)

            # Remove variant file
            variant_file = self.STRATEGIES_DIR / f"{variant_id}.py"
            if variant_file.exists():
                variant_file.unlink()

            commit_hash = self._git_commit(
                f"revert(strategy): roll back {variant_id}\n\n"
                f"Reason: {reason}\n"
                f"Restored from tag: {latest_tag}"
            )

            self._log_change(
                strategy_id=variant_id,
                action="rollback",
                baseline_id=baseline_id,
                validation=None,
                commit_hash=commit_hash,
                pre_tag=latest_tag,
                reason=reason,
            )

            logger.info("Rolled back %s to %s (commit=%s)", variant_id, baseline_id, commit_hash)
            return AdoptionResult(
                success=True,
                strategy_id=variant_id,
                action="rollbacked",
                git_commit=commit_hash,
                pre_adopt_tag=latest_tag,
                error=None,
            )

        except Exception as exc:
            logger.exception("Rollback failed for %s", variant_id)
            return AdoptionResult(
                success=False,
                strategy_id=variant_id,
                action="failed",
                git_commit=None,
                pre_adopt_tag=None,
                error=str(exc),
            )

    # ── Internal ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _git_stage_all() -> None:
        subprocess.run(["git", "add", "-A"], cwd=PROJECT_DIR, check=True, capture_output=True)

    @staticmethod
    def _git_commit(message: str) -> str:
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
        )
        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _git_tag(tag: str) -> None:
        subprocess.run(
            ["git", "tag", "-a", tag, "-m", f"Pre-adoption baseline {tag}"],
            cwd=PROJECT_DIR,
            check=False,
            capture_output=True,
        )

    @staticmethod
    def _git_list_tags(pattern: str) -> list[str]:
        result = subprocess.run(
            ["git", "tag", "-l", pattern],
            cwd=PROJECT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        return [t for t in result.stdout.strip().split("\n") if t]

    @staticmethod
    def _git_checkout_tag(tag: str) -> None:
        # Reset to tag (destructive — should only be used on clean repo)
        subprocess.run(
            ["git", "reset", "--hard", tag],
            cwd=PROJECT_DIR,
            check=False,
            capture_output=True,
        )

    @staticmethod
    def _register_variant(source_code: str, name: str) -> None:
        """Exec variant source and register it dynamically."""
        namespace: dict[str, Any] = {
            "Signal": __import__("trading_lab.models", fromlist=["Signal"]).Signal,
            "SignalAction": __import__("trading_lab.models", fromlist=["SignalAction"]).SignalAction,
            "Strategy": Strategy,
            "register_strategy": register_strategy,
        }
        try:
            import numpy as np
            namespace["np"] = np
            namespace["numpy"] = np
        except ImportError:
            pass
        exec(compile(source_code, "<variant>", "exec"), namespace)
        logger.info("Registered variant %s dynamically", name)

    @staticmethod
    def _log_change(
        strategy_id: str,
        action: str,
        baseline_id: str,
        validation: VariantValidationResult | None,
        commit_hash: str | None,
        pre_tag: str | None,
        reason: str = "",
    ) -> None:
        from trading_lab.meta.change_log import ChangeLog
        ChangeLog().record(
            strategy_id=strategy_id,
            action=action,
            reason=reason or (validation.reason if validation else ""),
            baseline_hash=pre_tag,
            variant_hash=commit_hash,
            performance_before=0.0,  # Could query from registry
            performance_after=validation.sharpe_diff if validation else 0.0,
            regime_at_change="",
            llm_prompt="",
            llm_response="",
            composite_score=validation.composite_score if validation else 0.0,
            p_value=validation.p_value if validation else None,
        )
