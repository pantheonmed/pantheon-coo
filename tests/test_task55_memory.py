"""Task 55 — Semantic memory store & API."""
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from config import settings
from memory.semantic_store import SemanticMemory


@pytest.mark.asyncio
async def test_store_memory_inserts_row():
    dbp = settings.db_path
    sm = SemanticMemory(dbp)
    mid = await sm.store_memory(
        task_id=str(uuid.uuid4()),
        content="hello stock analysis",
        memory_type="analyze",
        tags=["stock", "finance"],
        importance=0.8,
        owner_user_id="u1",
    )
    assert len(mid) > 10
    import memory.store as store

    row = await store.get_semantic_memory(mid)
    assert row is not None
    assert row["memory_type"] == "analyze"
    assert abs(float(row["importance"]) - 0.8) < 0.01


@pytest.mark.asyncio
async def test_recall_returns_list_mock_keywords():
    dbp = settings.db_path
    sm = SemanticMemory(dbp)
    await sm.store_memory(
        task_id="t1",
        content="stock analysis report",
        memory_type="analyze",
        tags=["stock"],
        importance=0.9,
    )

    async def fake_kw(self, q):
        return ["stock"]

    with patch.object(SemanticMemory, "_extract_keywords", fake_kw):
        out = await sm.recall("analysis", limit=3)
    assert isinstance(out, list)
    assert len(out) >= 1


def test_get_memory_semantic_200(client: TestClient):
    r = client.get("/memory/semantic?query=test&limit=2")
    assert r.status_code == 200
    assert "memories" in r.json()


def test_get_memory_stats_fields(client: TestClient):
    r = client.get("/memory/stats")
    assert r.status_code == 200
    j = r.json()
    for k in ("total_learnings", "total_semantic_memories", "top_memory_types", "avg_importance"):
        assert k in j
