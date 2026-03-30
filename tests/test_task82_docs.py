"""Task 82 — developer docs page, guides, /docs-page route."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_static_docs_html_exists():
    root = Path(__file__).resolve().parents[1]
    p = root / "static" / "docs.html"
    assert p.is_file()


def test_docs_html_has_authentication_section():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "docs.html").read_text(encoding="utf-8")
    assert "Authentication" in html or "authentication" in html.lower()


def test_docs_html_has_python_sdk_example():
    root = Path(__file__).resolve().parents[1]
    html = (root / "static" / "docs.html").read_text(encoding="utf-8")
    assert "PantheonCOO" in html or "class PantheonCOO" in html


def test_user_guide_exists_and_substantial():
    root = Path(__file__).resolve().parents[1]
    p = root / "USER_GUIDE.md"
    assert p.is_file()
    assert len(p.read_text(encoding="utf-8")) > 500


def test_operator_guide_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "OPERATOR_GUIDE.md").is_file()


def test_docs_page_returns_200(client: TestClient):
    r = client.get("/docs-page")
    assert r.status_code == 200
