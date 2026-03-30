"""
agents/model_router.py
───────────────────────
Phase 4 — Multi-Model Router

Every agent call goes through this router instead of calling Claude directly.

Routing logic:
  1. Try Claude (primary) with configured model
  2. If rate-limited, unavailable, or repeatedly failing → fall back to OpenAI
  3. Log which model was used and whether fallback was triggered
  4. Restore Claude as primary once it recovers (checked on next call)

This makes the COO resilient to any single provider's downtime.
The router is transparent — agents don't know which model answered.

Supports:
  - claude-sonnet / claude-haiku (Anthropic)
  - gpt-4o / gpt-4o-mini (OpenAI)
  - Extensible: add Gemini, Mistral, etc. as providers
"""
from __future__ import annotations
import json
import time
from typing import Any
from pydantic import BaseModel

from config import settings

# Circuit breaker state — module-level singleton
_claude_failures: int = 0
_claude_last_failure: float = 0.0
_CIRCUIT_OPEN_SECONDS = 120   # keep Claude circuit open for 2 min after failures
_FAILURE_THRESHOLD = 3        # open circuit after 3 consecutive failures

# Lifetime call counts (for performance reports)
_claude_calls: int = 0
_openai_fallback_calls: int = 0


def get_model_usage_counts() -> dict[str, int]:
    return {"claude": _claude_calls, "openai_fallback": _openai_fallback_calls}


def _claude_circuit_open() -> bool:
    """True if Claude should be bypassed (circuit breaker open)."""
    global _claude_failures
    if _claude_failures >= _FAILURE_THRESHOLD:
        if time.time() - _claude_last_failure < _CIRCUIT_OPEN_SECONDS:
            return True
        # Reset after cooldown
        _claude_failures = 0
    return False


def _record_claude_failure() -> None:
    global _claude_failures, _claude_last_failure
    _claude_failures += 1
    _claude_last_failure = time.time()


def _record_claude_success() -> None:
    global _claude_failures
    _claude_failures = 0


class ModelResponse(BaseModel):
    text: str
    model_used: str
    provider: str
    fallback_used: bool = False


def call_model(
    system: str,
    user: str,
    *,
    use_fast: bool = False,
    max_tokens: int = 2048,
) -> ModelResponse:
    """
    Synchronous model call with automatic fallback.
    Returns a ModelResponse with the text and metadata.
    """
    # Determine which model tier to use
    claude_model = settings.claude_model_fast if use_fast else settings.claude_model

    # Try Claude first (unless circuit is open)
    if not _claude_circuit_open() and settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=claude_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            _record_claude_success()
            global _claude_calls
            _claude_calls += 1
            return ModelResponse(
                text=response.content[0].text,
                model_used=claude_model,
                provider="anthropic",
                fallback_used=False,
            )
        except Exception as e:
            _record_claude_failure()
            err_str = str(e).lower()
            is_rate_limit = any(k in err_str for k in ("rate", "limit", "429", "overload"))
            if not (settings.enable_fallback and settings.openai_api_key):
                raise
            print(f"[ModelRouter] Claude failed ({'rate-limit' if is_rate_limit else 'error'}): {e}. Falling back to OpenAI.")

    # Fallback: OpenAI
    if settings.enable_fallback and settings.openai_api_key:
        return _call_openai(system, user, use_fast=use_fast, max_tokens=max_tokens)

    raise RuntimeError(
        "No AI provider available. Set ANTHROPIC_API_KEY (and optionally OPENAI_API_KEY for fallback)."
    )


def _call_openai(system: str, user: str, *, use_fast: bool, max_tokens: int) -> ModelResponse:
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    model = settings.openai_model_fast if use_fast else settings.openai_model
    client = openai.OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    global _openai_fallback_calls
    _openai_fallback_calls += 1
    return ModelResponse(
        text=response.choices[0].message.content or "",
        model_used=model,
        provider="openai",
        fallback_used=True,
    )


def router_status() -> dict:
    """Return current router state for the dashboard."""
    circuit_open = _claude_circuit_open()
    return {
        "claude_circuit": "open (using fallback)" if circuit_open else "closed (healthy)",
        "claude_consecutive_failures": _claude_failures,
        "fallback_enabled": settings.enable_fallback,
        "fallback_provider": "openai" if settings.openai_api_key else "none",
        "primary_model": settings.claude_model,
        "fallback_model": settings.openai_model if settings.openai_api_key else "n/a",
    }
