"""Task 41 — image analyzer + sandbox."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from config import settings
from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_step
from tools import image_analyzer as img_mod


@pytest.mark.asyncio
async def test_analyze_image_returns_description(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    def fake_vision(*a, **k):
        return '{"description": "A diagram", "objects_found": ["box"], "text_extracted": "Hi"}'

    with patch.object(img_mod, "_call_vision", side_effect=fake_vision):
        r = await img_mod.execute("analyze_image", {"image_path": str(p), "question": "What?"})
    assert r["description"] == "A diagram"


@pytest.mark.asyncio
async def test_extract_text_from_image_returns_text(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    p = tmp_path / "doc.jpg"
    p.write_bytes(b"\xff\xd8\xff" + b"\x00" * 30)

    def fake_vision(*a, **k):
        return '{"text": "Invoice 123", "confidence": "high"}'

    with patch.object(img_mod, "_call_vision", side_effect=fake_vision):
        r = await img_mod.execute("extract_text_from_image", {"image_path": str(p)})
    assert r["text"] == "Invoice 123"
    assert r["confidence"] == "high"


def test_non_image_extension_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    pyf = tmp_path / "bad.py"
    pyf.write_text("x=1", encoding="utf-8")
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.IMAGE_ANALYZER,
        action="analyze_image",
        params={"image_path": str(pyf)},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError):
        validate_step(step)


def test_oversize_image_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    big = tmp_path / "big.png"
    big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (11 * 1024 * 1024))
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.IMAGE_ANALYZER,
        action="analyze_image",
        params={"image_path": str(big)},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError, match="10MB"):
        validate_step(step)


def test_toolname_image_analyzer_enum():
    assert ToolName.IMAGE_ANALYZER.value == "image_analyzer"
