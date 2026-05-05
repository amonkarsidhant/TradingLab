"""Alpha Discovery & Multi-Agent Simulation (Phase 3).

Modules:
  - discovery: AlphaDiscoveryEngine — LLM-driven hypothesis generation
  - features: FeatureEngine — compute built-in + custom features from OHLCV
  - neural_signal: NeuralSignalModel — tiny MLP classifier on features
  - simulation: MultiAgentSimulation — run strategies against each other
  - analytics: SimulationAnalytics — leaderboard, reports, persistence
  - integration: AlphaIntegration — wire sim results into Phase 2 adoption

Public API:
  AlphaDiscoveryEngine, AlphaHypothesis,
  FeatureEngine, FeatureSet, compute_features_for_tickers,
  NeuralSignalModel, NeuralSignal, generate_labels_from_returns,
  MultiAgentSimulation, AgentState, SimulationResult,
  SimulationAnalytics, SimulationReport, LeaderboardEntry,
  AlphaIntegration
"""
from trading_lab.alpha.discovery import AlphaDiscoveryEngine, AlphaHypothesis
from trading_lab.alpha.features import FeatureEngine, FeatureSet, compute_features_for_tickers
from trading_lab.alpha.neural_signal import NeuralSignalModel, NeuralSignal, generate_labels_from_returns
from trading_lab.alpha.simulation import MultiAgentSimulation, AgentState, SimulationResult
from trading_lab.alpha.analytics import SimulationAnalytics, SimulationReport, LeaderboardEntry
from trading_lab.alpha.integration import AlphaIntegration

__all__ = [
    "AlphaDiscoveryEngine",
    "AlphaHypothesis",
    "FeatureEngine",
    "FeatureSet",
    "compute_features_for_tickers",
    "NeuralSignalModel",
    "NeuralSignal",
    "generate_labels_from_returns",
    "MultiAgentSimulation",
    "AgentState",
    "SimulationResult",
    "SimulationAnalytics",
    "SimulationReport",
    "LeaderboardEntry",
    "AlphaIntegration",
]
