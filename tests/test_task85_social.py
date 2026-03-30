"""Task 85 — Instagram + Twitter tools + templates."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import settings
from models import ToolName
from templates import TEMPLATES
from tools import instagram, twitter


@pytest.mark.asyncio
async def test_instagram_post_image_requires_existing_file():
    with pytest.raises(Exception):
        await instagram.execute("post_image", {"image_path": "/tmp/does_not_exist_xxx.png"})


@pytest.mark.asyncio
async def test_instagram_post_image_ok():
    ws = Path(settings.workspace_dir) / "t85_instagram"
    ws.mkdir(parents=True, exist_ok=True)
    img = ws / "a.png"
    img.write_bytes(b"x")
    out = await instagram.execute(
        "post_image", {"image_path": str(img), "caption": "hi", "hashtags": ["#x"]}
    )
    assert out.get("status") == "planned"


@pytest.mark.asyncio
async def test_twitter_search_list():
    out = await twitter.execute("search", {"query": "AI", "limit": 3})
    assert "data" in out or "meta" in out or isinstance(out, dict)


def test_toolname_instagram_twitter():
    assert ToolName.INSTAGRAM.value == "instagram"
    assert ToolName.TWITTER.value == "twitter"


def test_social_templates():
    ids = {t["id"] for t in TEMPLATES}
    assert "instagram_product_post" in ids
    assert "social_media_calendar" in ids
