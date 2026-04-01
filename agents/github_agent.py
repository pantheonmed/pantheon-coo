"""
agents/github_agent.py
──────────────────────
GitHubAgent — minimal GitHub contents API + repo clone/pull helper.

This is intentionally conservative:
  - Requires settings.github_token
  - Uses GitHub Contents API for read/write
  - Uses the terminal tool for git clone/pull (still sandboxed by allowed_commands)
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from agents.model_router import call_model
from config import settings
from tools import terminal as term_tool


@dataclass
class GitHubFile:
    path: str
    sha: str
    content: str


class GitHubAgent:
    name = "github_agent"

    def __init__(self) -> None:
        if not (settings.github_token or "").strip():
            raise RuntimeError("GITHUB_TOKEN / settings.github_token is not configured")

    @property
    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        }

    async def _get_json(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=self.auth_headers)
            r.raise_for_status()
            return r.json()

    async def _put_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.put(url, headers=self.auth_headers, json=payload)
            r.raise_for_status()
            return r.json()

    async def read_file(self, repo: str, file_path: str, branch: str = "main") -> str:
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={branch}"
        j = await self._get_json(url)
        if j.get("type") != "file":
            raise ValueError("Not a file path")
        raw = j.get("content") or ""
        encoding = (j.get("encoding") or "base64").lower()
        if encoding != "base64":
            raise ValueError(f"Unsupported encoding: {encoding}")
        return base64.b64decode(raw).decode("utf-8", errors="replace")

    async def get_file_sha(self, repo: str, file_path: str, branch: str = "main") -> Optional[str]:
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={branch}"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, headers=self.auth_headers)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            j = r.json()
            return j.get("sha")

    async def write_file(
        self,
        repo: str,
        file_path: str,
        content: str,
        commit_message: str,
        *,
        branch: str = "main",
    ) -> dict[str, Any]:
        sha = await self.get_file_sha(repo, file_path, branch=branch)
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        payload: dict[str, Any] = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        return await self._put_json(url, payload)

    async def pull_repo(self, repo: str, local_path: str) -> dict[str, Any]:
        dst = Path(local_path).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and (dst / ".git").is_dir():
            res = await term_tool.execute(
                "run_command",
                {"command": "git pull", "cwd": str(dst)},
            )
            return {"path": str(dst), "status": "pulled", "result": res}
        res = await term_tool.execute(
            "run_command",
            {"command": f"git clone https://github.com/{repo}.git {str(dst)}", "cwd": str(dst.parent)},
        )
        return {"path": str(dst), "status": "cloned", "result": res}

    def _list_py_files(self, root: Path) -> list[Path]:
        out: list[Path] = []
        for d, _, files in os.walk(root):
            if ".git" in d.split(os.sep):
                continue
            for f in files:
                if f.endswith(".py"):
                    out.append(Path(d) / f)
        return out

    async def understand_and_fix(self, repo: str, issue_description: str) -> dict[str, Any]:
        local_path = f"/tmp/pantheon_v2/{repo.split('/')[-1]}"
        await self.pull_repo(repo, local_path)
        root = Path(local_path).resolve()
        files = self._list_py_files(root)[:80]  # cap
        codebase: dict[str, str] = {}
        for fp in files:
            try:
                codebase[str(fp.relative_to(root))] = fp.read_text(encoding="utf-8")[:12000]
            except Exception:
                continue

        system = (
            "You are an expert software engineer. Given a codebase snapshot and an issue description,\n"
            "identify the single best file to change and return STRICT JSON:\n"
            '{"file":"path","fixed_code":"...","commit_message":"..."}\n'
        )
        user = f"Issue:\n{issue_description}\n\nCodebase files:\n{json.dumps(codebase)[:200000]}"
        r = call_model(system, user, use_fast=False, max_tokens=4096)
        raw = (r.text or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if "```" in raw:
                raw = raw[: raw.rfind("```")].rstrip()
        data = json.loads(raw)
        file_rel = str(data["file"])
        fixed_code = str(data["fixed_code"])
        msg = str(data.get("commit_message") or f"Fix: {issue_description}")[:120]

        # Apply in local clone (best-effort) and push via API write.
        target = root / file_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fixed_code, encoding="utf-8")

        await self.write_file(repo, file_rel, fixed_code, msg)
        return {"fixed": True, "file": file_rel, "local_path": str(target), "commit_message": msg}

