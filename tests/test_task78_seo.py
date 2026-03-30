"""Task 78 — SEO meta, robots, sitemap."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_landing_has_og_title():
    html = (ROOT / "static" / "landing.html").read_text(encoding="utf-8")
    assert 'property="og:title"' in html
    assert "Pantheon COO OS" in html


def test_landing_has_twitter_card():
    html = (ROOT / "static" / "landing.html").read_text(encoding="utf-8")
    assert 'name="twitter:card"' in html
    assert "summary_large_image" in html


def test_robots_txt_exists():
    assert (ROOT / "static" / "robots.txt").is_file()


def test_sitemap_xml_returns_200(client: TestClient):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in (r.headers.get("content-type") or "").lower() or r.text.strip().startswith("<?xml")


def test_landing_has_schema_org_json_ld():
    html = (ROOT / "static" / "landing.html").read_text(encoding="utf-8")
    assert "application/ld+json" in html
    assert "SoftwareApplication" in html
    assert "schema.org" in html


def test_og_image_svg_exists():
    assert (ROOT / "static" / "og-image.svg").is_file()
