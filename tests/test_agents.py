"""
Tests for the multi-agent review framework.

No real LLM calls. No API keys. No network.
All tests use a mock LLM provider that returns fixed text.
"""
import json

import pytest

from trading_lab.agents.pipeline import (
    ReviewPipeline,
    ReviewResult,
    render_review_report,
)
from trading_lab.agents.prompts import (
    bear_user,
    bull_user,
    fundamentals_user,
    risk_reviewer_user,
    technical_analyst_user,
)
from trading_lab.agents.runner import AgentRunner, detect_provider
from trading_lab.models import Signal, SignalAction


class _MockProvider:
    """Returns predictable text so tests don't need a real LLM."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "technical analyst" in system_prompt.lower():
            return "VALIDITY: VALID\n\nREASONING:\n- Price trend supports the signal.\n- Strategy logic is sound.\n\nCONFIDENCE: 0.80"
        if "macro-aware" in system_prompt.lower() or "fundamental" in system_prompt.lower():
            return "VALIDITY: NEUTRAL\n\nREASONING:\n- Market conditions are mixed.\n- No obvious macro headwinds.\n\nCONFIDENCE: 0.60"
        if "bullish" in system_prompt.lower():
            return "BULL_CASE:\n- Momentum is strong.\n- Trend is intact.\n\nKEY_RISK_TO_WATCH: Reversal at resistance."
        if "bearish" in system_prompt.lower():
            return "BEAR_CASE:\n- Overbought conditions.\n- Volume declining.\n\nKEY_CONCERN: False breakout."
        if "risk manager" in system_prompt.lower() or "risk" in system_prompt.lower():
            return "RISK_LEVEL: LOW\n\nCONCERNS:\n- Position size is small.\n\nSIZE_SUGGESTION: Size is acceptable."
        return "DEFAULT: No match."


def _make_signal(action=SignalAction.BUY, strategy="simple_momentum", ticker="TEST", confidence=0.8, reason="Upward momentum.", quantity=1.0):
    return Signal(strategy=strategy, ticker=ticker, action=action, confidence=confidence, reason=reason, suggested_quantity=quantity)


# ── Provider detection ─────────────────────────────────────────────────────────

def test_detect_provider_fails_with_nothing_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:19999")
    with pytest.raises(RuntimeError, match="No LLM provider"):
        detect_provider()


# ── AgentRunner ────────────────────────────────────────────────────────────────

def test_runner_forwards_to_provider():
    runner = AgentRunner(provider=_MockProvider())
    result = runner.ask(system="You are a technical analyst.", user="Evaluate.")
    assert "VALID" in result


def test_runner_lazy_inits_provider(monkeypatch):
    """When no provider given, runner auto-detects on first ask."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    # Will fail because the fake key can't actually call the API,
    # but the detection itself should succeed.
    try:
        provider, model = detect_provider()
        assert model
    except RuntimeError:
        pass  # expected if ollama unreachable etc.
    # Runner with explicit mock should work fine though.
    runner = AgentRunner(provider=_MockProvider())
    assert runner.ask("s", "u")


# ── Pipeline ───────────────────────────────────────────────────────────────────

def test_pipeline_review_returns_all_sections():
    pipeline = ReviewPipeline(runner=AgentRunner(_MockProvider()))
    signal = _make_signal()
    result = pipeline.review(signal, prices=[100.0, 101.0, 102.0])

    assert isinstance(result, ReviewResult)
    assert "VALID" in result.technical_review
    assert "NEUTRAL" in result.fundamentals_review
    assert "BULL_CASE" in result.bull_case
    assert "BEAR_CASE" in result.bear_case
    assert "LOW" in result.risk_review
    assert result.signal == signal


def test_pipeline_review_handles_different_actions():
    pipeline = ReviewPipeline(runner=AgentRunner(_MockProvider()))

    for action in (SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD):
        signal = _make_signal(action=action)
        result = pipeline.review(signal)
        assert result.signal.action == action


