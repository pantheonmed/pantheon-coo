"""
tools/deployer.py — Railway, Vercel, GitHub deploy helpers (CLI + API).
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from config import settings

GITHUB_API = "https://api.github.com"


def _ws() -> Path:
    return Path(settings.workspace_dir).resolve()


def _ensure_project_path(p: str) -> Path:
    path = Path(p).resolve()
    ws = _ws()
    if not _is_under(path, ws):
        raise ValueError("project_path must be under workspace_dir")
    return path


def _is_under(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


async def _deploy_to_railway(p: dict[str, Any]) -> dict[str, Any]:
    project_path = str(_ensure_project_path(str(p.get("project_path", ""))))
    service_name = str(p.get("service_name") or "web")
    port = int(p.get("port") or 8000)
    env_vars = p.get("env_vars") or {}
    if not settings.railway_token:
        raise ValueError("RAILWAY_TOKEN is not configured.")
    env = {**os.environ, "RAILWAY_TOKEN": settings.railway_token, "PORT": str(port)}
    for k, v in env_vars.items():
        env[str(k)] = str(v)
    cmd = ["railway", "up", "--service", service_name]
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        cwd=project_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    # Best-effort parse; Railway CLI output varies by version
    url_m = re.search(r"https://[\w.-]+\.up\.railway\.app", out)
    dep_m = re.search(r"deployment[_\s-]?id[:\s]+([a-zA-Z0-9-]+)", out, re.I)
    return {
        "url": url_m.group(0) if url_m else "",
        "deployment_id": dep_m.group(1) if dep_m else "",
        "status": "success" if proc.returncode == 0 else "failed",
        "cli_output_tail": out[-2000:],
    }


async def _deploy_to_vercel(p: dict[str, Any]) -> dict[str, Any]:
    project_path = str(_ensure_project_path(str(p.get("project_path", ""))))
    project_name = str(p.get("project_name") or "app")
    framework = str(p.get("framework") or "static")
    if not settings.vercel_token:
        raise ValueError("VERCEL_TOKEN is not configured.")
    env = {**os.environ, "VERCEL_TOKEN": settings.vercel_token}
    cmd = [
        "vercel",
        "--prod",
        "--yes",
        "--name",
        re.sub(r"[^a-zA-Z0-9_-]", "-", project_name)[:50],
    ]
    if framework == "nextjs":
        cmd.extend(["--build-env", "NEXT_TELEMETRY_DISABLED=1"])
    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        cwd=project_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    url_m = re.search(r"https://[\w.-]+\.vercel\.app", out)
    dep_m = re.search(r"Production:\s*(https://\S+)", out)
    url = ""
    if url_m:
        url = url_m.group(0)
    elif dep_m:
        url = dep_m.group(1).strip()
    return {
        "url": url,
        "deployment_id": f"vercel-{int(time.time())}" if proc.returncode == 0 else "",
        "status": "success" if proc.returncode == 0 else "failed",
        "output_tail": out[-1500:],
    }


async def _create_github_repo(p: dict[str, Any]) -> dict[str, Any]:
    if not settings.github_token:
        raise ValueError("GITHUB_TOKEN is not configured.")
    repo_name = str(p.get("repo_name", "")).strip()
    description = str(p.get("description") or "")
    private = bool(p.get("private", False))
    push_path = str(p.get("push_path") or "").strip()
    owner = (settings.github_username or "").strip()
    body = {"name": repo_name, "description": description, "private": private}
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{GITHUB_API}/user/repos", json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    html_url = data.get("html_url", "")
    clone_url = data.get("clone_url", "")
    if push_path and clone_url:
        pp = Path(push_path).resolve()
        if not _is_under(pp, _ws()):
            raise ValueError("push_path must be under workspace_dir")
        await asyncio.to_thread(
            _git_push_initial,
            str(pp),
            clone_url,
            settings.github_token,
        )
    return {"repo_url": html_url, "clone_url": clone_url}


def _git_push_initial(local_path: str, clone_url: str, token: str) -> None:
    """git init, commit, push using token in URL (HTTPS)."""
    path = Path(local_path)
    path.mkdir(parents=True, exist_ok=True)
    # embed token for HTTPS push: https://TOKEN@github.com/...
    if clone_url.startswith("https://") and token:
        auth_url = clone_url.replace("https://", f"https://{token}@")
    else:
        auth_url = clone_url
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "coo@pantheon.local"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Pantheon COO"], cwd=path, check=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text("# Pantheon COO export\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit from Pantheon COO"],
        cwd=path,
        check=False,
        capture_output=True,
    )
    subprocess.run(["git", "branch", "-M", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=path, check=False, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=path, check=True, capture_output=True)


def _git_commit_push(local_path: str, repo_url: str, msg: str, token: str) -> str:
    path = Path(local_path)
    if not (path / ".git").exists():
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "coo@pantheon.local"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Pantheon COO"], cwd=path, check=True)
    auth_url = repo_url
    if token and repo_url.startswith("https://"):
        auth_url = repo_url.replace("https://", f"https://{token}@", 1)
    subprocess.run(["git", "remote", "remove", "origin"], cwd=path, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", auth_url], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", msg], cwd=path, check=False, capture_output=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=path, check=False, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=path, check=True, capture_output=True)
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


async def _push_to_github(p: dict[str, Any]) -> dict[str, Any]:
    local_path = str(Path(str(p.get("local_path", ""))).resolve())
    repo_url = str(p.get("repo_url", "")).strip()
    msg = str(p.get("commit_message") or "Update from Pantheon COO")
    lp = Path(local_path)
    if not _is_under(lp, _ws()):
        raise ValueError("local_path must be under workspace_dir")
    token = settings.github_token or ""
    sha = await asyncio.to_thread(_git_commit_push, local_path, repo_url, msg, token)
    return {"success": True, "commit_sha": sha}


async def _check_deployment(p: dict[str, Any]) -> dict[str, Any]:
    url = str(p.get("url", "")).strip()
    if not url:
        raise ValueError("url is required.")
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url)
        ms = int((time.monotonic() - t0) * 1000)
        live = 200 <= r.status_code < 400
        return {"live": live, "response_time_ms": ms, "status_code": r.status_code}
    except httpx.HTTPError:
        ms = int((time.monotonic() - t0) * 1000)
        return {"live": False, "response_time_ms": ms, "status_code": 0}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "deploy_to_railway": _deploy_to_railway,
        "deploy_to_vercel": _deploy_to_vercel,
        "create_github_repo": _create_github_repo,
        "push_to_github": _push_to_github,
        "check_deployment": _check_deployment,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown deployer action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
