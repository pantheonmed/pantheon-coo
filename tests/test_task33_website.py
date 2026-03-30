"""Task 33 — website_builder + website_generator."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from config import settings
from models import ToolName
from templates import get_template_by_id


HTML_MOCK = """<!DOCTYPE html><html><head>
<meta charset="utf-8"><title>T</title>
<style>body{margin:0}@media (max-width:600px){body{font-size:14px}}</style>
</head><body><p>Test</p></body></html>"""


@pytest.mark.asyncio
async def test_create_landing_page_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))

    async def fake_gen(self, instruction):  # noqa: ARG001
        return HTML_MOCK

    with patch(
        "agents.website_generator.WebsiteGeneratorAgent.generate_html",
        new=fake_gen,
    ):
        from tools import website_builder

        r = await website_builder.execute(
            "create_landing_page",
            {
                "business_name": "Acme Co",
                "tagline": "Best",
                "description": "We build",
                "features": ["a", "b"],
                "contact_email": "a@b.com",
                "color_scheme": "modern",
            },
        )
    p = Path(r["html_path"])
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "<html" in text.lower()
    assert "<head" in text.lower()
    assert "<body" in text.lower()
    assert "@media" in text
    assert str(tmp_path) in str(p.resolve())


@pytest.mark.asyncio
async def test_optimize_seo_adds_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    sites = tmp_path / "websites" / "x"
    sites.mkdir(parents=True)
    f = sites / "p.html"
    f.write_text("<html><head></head><body></body></html>", encoding="utf-8")

    from tools import website_builder

    r = await website_builder.execute(
        "optimize_seo",
        {
            "page_path": str(f),
            "keywords": ["a", "b"],
            "meta_description": "Hello world desc",
        },
    )
    body = Path(r["html_path"]).read_text(encoding="utf-8")
    assert 'name="description"' in body
    assert "Hello world desc" in body


def test_website_templates_exist():
    assert get_template_by_id("business_website")
    assert get_template_by_id("medical_website")


def test_toolname_website_builder():
    assert ToolName.WEBSITE_BUILDER.value == "website_builder"
