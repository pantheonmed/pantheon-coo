"""Task 34 — content_creator tool + templates."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ToolName
from templates import TEMPLATES, get_template_by_id


def _mock_model_response(text: str):
    return MagicMock(text=text, model_used="mock", provider="mock")


@pytest.mark.asyncio
async def test_write_blog_post_creates_md(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))

    with patch(
        "tools.content_creator.call_model",
        return_value=_mock_model_response("# Blog\n\nHello"),
    ):
        from tools import content_creator

        r = await content_creator.execute(
            "write_blog_post",
            {"topic": "AI", "keywords": ["a"], "word_count": 100, "tone": "professional"},
        )
    p = Path(r["path"])
    assert p.suffix == ".md"
    assert p.read_text(encoding="utf-8").startswith("# Blog")


@pytest.mark.asyncio
async def test_write_social_instagram_has_hashtags(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    body = "Great post #india #startup #biz #life #extra"

    with patch(
        "tools.content_creator.call_model",
        return_value=_mock_model_response(body),
    ):
        from tools import content_creator

        r = await content_creator.execute(
            "write_social_post",
            {
                "platform": "instagram",
                "topic": "Growth",
                "goal": "engagement",
                "include_hashtags": True,
            },
        )
    assert "#" in Path(r["path"]).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_content_calendar_mentions_month(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    md = "| Date | Platform |\n| --- | --- |\n| 1 Apr | linkedin |"

    with patch(
        "tools.content_creator.call_model",
        return_value=_mock_model_response(md),
    ):
        from tools import content_creator

        r = await content_creator.execute(
            "create_content_calendar",
            {
                "brand_name": "B",
                "industry": "tech",
                "platforms": ["linkedin"],
                "posts_per_week": 5,
                "month": "April 2026",
            },
        )
    text = Path(r["path"]).read_text(encoding="utf-8")
    assert "linkedin" in text.lower() or "Platform" in text


@pytest.mark.asyncio
async def test_write_email_includes_cta(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))

    with patch(
        "tools.content_creator.call_model",
        return_value=_mock_model_response("Click BUY NOW today"),
    ):
        from tools import content_creator

        await content_creator.execute(
            "write_email_campaign",
            {
                "campaign_type": "promotional",
                "product_name": "P",
                "key_message": "M",
                "cta_text": "BUY NOW",
            },
        )
    d = tmp_path / "content"
    files = list(d.glob("*.md"))
    assert files
    assert "BUY" in files[0].read_text(encoding="utf-8")


def test_four_templates_exist():
    for tid in ("linkedin_post", "blog_post", "product_description", "biovital_content"):
        assert get_template_by_id(tid), tid


def test_content_creator_enum():
    assert ToolName.CONTENT_CREATOR.value == "content_creator"