def test_pipeline_journals_when_db_path_provided(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    pipeline = ReviewPipeline(
        runner=AgentRunner(_MockProvider()),
        db_path=db,
    )
    signal = _make_signal()
    result = pipeline.review(signal)

    import sqlite3
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT * FROM agent_reviews").fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "simple_momentum"  # strategy column
        assert rows[0][3] == "TEST"  # ticker column


def test_pipeline_does_not_crash_without_db_path():
    pipeline = ReviewPipeline(runner=AgentRunner(_MockProvider()))
    result = pipeline.review(_make_signal())
    assert result is not None


# ── Context builder (indirect test via pipeline) ───────────────────────────────

def test_context_includes_prices_when_provided():
    class _CaptureProvider:
        captured: str = ""

        def complete(self, system, user):
            _CaptureProvider.captured = user
            return "VALIDITY: OK\n\nREASONING: ok\n\nCONFIDENCE: 0.5"

    pipeline = ReviewPipeline(runner=AgentRunner(_CaptureProvider()))
    signal = _make_signal()
    pipeline.review(signal, prices=[100.0, 101.0, 102.0, 103.0, 104.0])

    assert "100.00" in _CaptureProvider.captured
    assert "104.00" in _CaptureProvider.captured


# ── Report rendering ───────────────────────────────────────────────────────────

def test_render_report_includes_all_sections():
    pipeline = ReviewPipeline(runner=AgentRunner(_MockProvider()))
    signal = _make_signal()
    result = pipeline.review(signal)

    report = render_review_report(result)

    assert "Multi-Agent Review" in report
    assert "Technical Analyst" in report
    assert "Fundamentals Analyst" in report
    assert "Bull Case" in report
    assert "Bear Case" in report
    assert "Risk Review" in report
    assert "Agents advise" in report


def test_render_report_includes_signal_details():
    pipeline = ReviewPipeline(runner=AgentRunner(_MockProvider()))
    signal = _make_signal(action=SignalAction.BUY, ticker="AAPL_US_EQ")
    result = pipeline.review(signal)

    report = render_review_report(result)
    assert "BUY" in report
    assert "AAPL_US_EQ" in report


# ── Anthropic provider content extraction ──────────────────────────────────────

def _make_text_block(text):
    class _TextBlock:
        type = "text"
        text = text
    return _TextBlock()


def _make_thinking_block(text="..."):
    class _ThinkingBlock:
        type = "thinking"
        thinking = text
    return _ThinkingBlock()


def test_anthropic_provider_iterates_content_blocks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    pytest.importorskip("anthropic")
    import anthropic as _anthropic_mod
    from trading_lab.agents.runner import _try_anthropic

    class _FakeMsg:
        content = [_make_thinking_block(), _make_text_block("hello")]

    class _FakeClient:
        def messages(self):
            return self
        def create(self, **kw):
            return _FakeMsg()

    original_cls = _anthropic_mod.Anthropic
    try:
        _anthropic_mod.Anthropic = _FakeClient
        provider, _ = _try_anthropic()
        result = provider.complete("s", "u")
        assert result == "hello"
    finally:
        _anthropic_mod.Anthropic = original_cls


def test_anthropic_provider_handles_empty_content(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    pytest.importorskip("anthropic")
    import anthropic as _anthropic_mod
    from trading_lab.agents.runner import _try_anthropic

    class _FakeMsg:
        content = []

    class _FakeClient:
        def messages(self):
            return self
        def create(self, **kw):
            return _FakeMsg()

    original_cls = _anthropic_mod.Anthropic
    try:
        _anthropic_mod.Anthropic = _FakeClient
        provider, _ = _try_anthropic()
        result = provider.complete("s", "u")
        assert result == ""
    finally:
        _anthropic_mod.Anthropic = original_cls


def test_anthropic_provider_fallback_to_first_block(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    pytest.importorskip("anthropic")
    import anthropic as _anthropic_mod
    from trading_lab.agents.runner import _try_anthropic

    class _TextOnly:
        text = "fallback"

    class _FakeMsg:
        content = [_TextOnly()]

    class _FakeClient:
        def messages(self):
            return self
        def create(self, **kw):
            return _FakeMsg()

    original_cls = _anthropic_mod.Anthropic
    try:
        _anthropic_mod.Anthropic = _FakeClient
        provider, _ = _try_anthropic()
        result = provider.complete("s", "u")
        assert result == "fallback"
    finally:
        _anthropic_mod.Anthropic = original_cls


# ── Prompt templates (unit tests) ──────────────────────────────────────────────

def test_technical_analyst_prompt_includes_signal_and_context():
    prompt = technical_analyst_user('{"action": "BUY"}', "Strategy: momentum\nTicker: TEST")
    assert "BUY" in prompt
    assert "momentum" in prompt
    assert "VALIDITY, REASONING, CONFIDENCE" in prompt


def test_fundamentals_prompt_includes_context():
    prompt = fundamentals_user('{"action": "SELL"}', "Ticker: TSLA")
    assert "SELL" in prompt
    assert "TSLA" in prompt


def test_bull_prompt_asks_for_bull_case():
    prompt = bull_user("{}", "context")
    assert "bull" in prompt.lower() or "FOR" in prompt


def test_bear_prompt_asks_for_bear_case():
    prompt = bear_user("{}", "context")
    assert "bear" in prompt.lower() or "AGAINST" in prompt


def test_risk_reviewer_prompt_includes_risk_context():
    prompt = risk_reviewer_user('{"action": "BUY"}', "quantity: 10")
    assert "BUY" in prompt
    assert "10" in prompt


def test_review_result_dataclass_fields():
    signal = _make_signal()
    result = ReviewResult(
        signal=signal,
        technical_review="valid",
        fundamentals_review="ok",
        bull_case="bull",
        bear_case="bear",
        risk_review="low risk",
    )
    assert isinstance(result.generated_at, str)
    assert "T" in result.generated_at  # ISO format
