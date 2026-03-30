"""
tests/conftest.py
──────────────────
Shared pytest fixtures for Pantheon COO OS tests.

Sets up:
  - In-memory / temp SQLite DB (isolated per test)
  - FastAPI test client with auth mocked out
  - Mocked Claude API (no real API calls in tests)
  - Temp workspace directory
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# ── Ensure project root is on path ───────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Point to isolated test DB and workspace before importing app ──────────────
_tmp = tempfile.mkdtemp(prefix="pantheon_test_")
os.environ.setdefault("DB_PATH", str(Path(_tmp) / "test.db"))
os.environ.setdefault("WORKSPACE_DIR", str(Path(_tmp) / "workspace"))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
os.environ.setdefault("AUTH_MODE", "none")  # disable auth in tests
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

Path(os.environ["WORKSPACE_DIR"]).mkdir(parents=True, exist_ok=True)


def pytest_collection_modifyitems(config, items):
    """OpenTelemetry tests mutate global tracer state; run them last."""

    def _sort_key(it):
        p = str(getattr(it, "path", None) or getattr(it, "fspath", "") or "")
        return (2 if "test_task52_tracing" in p else 1, p)

    items.sort(key=_sort_key)


# ─────────────────────────────────────────────────────────────────────────────
# Mock Claude API — every test uses this by default
# ─────────────────────────────────────────────────────────────────────────────

MOCK_PLAN_JSON = """{
  "goal_summary": "Test plan goal",
  "estimated_seconds": 5,
  "notes": "",
  "steps": [
    {
      "step_id": 1,
      "tool": "filesystem",
      "action": "make_dir",
      "params": {"path": "/tmp/pantheon_v2/test_output"},
      "depends_on": [],
      "description": "Create test output directory"
    }
  ]
}"""

MOCK_REASONING_JSON = """{
  "understood_goal": "Create a test directory",
  "goal_type": "build",
  "complexity": "low",
  "risks": [],
  "constraints": [],
  "success_criteria": ["Directory exists after execution"],
  "clarifications_needed": []
}"""

MOCK_EVAL_JSON = """{
  "score": 0.95,
  "goal_met": true,
  "what_worked": ["Directory created successfully"],
  "what_failed": [],
  "improvement_hints": [],
  "summary": "Task completed successfully. Directory was created as expected."
}"""

MOCK_MEMORY_JSON = """{
  "stored": true,
  "learning": "Use make_dir before write_file to ensure parent directories exist."
}"""

MOCK_CONFIDENCE_JSON = """{
  "score": 0.9,
  "level": "high",
  "reasoning": "Clear, specific goal with well-defined success criteria.",
  "flags": []
}"""

MOCK_SUGGESTIONS_JSON = """{
  "suggestions": ["Review the output file", "Run a follow-up check", "Share results with the team"]
}"""

MOCK_TRADING_ANALYSIS_JSON = """{
  "symbol": "RELIANCE.NS",
  "trend": "neutral",
  "summary": "Price action mixed. Volume stable.",
  "key_levels": {"support": 2400.0, "resistance": 2600.0},
  "risk_factors": ["macro", "sector rotation"],
  "disclaimer": "This is educational analysis only, NOT investment advice. Consult a SEBI-registered advisor before investing."
}"""

MOCK_BRAND_STRATEGY_JSON = """{
  "content_pillars": ["pillar_a", "pillar_b"],
  "posting_schedule": {"linkedin": "3x weekly"},
  "hashtag_strategy": ["#india", "#startup"],
  "90_day_plan": ["Month 1: awareness", "Month 2: authority", "Month 3: conversion"]
}"""

MOCK_VIRAL_IDEAS_JSON = (
    '{"ideas":['
    + ",".join(
        [
            '{"hook":"h%s","body_outline":"b%s","cta":"c%s","hashtags":["#t%s"]}'
            % (i, i, i, i)
            for i in range(10)
        ]
    )
    + "]}"
)

MOCK_CONTENT_PACK_JSON = (
    '{"linkedin":["L1","L2"],"twitter":["T1"],"instagram":["I1"]}'
)


def make_mock_claude_response(json_text: str):
    """Build a mock Anthropic API response object."""
    mock_content = MagicMock()
    mock_content.text = json_text
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


@pytest.fixture(autouse=True)
def mock_claude_api():
    """
    Auto-used fixture: patches the Anthropic client for all tests.
    Different agent calls return appropriate mock JSON.
    """
    def side_effect(*args, **kwargs):
        system = kwargs.get("system", "")
        msgs = kwargs.get("messages") or []
        user_txt = ""
        if msgs:
            c0 = msgs[0].get("content") if isinstance(msgs[0], dict) else ""
            user_txt = str(c0)
        if "Reasoning Agent" in system:
            return make_mock_claude_response(MOCK_REASONING_JSON)
        elif "Planning Agent" in system:
            return make_mock_claude_response(MOCK_PLAN_JSON)
        elif "Evaluator Agent" in system:
            return make_mock_claude_response(MOCK_EVAL_JSON)
        elif "Memory Agent" in system:
            return make_mock_claude_response(MOCK_MEMORY_JSON)
        elif "confidence evaluator" in system:
            return make_mock_claude_response(MOCK_CONFIDENCE_JSON)
        elif "proactive COO assistant" in system:
            return make_mock_claude_response(MOCK_SUGGESTIONS_JSON)
        elif "market analysis assistant" in system:
            return make_mock_claude_response(MOCK_TRADING_ANALYSIS_JSON)
        elif "personal branding and social media strategist" in system:
            if "viral content ideas" in user_txt:
                return make_mock_claude_response(MOCK_VIRAL_IDEAS_JSON)
            if '"linkedin"' in user_txt and "Week:" in user_txt:
                return make_mock_claude_response(MOCK_CONTENT_PACK_JSON)
            return make_mock_claude_response(MOCK_BRAND_STRATEGY_JSON)
        elif "research synthesizer" in system:
            m = MagicMock()
            m.text = "## Summary\nSynthesized.\n## Key facts\n- one\n## Sources\n- src"
            mr = MagicMock()
            mr.content = [m]
            return mr
        # Default
        return make_mock_claude_response('{"result": "ok"}')

    with patch("anthropic.Anthropic") as mock_class:
        mock_instance = MagicMock()
        mock_instance.messages.create.side_effect = side_effect
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Per-test temp workspace that is guaranteed clean."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI test client
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client() -> Generator:
    """Synchronous test client. Waits for background DB init before tests run."""
    from main import app

    with TestClient(app, raise_server_exceptions=True) as c:
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            try:
                r = c.get("/ready")
                if r.status_code in (200, 503):
                    break
            except Exception:
                pass
            time.sleep(0.05)
        yield c


@pytest.fixture
def authed_client(client) -> Generator:
    """Client with a valid API key header (AUTH_MODE=apikey scenario)."""
    client.headers.update({"X-COO-API-Key": "test-key"})
    yield client


# ─────────────────────────────────────────────────────────────────────────────
# Async event loop (pytest-asyncio)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
