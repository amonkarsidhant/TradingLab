"""
Multi-agent review framework for Sid Trading Lab.

Agents analyze signals through different lenses (technical, fundamental,
bull/bear debate, risk review) and produce structured reports.  The
human is the final decision-maker — agents advise, they never execute.

Provider-agnostic: Anthropic, OpenAI, Ollama (local), and OpenRouter
are supported via a common LLMProvider interface.
"""
from trading_lab.agents.runner import AgentRunner
from trading_lab.agents.pipeline import ReviewPipeline, ReviewResult

__all__ = ["AgentRunner", "ReviewPipeline", "ReviewResult"]
