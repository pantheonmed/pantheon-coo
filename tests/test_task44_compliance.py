"""Task 44 — compliance / legal templates."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import settings
from models import ToolName
from tools import compliance as comp_mod


@pytest.mark.asyncio
async def test_validate_gstin_known_sample():
    r = await comp_mod.execute("validate_gstin", {"gstin": "27AAPFU0939F1ZV"})
    assert r["valid"] is True


@pytest.mark.asyncio
async def test_validate_gstin_invalid():
    r = await comp_mod.execute("validate_gstin", {"gstin": "INVALID123"})
    assert r["valid"] is False


@pytest.mark.asyncio
async def test_validate_pan_ok():
    r = await comp_mod.execute("validate_pan", {"pan": "ABCDE1234F"})
    assert r["valid"] is True


@pytest.mark.asyncio
async def test_validate_pan_bad():
    r = await comp_mod.execute("validate_pan", {"pan": "123456"})
    assert r["valid"] is False


@pytest.mark.asyncio
async def test_gst_compliance_check_state_code():
    r = await comp_mod.execute("gst_compliance_check", {"gstin": "27AAPFU0939F1ZV"})
    assert r["state_code"] == "27"


@pytest.mark.asyncio
async def test_create_nda_has_disclaimer(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    r = await comp_mod.execute(
        "create_nda",
        {
            "party1_name": "CoA",
            "party1_address": "A1",
            "party2_name": "CoB",
            "party2_address": "B1",
            "purpose": "Pilot",
            "duration_years": 2,
        },
    )
    text = Path(r["file_path"]).read_text(encoding="utf-8")
    assert "DISCLAIMER" in text


@pytest.mark.asyncio
async def test_generate_compliance_doc_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    r = await comp_mod.execute(
        "generate_compliance_doc",
        {"regulation": "GDPR", "company_name": "Acme", "product_name": "Device"},
    )
    p = Path(r["file_path"])
    assert p.suffix == ".md"
    assert "Acme" in p.read_text(encoding="utf-8")


def test_toolname_compliance_enum():
    assert ToolName.COMPLIANCE.value == "compliance"
