"""
Shadow Account v1.

A shadow account mechanically follows every strategy signal and
tracks what *would have happened* vs what *did happen*.

The shadow portfolio is built from a backtest — it represents
the strategy executed with zero discretion, zero emotion,
zero override.  Comparing it to your journaled signals reveals
behavioral drift: missed entries, early exits, overtrading.

No broker calls.  No order placement.  Read-only analysis.
"""
from trading_lab.shadow.account import ShadowAccount, ShadowResult
from trading_lab.shadow.report import render_shadow_report

__all__ = ["ShadowAccount", "ShadowResult", "render_shadow_report"]
