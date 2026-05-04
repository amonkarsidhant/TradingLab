"""
Concentration guard — blocks buy signals when sector/asset concentration is too high.

Ported from go-trader correlation.go: warns when a single asset exceeds
concentration threshold or too many strategies share the same direction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_MAX_CONCENTRATION_PCT = 60.0
DEFAULT_MAX_SAME_DIRECTION_PCT = 75.0


@dataclass
class PositionExposure:
    """A single position's contribution to asset exposure."""
    ticker: str
    delta_usd: float  # signed: +long, -short
    strategy: str = ""


@dataclass
class AssetExposure:
    """Aggregated exposure for one asset across all strategies."""
    asset: str
    net_delta_usd: float = 0.0
    gross_delta_usd: float = 0.0
    positions: list[PositionExposure] = field(default_factory=list)
    concentration_pct: float = 0.0


@dataclass
class ConcentrationSnapshot:
    """Portfolio-level directional exposure snapshot."""
    timestamp: str
    assets: dict[str, AssetExposure] = field(default_factory=dict)
    portfolio_gross_usd: float = 0.0
    warnings: list[str] = field(default_factory=list)


class ConcentrationGuard:
    """Warns and optionally blocks when concentration limits are breached.

    Set max_concentration_pct to warn when a single asset exceeds this % of
    portfolio gross exposure.  Set max_same_direction_pct to warn when more
    than this % of strategies on an asset share a direction.
    """

    def __init__(
        self,
        max_concentration_pct: float = DEFAULT_MAX_CONCENTRATION_PCT,
        max_same_direction_pct: float = DEFAULT_MAX_SAME_DIRECTION_PCT,
        block_on_warning: bool = False,
    ):
        self.max_concentration_pct = max_concentration_pct
        self.max_same_direction_pct = max_same_direction_pct
        self.block_on_warning = block_on_warning
        self._last_warnings: list[str] = []

    def check(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, float],
    ) -> tuple[bool, list[str]]:
        """Returns (allowed, warnings).  allowed=False when guard is configured to block and a warning fires."""
        snapshot = self._compute(positions, prices)
        self._last_warnings = snapshot.warnings
        allowed = not (self.block_on_warning and snapshot.warnings)
        return allowed, snapshot.warnings

    def _compute(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, float],
    ) -> ConcentrationSnapshot:
        snap = ConcentrationSnapshot(timestamp=_now_iso())

        # Build per-asset exposure from position list
        for p in positions:
            ticker = p.get("ticker", "")
            qty = float(p.get("quantity", 0))
            avg_price = float(p.get("avg_price", 0))
            strategy = p.get("strategy", "")
            if not ticker or qty <= 0 or avg_price <= 0:
                continue

            price = prices.get(ticker, 0)
            if price <= 0:
                continue

            delta_usd = qty * price
            side = str(p.get("side", "")).strip().lower()
            if side == "short":
                delta_usd = -delta_usd

            asset = _extract_asset(ticker)
            if asset not in snap.assets:
                snap.assets[asset] = AssetExposure(asset=asset)
            ae = snap.assets[asset]
            ae.positions.append(PositionExposure(ticker=ticker, delta_usd=delta_usd, strategy=strategy))
            ae.net_delta_usd += delta_usd
            ae.gross_delta_usd += abs(delta_usd)

        # Portfolio gross
        for ae in snap.assets.values():
            snap.portfolio_gross_usd += ae.gross_delta_usd

        # Concentration + same-direction checks
        if snap.portfolio_gross_usd > 0:
            for ae in snap.assets.values():
                ae.concentration_pct = abs(ae.net_delta_usd) / snap.portfolio_gross_usd * 100

                # Concentration warning
                if ae.concentration_pct > self.max_concentration_pct:
                    direction = "long" if ae.net_delta_usd > 0 else "short"
                    snap.warnings.append(
                        f"{ae.asset} concentration {ae.concentration_pct:.0f}% "
                        f"(net {direction} ${abs(ae.net_delta_usd):.0f}) exceeds "
                        f"{self.max_concentration_pct:.0f}% threshold"
                    )

                # Same-direction warning
                if len(ae.positions) >= 2:
                    longs = sum(1 for pe in ae.positions if pe.delta_usd > 0)
                    shorts = sum(1 for pe in ae.positions if pe.delta_usd < 0)
                    max_same = longs if longs >= shorts else shorts
                    direction = "long" if longs >= shorts else "short"
                    same_pct = max_same / len(ae.positions) * 100
                    if same_pct > self.max_same_direction_pct:
                        snap.warnings.append(
                            f"{ae.asset}: {max_same}/{len(ae.positions)} strategies "
                            f"{direction} ({same_pct:.0f}%) exceeds "
                            f"{self.max_same_direction_pct:.0f}% same-direction threshold"
                        )

        return snap

    @property
    def last_warnings(self) -> list[str]:
        return self._last_warnings


def _extract_asset(ticker: str) -> str:
    """Extract base asset from T212 ticker (e.g. 'AAPL_US_EQ' -> 'AAPL')."""
    base = ticker.split("_")[0] if "_" in ticker else ticker
    return base.upper()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
