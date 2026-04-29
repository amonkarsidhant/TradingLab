"""
Agentic Trading — autonomous portfolio management for demo environment.

This is a learning/entertainment system. All orders go to T212 demo.
No real money. AI suggests, code executes, human can audit.
"""
from trading_lab.agentic.portfolio import PortfolioManager
from trading_lab.agentic.scorer import SignalScorer

__all__ = ["PortfolioManager", "SignalScorer"]
