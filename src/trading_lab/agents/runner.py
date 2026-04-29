"""LLM provider abstraction and agent runner.

Supports Anthropic, OpenAI, Ollama (local), and OpenRouter through
a common complete() interface.  Providers are discovered at runtime
so no single SDK is a hard dependency.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMProvider(Protocol):
    """A thing that can call an LLM and return text."""

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


def detect_provider() -> tuple[LLMProvider, str]:
    """Auto-detect an available provider from environment variables.

    Checks in order: anthropic, openrouter, openai, ollama.
    Returns (provider, model_name).
    Raises RuntimeError if no provider is configured.
    """
    providers: list[tuple[str, str, callable]] = [
        ("anthropic", "ANTHROPIC_API_KEY", _try_anthropic),
        ("openrouter", "OPENROUTER_API_KEY", _try_openrouter),
        ("openai", "OPENAI_API_KEY", _try_openai),
        ("ollama", "", _try_ollama),
    ]

    for name, env_var, factory in providers:
        try:
            provider, model = factory()
            logger.info("Using %s provider (model=%s)", name, model)
            return provider, model
        except Exception as exc:
            logger.debug("Provider %s unavailable: %s", name, exc)

    raise RuntimeError(
        "No LLM provider configured. Set one of:\n"
        "  ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,\n"
        "  or ensure Ollama is running at OLLAMA_BASE_URL (default http://localhost:11434)."
    )


class AgentRunner:
    """Sends prompts to an LLM and returns the response.

    Usage:
        runner = AgentRunner()
        result = runner.ask(system="You are a technical analyst.",
                             user="Evaluate this signal: ...")
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider, _ = detect_provider()
        return self._provider

    def ask(self, system: str, user: str) -> str:
        return self.provider.complete(system, user)


# ── Anthropic ──────────────────────────────────────────────────────────────────

def _try_anthropic() -> tuple[LLMProvider, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("AGENT_MODEL") or "claude-sonnet-4-6"

    class _AnthropicProvider:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            msg = client.messages.create(
                model=model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return msg.content[0].text

    return _AnthropicProvider(), model


# ── OpenAI ─────────────────────────────────────────────────────────────────────

def _try_openai() -> tuple[LLMProvider, str]:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("AGENT_MODEL") or "gpt-5.1"

    class _OpenAIProvider:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""

    return _OpenAIProvider(), model


# ── OpenRouter ──────────────────────────────────────────────────────────────────

def _try_openrouter() -> tuple[LLMProvider, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    model = os.getenv("AGENT_MODEL") or "anthropic/claude-sonnet-4.6"

    class _OpenRouterProvider:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""

    return _OpenRouterProvider(), model


# ── Ollama (local) ─────────────────────────────────────────────────────────────

def _try_ollama() -> tuple[LLMProvider, str]:
    import requests

    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("AGENT_MODEL") or "llama3.2"

    # Quick health check.
    try:
        resp = requests.get(f"{base}/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Ollama not reachable at {base}: {exc}")

    class _OllamaProvider:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            payload = {
                "model": model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
            }
            r = requests.post(f"{base}/api/generate", json=payload, timeout=120)
            r.raise_for_status()
            return r.json().get("response", "")

    return _OllamaProvider(), model
