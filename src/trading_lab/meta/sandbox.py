"""Syntax Sandbox — validate generated strategy code before disk write.

Phase 2 Milestone 2: compile() + ast.parse() + forbidden import checks.
"""
from __future__ import annotations

import ast
import compileall
import logging
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from trading_lab.models import Signal, SignalAction
from trading_lab.strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    valid: bool
    error: str | None
    test_signal: dict | None
    forbidden_imports: list[str]
    has_generate_signal: bool
    signal_action_valid: bool


class SyntaxSandbox:
    """Validates strategy source code in an isolated namespace."""

    # Imports that are NEVER allowed in generated strategy code
    FORBIDDEN_IMPORTS = {
        "os", "sys", "subprocess", "pathlib", "shutil", "socket",
        "urllib", "http", "requests", "ftplib", "smtplib",
        "eval", "exec", "compile", "open", "input",
        "importlib", "inspect", "pickle", "marshal",
    }

    # Safe builtins for exec()
    SAFE_BUILTINS = {
        "abs", "all", "any", "bool", "dict", "enumerate", "filter",
        "float", "int", "len", "list", "map", "max", "min", "range",
        "round", "set", "slice", "sorted", "str", "sum", "tuple",
        "zip", "True", "False", "None", "__import__",
    }

    ALLOWED_IMPORTS = {
        "trading_lab.models",
        "trading_lab.strategies.base",
        "numpy",
        "__future__",
    }

    @classmethod
    def validate(cls, source_code: str) -> SandboxResult:
        """Full validation pipeline: syntax → imports → instantiation → test call.

        Returns SandboxResult with detailed pass/fail for each layer.
        """
        forbidden: list[str] = []
        test_signal: dict | None = None
        has_gs = False
        action_valid = False

        # Layer 1: Syntax compilation
        try:
            compile(source_code, "<variant>", "exec")
        except SyntaxError as exc:
            return SandboxResult(
                valid=False,
                error=f"SyntaxError: {exc}",
                test_signal=None,
                forbidden_imports=[],
                has_generate_signal=False,
                signal_action_valid=False,
            )

        # Layer 2: AST parse + forbidden import check
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            return SandboxResult(
                valid=False,
                error=f"AST parse error: {exc}",
                test_signal=None,
                forbidden_imports=[],
                has_generate_signal=False,
                signal_action_valid=False,
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if mod not in cls.ALLOWED_IMPORTS and mod.split(".")[0] not in cls.ALLOWED_IMPORTS:
                        forbidden.append(mod)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod not in cls.ALLOWED_IMPORTS and mod.split(".")[0] not in cls.ALLOWED_IMPORTS:
                    forbidden.append(mod)

        if forbidden:
            return SandboxResult(
                valid=False,
                error=f"Forbidden imports detected: {forbidden}",
                test_signal=None,
                forbidden_imports=forbidden,
                has_generate_signal=False,
                signal_action_valid=False,
            )

        # Layer 3: Instantiate in isolated namespace
        namespace: dict[str, Any] = {}
        # Build restricted builtins dict
        if isinstance(__builtins__, dict):
            builtins_dict = {name: __builtins__[name] for name in cls.SAFE_BUILTINS if name in __builtins__}
        else:
            builtins_dict = {}
            for name in cls.SAFE_BUILTINS:
                if hasattr(__builtins__, name):
                    builtins_dict[name] = getattr(__builtins__, name)
        namespace["__builtins__"] = builtins_dict
        namespace["Signal"] = Signal
        namespace["SignalAction"] = SignalAction
        namespace["Strategy"] = Strategy
        # Add numpy if available (strategies may use it)
        try:
            import numpy as np
            namespace["np"] = np
            namespace["numpy"] = np
        except ImportError:
            pass

        try:
            exec(compile(tree, "<variant>", "exec"), namespace)
        except Exception as exc:
            return SandboxResult(
                valid=False,
                error=f"Exec error: {exc}",
                test_signal=None,
                forbidden_imports=[],
                has_generate_signal=False,
                signal_action_valid=False,
            )

        # Layer 4: Find strategy class + test call
        strategy_cls = None
        for obj in namespace.values():
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                strategy_cls = obj
                break

        if strategy_cls is None:
            return SandboxResult(
                valid=False,
                error="No Strategy subclass found in generated code",
                test_signal=None,
                forbidden_imports=[],
                has_generate_signal=False,
                signal_action_valid=False,
            )

        has_gs = hasattr(strategy_cls, "generate_signal")

        # Layer 5: Test call with synthetic data
        try:
            instance = strategy_cls()
            synthetic = [100.0 + i * 0.5 for i in range(30)]  # uptrend
            signal = instance.generate_signal(ticker="TEST", prices=synthetic)
            if signal is None:
                raise ValueError("generate_signal returned None")
            test_signal = {
                "action": signal.action.value,
                "confidence": signal.confidence,
                "reason": signal.reason,
            }
            action_valid = signal.action in (SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD)
        except Exception as exc:
            return SandboxResult(
                valid=False,
                error=f"Test call failed: {exc}",
                test_signal=None,
                forbidden_imports=[],
                has_generate_signal=has_gs,
                signal_action_valid=False,
            )

        return SandboxResult(
            valid=True,
            error=None,
            test_signal=test_signal,
            forbidden_imports=[],
            has_generate_signal=has_gs,
            signal_action_valid=action_valid,
        )

    @classmethod
    def quick_check(cls, source_code: str) -> bool:
        """Return True only if source passes all layers."""
        return cls.validate(source_code).valid


def sandbox_test(source_code: str) -> dict:
    """CLI entry point. Returns dict for JSON serialization."""
    result = SyntaxSandbox.validate(source_code)
    return {
        "valid": result.valid,
        "error": result.error,
        "test_signal": result.test_signal,
        "forbidden_imports": result.forbidden_imports,
        "has_generate_signal": result.has_generate_signal,
        "signal_action_valid": result.signal_action_valid,
    }
