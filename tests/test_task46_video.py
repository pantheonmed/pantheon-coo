"""Task 46 — video generator fallbacks."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings
from models import ToolName
from tools import video_generator as vg_mod


@pytest.mark.asyncio
async def test_text_to_video_fallback_script_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    monkeypatch.setattr(settings, "video_generation_enabled", False)
    monkeypatch.setattr(settings, "did_api_key", "")
    r = await vg_mod.execute(
        "text_to_video",
        {"script": "Hello world narration", "style": "professional", "duration_seconds": 30},
    )
    assert "script_path" in r
    assert Path(r["script_path"]).is_file()


@pytest.mark.asyncio
async def test_text_to_video_creates_workspace_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    monkeypatch.setattr(settings, "video_generation_enabled", False)
    r = await vg_mod.execute("text_to_video", {"script": "A", "duration_seconds": 10})
    assert Path(r["script_path"]).read_text(encoding="utf-8") == "A"
    assert Path(r["video_path"]).suffix == ".html"


@pytest.mark.asyncio
async def test_images_to_slideshow_html(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    with patch.object(vg_mod.subprocess, "run", side_effect=FileNotFoundError()):
        r = await vg_mod.execute(
            "images_to_slideshow",
            {"image_paths": [str(img)], "duration_per_image": 2, "output_filename": "s.mp4"},
        )
    assert r["output_path"].endswith(".html") or r["output_path"].endswith(".mp4")
    assert Path(r["output_path"]).is_file()


@pytest.mark.asyncio
async def test_create_social_video_script_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))

    class R:
        text = "## Hook\nHi\n#tag #india"

    with patch("tools.video_generator.call_model", return_value=R()):
        r = await vg_mod.execute(
            "create_social_video",
            {"platform": "instagram", "topic": "wellness", "duration_seconds": 30},
        )
    assert "script_path" in r
    assert Path(r["script_path"]).is_file()
    assert isinstance(r.get("recommended_hashtags"), list)


def test_toolname_video_generator_enum():
    assert ToolName.VIDEO_GENERATOR.value == "video_generator"


@pytest.mark.asyncio
async def test_graceful_when_api_keys_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    monkeypatch.setattr(settings, "did_api_key", "")
    monkeypatch.setattr(settings, "synthesia_api_key", "")
    monkeypatch.setattr(settings, "video_generation_enabled", False)
    r = await vg_mod.execute("text_to_video", {"script": "ok"})
    assert r.get("video_url") in ("", None) or isinstance(r.get("video_url"), str)
