"""Task 45 — deployer tool + sandbox."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from models import ExecutionStep, StepStatus, ToolName
from security.sandbox import SecurityError, validate_step
from tools import deployer as dep_mod


@pytest.mark.asyncio
async def test_deploy_to_railway_cli_command(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    monkeypatch.setattr(settings, "railway_token", "rtok")
    proj = tmp_path / "svc"
    proj.mkdir()
    cmds = []

    def fake_run(*args, **kwargs):
        cmds.append(args[0])
        return MagicMock(returncode=0, stdout="", stderr="deployed https://x.up.railway.app")

    with patch.object(dep_mod.subprocess, "run", side_effect=fake_run):
        await dep_mod.execute(
            "deploy_to_railway",
            {"project_path": str(proj), "service_name": "api", "port": 8000},
        )
    assert cmds and cmds[0][0] == "railway"
    assert "up" in cmds[0]


@pytest.mark.asyncio
async def test_create_github_repo_api_request(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "github_token", "ghp_test")
    monkeypatch.setattr(settings, "github_username", "u")
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(
                return_value={
                    "html_url": "https://github.com/u/r",
                    "clone_url": "https://github.com/u/r.git",
                }
            )
            return resp

    with patch("tools.deployer.httpx.AsyncClient", return_value=FakeClient()):
        r = await dep_mod.execute(
            "create_github_repo",
            {"repo_name": "my-app", "description": "x", "private": False},
        )
    assert "api.github.com" in captured["url"]
    assert captured["json"]["name"] == "my-app"
    assert r["repo_url"]


@pytest.mark.asyncio
async def test_push_to_github_workspace_path(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    monkeypatch.setattr(settings, "github_token", "tok")
    lp = tmp_path / "code"
    lp.mkdir()
    (lp / "f.txt").write_text("hi", encoding="utf-8")

    with patch.object(dep_mod, "_git_commit_push", return_value="abc123"):
        r = await dep_mod.execute(
            "push_to_github",
            {"local_path": str(lp), "repo_url": "https://github.com/u/r.git"},
        )
    assert r["success"] is True
    assert r["commit_sha"] == "abc123"


def test_invalid_repo_name_sandbox():
    step = ExecutionStep(
        step_id=1,
        tool=ToolName.DEPLOYER,
        action="create_github_repo",
        params={"repo_name": "my repo!"},
        status=StepStatus.PENDING,
    )
    with pytest.raises(SecurityError):
        validate_step(step)


@pytest.mark.asyncio
async def test_check_deployment_live_field():
    fake_resp = MagicMock()
    fake_resp.status_code = 200

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, **kwargs):
            return fake_resp

    with patch("tools.deployer.httpx.AsyncClient", return_value=FakeClient()):
        r = await dep_mod.execute("check_deployment", {"url": "https://example.com"})
    assert "live" in r
    assert r["live"] is True


def test_toolname_deployer_enum():
    assert ToolName.DEPLOYER.value == "deployer"
