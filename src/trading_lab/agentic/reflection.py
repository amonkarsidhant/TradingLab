"""
MungerReflectionEngine — constant portfolio introspection.

Applies Charlie Munger's mental model toolkit:
1. Circle of Competence check — do we understand this thesis?
2. Inversion — what kills a position? Is it headed there?
3. Concentration risk — are we really diversified?
4. Robustness check — is the edge real or overfitted?
5. Lollapalooza — are multiple forces aligning against us?

Triggered daily (market close) and on-demand via /reflect.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trading_lab.agentic.market_regime import MarketRegimeDetector
from trading_lab.agentic.portfolio import PortfolioManager, PortfolioState
from trading_lab.config import Settings
from trading_lab.universes import SP500_BY_SECTOR


# Reverse index: T212 ticker → GICS sector. Built once at import time.
_TICKER_TO_SECTOR: dict[str, str] = {
    ticker: sector
    for sector, tickers in SP500_BY_SECTOR.items()
    for ticker in tickers
}

# Fired when any single sector exceeds this share of portfolio value.
_SECTOR_CONCENTRATION_THRESHOLD_PCT = 50.0


@dataclass
class PositionCritique:
    ticker: str
    name: str
    pnl_pct: float
    pct_of_portfolio: float
    days_held: int
    is_concentrated: bool
    is_drawdown_danger: bool
    is_outside_circle: bool
    thesis_strength: str  # strong / questionable / weak
    munger_verdict: str
    action: str  # HOLD / TRIM / CUT / ADD


@dataclass
class RegimeSummary:
    regime: str
    description: str
    cash_target_pct: float
    position_size_pct: float
    recommended_stop_pct: float
    recommended_strategies: list[str]


@dataclass
class ReflectionReport:
    portfolio_pnl_pct: float
    cash_pct: float
    regime: RegimeSummary
    critiques: list[PositionCritique]
    concentration_flag: bool
    sector_exposure: dict[str, float]
    not_to_do: list[str]
    munger_grade: str  # A-F


# Hard-coded circle of competence: what we understand
_OUTSIDE_CIRCLE = {
    "biotech", "pharma", "early-stage", "crypto", "options",
    "futures", "leveraged", "penny", "spin-off", "blank-check",
}


# Not-to-do list (enforced by reflection)
_NOT_TO_DO = [
    "Do not add to a losing position to 'average down'.",
    "Do not trade in the 24 hours before FOMC decisions.",
    "Do not chase a stock up more than 15% without a pullback.",
    "Do not sell a winner to buy a loser.",
    "Do not open a position without knowing the exit price.",
    "Do not let a single sector exceed 50% of portfolio.",
    "Do not trade for 'action' — every trade needs a written thesis.",
]


class MungerReflectionEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pm = PortfolioManager(settings)
        self.regime_detector = MarketRegimeDetector()

    def reflect(self) -> ReflectionReport:
        state = self.pm.state()
        regime = self._detect_regime(state)
        critiques = [self._critique_position(p, state) for p in state.positions]
        concentration_flag, sector_exposure = self._check_concentration(state)
        not_to_do = list(_NOT_TO_DO)

        # Grade
        munger_grade = self._grade(critiques, state, regime)

        # Real cost basis = sum(avg_price * quantity) across positions; avoids
        # cash-flow noise that breaks (total_value - unrealized_pnl).
        cost_basis = sum(p.avg_price * p.quantity for p in state.positions)
        pnl_pct = (state.unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        return ReflectionReport(
            portfolio_pnl_pct=round(pnl_pct, 2),
            cash_pct=round(state.cash / max(state.total_value, 1) * 100, 2),
            regime=regime,
            critiques=critiques,
            concentration_flag=concentration_flag,
            sector_exposure=sector_exposure,
            not_to_do=not_to_do,
            munger_grade=munger_grade,
        )

    def _detect_regime(self, state: PortfolioState) -> RegimeSummary:
        # Try to get SPY prices for regime detection, fall back to portfolio-based estimate
        try:
            from trading_lab.data.market_data import make_provider
            provider = make_provider(
                source="yfinance", ticker="SPY",
                cache_db=self.settings.db_path.replace(".sqlite3", "_cache.sqlite3"),
            )
            prices = provider.get_prices(ticker="SPY", lookback=60)
            regime_params = self.regime_detector.detect(prices)
        except Exception:
            regime_params = self.regime_detector._default_params()

        return RegimeSummary(
            regime=regime_params.regime,
            description=regime_params.description,
            cash_target_pct=10.0 * regime_params.cash_reserve_multiplier,
            position_size_pct=20.0 * regime_params.position_size_multiplier,
            recommended_stop_pct=regime_params.trailing_stop_pct * 100,
            recommended_strategies=regime_params.preferred_strategies,
        )

    def _critique_position(
        self, position: Any, state: PortfolioState
    ) -> PositionCritique:
        ticker = position.ticker
        name = self._position_name(ticker)
        pnl_pct = (
            (position.current_price - position.avg_price) / max(position.avg_price, 1)
        ) * 100 if position.avg_price > 0 else 0
        pct_of_portfolio = (position.current_value / max(state.total_value, 1)) * 100
        drawdown = self.pm.position_drawdown(position)
        is_high_drawdown = drawdown >= 0.05

        # Circle of competence
        inside_circle = not any(
            kw in ticker.lower() or kw in name.lower()
            for kw in _OUTSIDE_CIRCLE
        )

        # Thesis strength heuristic
        if pnl_pct < -5:
            thesis_strength = "weak"
        elif pnl_pct < -2:
            thesis_strength = "questionable"
        elif is_high_drawdown:
            thesis_strength = "questionable"
        else:
            thesis_strength = "strong"

        # Munger verdict
        if pct_of_portfolio > 20:
            verdict = "Overweight. Trim to 15%."
            action = "TRIM"
        elif pnl_pct < -5:
            verdict = f"Down {pnl_pct:.1f}%. Your thesis is being questioned by the market."
            action = "CUT"
        elif is_high_drawdown and pnl_pct < 0:
            verdict = f"Floating loss of {pnl_pct:.1f}%. Are you hoping or analyzing?"
            action = "MONITOR"
        elif position.quantity_in_pies > 0 and position.quantity_available < position.quantity:
            verdict = "Some shares locked in pies. Check quantityAvailableForTrading before selling."
            action = "MONITOR"
        elif pnl_pct > 15:
            verdict = f"Up {pnl_pct:.1f}%. Munger says: 'The first rule of compounding is never interrupt it unnecessarily.' But consider trimming 50%."
            action = "TRIM"
        else:
            verdict = "Within expected range. Let it ride."
            action = "HOLD"

        return PositionCritique(
            ticker=ticker,
            name=name,
            pnl_pct=round(pnl_pct, 2),
            pct_of_portfolio=round(pct_of_portfolio, 2),
            days_held=self._days_held(getattr(position, "created_at", "")),
            is_concentrated=pct_of_portfolio > 20,
            is_drawdown_danger=is_high_drawdown,
            is_outside_circle=not inside_circle,
            thesis_strength=thesis_strength,
            munger_verdict=verdict,
            action=action,
        )

    @staticmethod
    def _days_held(created_at: str) -> int:
        if not created_at:
            return 0
        try:
            ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - ts
            return max(delta.days, 0)
        except Exception:
            return 0

    def _position_name(self, ticker: str) -> str:
        try:
            inst = self.pm.client._instrument_cache.get(ticker)
            if inst:
                return inst.get("name", ticker)
        except Exception:
            pass
        return ticker

    def _check_concentration(
        self, state: PortfolioState
    ) -> tuple[bool, dict[str, float]]:
        sectors: dict[str, float] = {}
        for p in state.positions:
            sector = self._sector_for(p.ticker)
            share = (p.current_value / max(state.total_value, 1)) * 100
            sectors[sector] = sectors.get(sector, 0) + share

        breached = [s for s, pct in sectors.items()
                    if pct > _SECTOR_CONCENTRATION_THRESHOLD_PCT and s != "Other"]
        return bool(breached), sectors

    @staticmethod
    def _sector_for(ticker: str) -> str:
        """Look up a T212 ticker's GICS sector via the curated S&P 500 map."""
        return _TICKER_TO_SECTOR.get(ticker, "Other")

    @staticmethod
    def _grade(critiques: list[PositionCritique], state: PortfolioState, regime: RegimeSummary) -> str:
        issues = 0
        for c in critiques:
            if c.action == "CUT":
                issues += 2
            elif c.action == "TRIM":
                issues += 1
            elif c.action == "MONITOR" and c.is_drawdown_danger:
                issues += 1
        if state.cash / max(state.total_value, 1) > 0.5:
            issues += 1  # too much cash
        if issues == 0:
            return "A"
        if issues <= 2:
            return "B"
        if issues <= 4:
            return "C"
        return "D"

    def format_reflection(self, report: ReflectionReport) -> str:
        lines = []

        lines.append("🧠 **Bull's Munger Reflection**")
        lines.append("")

        # Grade
        grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "🔴"}
        lines.append(f"{grade_emoji.get(report.munger_grade, '⚪')} **Portfolio Grade: {report.munger_grade}**")
        lines.append(f"P&L: {report.portfolio_pnl_pct:+.2f}%  |  Cash: {report.cash_pct:.1f}%")
        lines.append("")

        # Regime
        lines.append(f"📊 **Regime: {report.regime.regime}**")
        lines.append(f"{report.regime.description}")
        lines.append(f"Target cash: {report.regime.cash_target_pct:.0f}%  |  Position size: {report.regime.position_size_pct:.0f}%")
        lines.append(f"Stop: {report.regime.recommended_stop_pct:.0f}%  |  Prefer: {', '.join(report.regime.recommended_strategies)}")
        lines.append("")

        # Positions
        lines.append("**Positions:**")
        for c in report.critiques:
            icon = "🛑" if c.action == "CUT" else ("⚠️" if c.action == "TRIM" else ("👀" if c.action == "MONITOR" else "✅"))
            lines.append(f"{icon} **{c.ticker}** ({c.name}) — {c.pnl_pct:+.2f}%, {c.pct_of_portfolio:.1f}% of portfolio")
            lines.append(f"   *{c.munger_verdict}*")
        lines.append("")

        # Concentration
        if report.concentration_flag:
            breached = [s for s, p in report.sector_exposure.items()
                        if p > _SECTOR_CONCENTRATION_THRESHOLD_PCT and s != "Other"]
            lines.append(f"⚠️ **Concentration Risk:** sector(s) over {_SECTOR_CONCENTRATION_THRESHOLD_PCT:.0f}% — {', '.join(breached)}")
            for sector, pct in sorted(report.sector_exposure.items(), key=lambda x: -x[1]):
                lines.append(f"   {sector}: {pct:.1f}%")
            lines.append("")

        # Not-to-do list
        lines.append("📋 **Not-To-Do List (Munger's Best Tool):**")
        for rule in report.not_to_do:
            lines.append(f"   • {rule}")

        return "\n".join(lines)
