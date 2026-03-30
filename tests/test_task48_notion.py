"""Task 48 — Notion tool + sandbox."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_step
from tools import notion as notion_mod


@pytest.mark.asyncio
async def test_create_page_notion_request(monkeypatch):
    monkeypatch.setattr(settings, "notion_api_key", "secret_x")
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"id": "page-1", "url": "https://notion.so/x"})
            return resp

    with patch("tools.notion.httpx.AsyncClient", return_value=FakeClient()):
        await notion_mod.execute(
            "create_page",
            {
                "parent_page_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "title": "T",
                "content": "Body",
            },
        )
    assert "notion.com" in captured["url"] or "api.notion.com" in captured["url"]
    assert captured["json"]["parent"]["page_id"]


@pytest.mark.asyncio
async def test_read_page_returns_title_content(monkeypatch):
    monkeypatch.setattr(settings, "notion_api_key", "secret_x")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "/blocks/" in url:
                resp.json = MagicMock(return_value={"results": []})
            else:
                resp.json = MagicMock(
                    return_value={
                        "properties": {
                            "title": {
                                "type": "title",
                                "title": [{"plain_text": "Hello"}],
                            }
                        },
                        "last_edited_time": "2026-01-01T00:00:00Z",
                    }
                )
            return resp

    with patch("tools.notion.httpx.AsyncClient", return_value=FakeClient()):
        r = await notion_mod.execute(
            "read_page",
            {"page_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        )
    assert r["title"] == "Hello"
    assert "content" in r


@pytest.mark.asyncio
async def test_search_pages_list_title(monkeypatch):
    monkeypatch.setattr(settings, "notion_api_key", "secret_x")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(
                return_value={
                    "results": [
                        {
                            "object": "page",
                            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "url": "https://n.test/p",
                            "last_edited_time": "t",
                            "properties": {
                                "title": {
                                    "type": "title",
                                    "title": [{"plain_text": "Doc"}],
                                }
                            },
                        }
                    ]
                }
            )
            return resp

    with patch("tools.notion.httpx.AsyncClient", return_value=FakeClient()):
        items = await notion_mod.execute("search_pages", {"query": "q", "limit": 5})
    assert len(items) == 1
    assert items[0]["title"] == "Doc"


def test_invalid_page_id_blocked_by_sandbox():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.NOTION,
        action="read_page",
        params={"page_id": "not-a-real-uuid"},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError):
        validate_step(step)


def test_toolname_notion_enum():
    assert ToolName.NOTION.value == "notion"
