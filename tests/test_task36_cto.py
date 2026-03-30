"""Task 36 — code_builder + code_agent."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ToolName


@pytest.mark.asyncio
async def test_create_fastapi_app_has_main(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import code_builder

    r = await code_builder.execute(
        "create_fastapi_app",
        {
            "app_name": "demo_api",
            "endpoints": [{"path": "/ping", "method": "GET"}],
            "database": "sqlite",
            "auth": False,
        },
    )
    root = Path(r["project_path"])
    main = root / "main.py"
    assert main.exists()
    assert "FastAPI" in main.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_telegram_bot_bot_py(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    from tools import code_builder

    r = await code_builder.execute(
        "create_telegram_bot",
        {
            "bot_name": "helper",
            "commands": [{"command": "start", "description": "Go", "handler": "on_start"}],
        },
    )
    bot = Path(r["project_path"]) / "bot.py"
    assert bot.exists()


@pytest.mark.asyncio
async def test_generate_tests_writes_prefixed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    src = tmp_path / "mod.py"
    src.write_text("def add(a,b): return a+b\n", encoding="utf-8")

    with patch(
        "tools.code_builder.call_model",
        return_value=MagicMock(
            text="def test_add():\n    assert add(1,2)==3\n",
            model_used="m",
            provider="p",
        ),
    ):
        from tools import code_builder

        r = await code_builder.execute(
            "generate_tests",
            {"source_file_path": str(src), "framework": "pytest"},
        )
    tp = Path(r["test_path"])
    assert tp.name.startswith("test_")
    assert tp.exists()


@pytest.mark.asyncio
async def test_run_code_review_dict_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    f = tmp_path / "x.py"
    f.write_text("x=1\n", encoding="utf-8")

    with patch(
        "tools.code_builder.call_model",
        return_value=MagicMock(
            text='{"issues":["i1"],"suggestions":["s1"],"score":80}',
            model_used="m",
            provider="p",
        ),
    ):
        from tools import code_builder

        r = await code_builder.execute(
            "run_code_review", {"file_path": str(f), "language": "python"}
        )
    assert "issues" in r
    assert "suggestions" in r


def test_build_api_template_exists():
    from templates import get_template_by_id

    assert get_template_by_id("build_api")
    assert get_template_by_id("generate_tests_template")


def test_code_builder_enum():
    assert ToolName.CODE_BUILDER.value == "code_builder"
