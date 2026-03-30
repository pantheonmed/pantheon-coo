"""
Task 29 — Suggester agent, suggestions_json, API + dashboard wiring.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import memory.store as store
from models import SuggestionOutput


@pytest.mark.asyncio
async def test_suggester_agent_returns_list():
    from agents.suggester import SuggesterAgent

    out = await SuggesterAgent().run("goal text", "summary text", "build")
    assert isinstance(out, list)
    assert len(out) == 3
    assert all(isinstance(x, str) for x in out)


def test_suggestion_output_model_validates():
    m = SuggestionOutput(suggestions=["a", "b", "c"])
    assert m.suggestions == ["a", "b", "c"]
    m2 = SuggestionOutput()
    assert m2.suggestions == []


@pytest.mark.asyncio
async def test_save_and_get_suggestions_roundtrip():
    await store.init()
    tid = str(uuid.uuid4())
    await store.create_task(tid, "sample command for suggestions", "test")
    await store.save_suggestions(tid, ["cmd one", "cmd two", "cmd three"])
    got = await store.get_suggestions(tid)
    assert got == ["cmd one", "cmd two", "cmd three"]


@pytest.mark.asyncio
async def test_get_task_response_includes_suggestions(client: TestClient):
    await store.init()
    tid = str(uuid.uuid4())
    await store.create_task(tid, "command", "test")
    await store.save_suggestions(tid, ["next a", "next b"])
    r = client.get(f"/tasks/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert body.get("suggestions") == ["next a", "next b"]


@pytest.mark.asyncio
async def test_failed_task_empty_suggestions_no_crash(client: TestClient):
    await store.init()
    tid = str(uuid.uuid4())
    await store.create_task(tid, "command", "test")
    from models import TaskStatus

    await store.update_status(
        tid,
        TaskStatus.FAILED,
        summary="failed",
        error="e",
        iterations=1,
    )
    r = client.get(f"/tasks/{tid}")
    assert r.status_code == 200
    assert r.json().get("suggestions") in ([], None) or r.json().get("suggestions") == []
