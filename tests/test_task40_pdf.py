"""Task 40 — PDF generator (reportlab)."""
from __future__ import annotations

from pathlib import Path

import pytest

import reportlab

from config import settings
from models import ToolName
from tools import REGISTRY
from tools import pdf_generator as pdf_mod


@pytest.mark.asyncio
async def test_create_report_pdf_file_size(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    r = await pdf_mod.execute(
        "create_report_pdf",
        {
            "title": "Q1 Report",
            "sections": [{"heading": "Overview", "content": "Line one.\n\nLine two."}],
            "footer_text": "Pantheon COO OS",
        },
    )
    p = tmp_path / "pdfs" / "report_Q1_Report.pdf"
    assert p.is_file()
    assert p.stat().st_size > 0
    assert r["pdf_path"] == str(p)
    assert r["pages"] >= 1


@pytest.mark.asyncio
async def test_create_letter_pdf_generates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    r = await pdf_mod.execute(
        "create_letter_pdf",
        {
            "from_name": "A",
            "from_address": "Addr1",
            "to_name": "B",
            "to_address": "Addr2",
            "subject": "Hello",
            "body": "Dear B,\n\nRegards.",
            "date": "2026-03-29",
        },
    )
    assert (tmp_path / "pdfs").exists()
    assert Path(r["pdf_path"]).is_file()


@pytest.mark.asyncio
async def test_markdown_to_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    md = tmp_path / "notes.md"
    md.write_text("# Title\n\nParagraph here.", encoding="utf-8")
    r = await pdf_mod.execute("markdown_to_pdf", {"markdown_file_path": str(md)})
    assert Path(r["pdf_path"]).suffix == ".pdf"
    assert Path(r["pdf_path"]).stat().st_size > 0


def test_toolname_pdf_generator_enum():
    assert ToolName.PDF_GENERATOR.value == "pdf_generator"


def test_reportlab_imported():
    assert reportlab.Version is not None


def test_pdf_generator_in_registry():
    assert ToolName.PDF_GENERATOR in REGISTRY
    assert REGISTRY[ToolName.PDF_GENERATOR] is pdf_mod
