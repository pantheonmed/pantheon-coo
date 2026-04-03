"""Task 42 — news / research tool."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ToolName
from tools import researcher as rs_mod

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>India tech news</title><link>https://news.example.com/1</link>
<pubDate>Mon, 1 Jan 2024 00:00:00 GMT</pubDate><description><![CDATA[Summary here]]></description><source>Ex</source></item>
</channel></rss>"""


@pytest.mark.asyncio
async def test_search_news_returns_title_url():
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.text = RSS_SAMPLE

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kwargs):
            self.url = url
            return fake_resp

    fc = FakeClient()
    with patch("tools.researcher.httpx.AsyncClient", return_value=fc):
        items = await rs_mod.execute("search_news", {"query": "startup", "limit": 5})
    assert len(items) >= 1
    assert "title" in items[0] and "url" in items[0]
    assert items[0]["title"]
    assert "news.google.com/rss/search" in fc.url
    assert "gl=IN" in fc.url


@pytest.mark.asyncio
async def test_research_topic_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))

    async def fake_news(p):
        return [{"title": "A", "url": "https://u.test/a", "summary": "", "source": "s", "date": "", "sentiment": "neutral"}]

    async def fake_tavily(q, limit=5):
        return [
            {
                "title": "A",
                "url": "https://u.test/a",
                "summary": "x",
                "source": "s",
                "published": "",
            }
        ]

    with patch.object(rs_mod, "tavily_search", side_effect=fake_tavily):
        r = await rs_mod.execute(
            "research_topic",
            {"topic": "widgets", "depth": "quick", "save_to_file": True},
        )
    assert r["file_path"]
    assert Path(r["file_path"]).is_file()


@pytest.mark.asyncio
async def test_get_industry_news_medical():
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.text = RSS_SAMPLE

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **k):
            return fake_resp

    with patch("tools.researcher.httpx.AsyncClient", return_value=FakeClient()):
        items = await rs_mod.execute("get_industry_news", {"industry": "medical", "limit": 3})
    assert isinstance(items, list)
    assert len(items) >= 1


def test_rss_url_indian_news():
    u = rs_mod._rss_url("health India", "en")
    assert "hl=en-IN" in u or "en-IN" in u
    assert "gl=IN" in u


def test_toolname_researcher_enum():
    assert ToolName.RESEARCHER.value == "researcher"
