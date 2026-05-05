"""Simulation Analytics — leaderboard, convergence, best extraction.

Phase 3 Milestone 5: Process simulation results, generate reports,
detect convergence, recommend adoption.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from trading_lab.core.config import PROJECT_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LeaderboardEntry:
    """One row in the simulation leaderboard."""

    rank: int
    agent_id: str
    final_equity: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    trades: int
    is_neural: bool
    alpha_vs_baseline: float  # (equity - baseline_equity) / baseline_equity


@dataclass(frozen=True)
class SimulationReport:
    """Full report from a simulation run."""

    sim_id: str
    timestamp: str
    tickers: list[str]
    agents: list[str]
    lookback_days: int
    best_agent: str
    best_sharpe: float
    baseline_sharpe: float
    alpha_pct: float
    convergence_day: int | None
    leaderboard: list[LeaderboardEntry]
    recommendation: str


class SimulationAnalytics:
    """Analyze simulation results and produce reports."""

    ALPHA_THRESHOLD = 0.05  # 5% alpha required for adoption recommendation
    SHARPE_THRESHOLD = 0.50  # Minimum Sharpe for recommendation

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(PROJECT_DIR / "trading_lab.sqlite3")
        self._ensure_tables()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyze(
        self,
        results: list,  # list[SimulationResult]
        sim_id: str,
        timestamp: str,
        tickers: list[str],
        lookback_days: int,
        baseline_id: str = "simple_momentum",
    ) -> SimulationReport:
        """Analyze simulation results and produce report."""
        if not results:
            return SimulationReport(
                sim_id=sim_id,
                timestamp=timestamp,
                tickers=tickers,
                agents=[],
                lookback_days=lookback_days,
                best_agent="",
                best_sharpe=0.0,
                baseline_sharpe=0.0,
                alpha_pct=0.0,
                convergence_day=None,
                leaderboard=[],
                recommendation="No results — simulation failed or no agents",
            )

        # Find baseline
        baseline = next((r for r in results if r.agent_id == baseline_id), results[0])
        baseline_equity = baseline.final_equity
        baseline_sharpe = baseline.sharpe

        # Build leaderboard
        leaderboard: list[LeaderboardEntry] = []
        for i, r in enumerate(results, 1):
            alpha = (r.final_equity - baseline_equity) / baseline_equity if baseline_equity > 0 else 0.0
            leaderboard.append(
                LeaderboardEntry(
                    rank=i,
                    agent_id=r.agent_id,
                    final_equity=r.final_equity,
                    sharpe=r.sharpe,
                    max_drawdown=r.max_drawdown,
                    win_rate=r.win_rate,
                    trades=r.trades,
                    is_neural=r.is_neural,
                    alpha_vs_baseline=alpha,
                )
            )

        best = results[0]
        alpha_pct = (best.final_equity - baseline_equity) / baseline_equity if baseline_equity > 0 else 0.0

        # Recommendation
        if alpha_pct >= self.ALPHA_THRESHOLD and best.sharpe >= self.SHARPE_THRESHOLD:
            if best.is_neural:
                recommendation = (
                    f"Adopt neural-augmented strategy '{best.agent_id}' "
                    f"(alpha {alpha_pct:.1%}, Sharpe {best.sharpe:.2f}). "
                    f"Export as .py and run through Phase 2 validator."
                )
            else:
                recommendation = (
                    f"Adopt variant '{best.agent_id}' "
                    f"(alpha {alpha_pct:.1%}, Sharpe {best.sharpe:.2f}). "
                    f"Run through Phase 2 adoption pipeline."
                )
        else:
            recommendation = (
                f"No adoption recommended. Best agent '{best.agent_id}' "
                f"has alpha {alpha_pct:.1%} (threshold {self.ALPHA_THRESHOLD:.0%}) "
                f"and Sharpe {best.sharpe:.2f} (threshold {self.SHARPE_THRESHOLD:.2f})."
            )

        report = SimulationReport(
            sim_id=sim_id,
            timestamp=timestamp,
            tickers=tickers,
            agents=[r.agent_id for r in results],
            lookback_days=lookback_days,
            best_agent=best.agent_id,
            best_sharpe=best.sharpe,
            baseline_sharpe=baseline_sharpe,
            alpha_pct=alpha_pct,
            convergence_day=None,  # Would require tracking day-by-day ranking
            leaderboard=leaderboard,
            recommendation=recommendation,
        )

        self._save_report(report, results)
        return report

    # ── Persistence ────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sim_id TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    tickers TEXT NOT NULL,
                    agents TEXT NOT NULL,
                    lookback_days INTEGER,
                    best_agent TEXT,
                    best_sharpe REAL,
                    baseline_sharpe REAL,
                    alpha_pct REAL,
                    convergence_day INTEGER,
                    report_path TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS simulation_agent_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sim_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    final_equity REAL,
                    sharpe REAL,
                    max_drawdown REAL,
                    win_rate REAL,
                    trades INTEGER,
                    is_neural INTEGER,
                    rank INTEGER
                )"""
            )

    def _save_report(self, report: SimulationReport, results: list) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO simulations
                (sim_id, timestamp, tickers, agents, lookback_days, best_agent,
                 best_sharpe, baseline_sharpe, alpha_pct, convergence_day, report_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.sim_id,
                    report.timestamp,
                    ",".join(report.tickers),
                    ",".join(report.agents),
                    report.lookback_days,
                    report.best_agent,
                    report.best_sharpe,
                    report.baseline_sharpe,
                    report.alpha_pct,
                    report.convergence_day,
                    None,
                ),
            )
            for entry in report.leaderboard:
                conn.execute(
                    """INSERT INTO simulation_agent_results
                    (sim_id, agent_id, final_equity, sharpe, max_drawdown, win_rate,
                     trades, is_neural, rank)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.sim_id,
                        entry.agent_id,
                        entry.final_equity,
                        entry.sharpe,
                        entry.max_drawdown,
                        entry.win_rate,
                        entry.trades,
                        1 if entry.is_neural else 0,
                        entry.rank,
                    ),
                )

    def get_report(self, sim_id: str) -> SimulationReport | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM simulations WHERE sim_id = ?", (sim_id,)
            ).fetchone()
            if not row:
                return None
            # Reconstruct (simplified — full reconstruction would need all fields)
            return SimulationReport(
                sim_id=row[1],
                timestamp=row[2],
                tickers=row[3].split(","),
                agents=row[4].split(","),
                lookback_days=row[5],
                best_agent=row[6] or "",
                best_sharpe=row[7] or 0.0,
                baseline_sharpe=row[8] or 0.0,
                alpha_pct=row[9] or 0.0,
                convergence_day=row[10],
                leaderboard=[],
                recommendation="",
            )

    def list_sims(self, limit: int = 10) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT sim_id, timestamp, best_agent, best_sharpe, alpha_pct
                    FROM simulations
                    ORDER BY timestamp DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                {
                    "sim_id": r[0],
                    "timestamp": r[1],
                    "best_agent": r[2],
                    "best_sharpe": r[3],
                    "alpha_pct": r[4],
                }
                for r in rows
            ]

    # ── Report Generation ─────────────────────────────────────────────────────

    def format_report(self, report: SimulationReport) -> str:
        """Format report as markdown string."""
        lines = [
            f"# Simulation Report: {report.sim_id}",
            f"",
            f"**Date:** {report.timestamp}",
            f"**Tickers:** {', '.join(report.tickers)}",
            f"**Lookback:** {report.lookback_days} days",
            f"**Agents:** {', '.join(report.agents)}",
            f"",
            f"## Leaderboard",
            f"",
            f"| Rank | Agent | Equity | Sharpe | Drawdown | Win% | Trades | Alpha |",
            f"|------|-------|--------|--------|----------|------|--------|-------|",
        ]
        for e in report.leaderboard:
            lines.append(
                f"| {e.rank} | {e.agent_id} | {e.final_equity:.4f} | {e.sharpe:.2f} | "
                f"{e.max_drawdown:.1%} | {e.win_rate:.0%} | {e.trades} | {e.alpha_vs_baseline:+.1%} |"
            )
        lines.extend([
            f"",
            f"## Recommendation",
            f"",
            f"{report.recommendation}",
            f"",
            f"**Best Agent:** {report.best_agent} (Sharpe {report.best_sharpe:.2f})",
            f"**Alpha vs Baseline:** {report.alpha_pct:+.1%}",
        ])
        return "\n".join(lines)
