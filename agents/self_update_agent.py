"""
agents/self_update_agent.py
───────────────────────────
SelfUpdateAgent — pull Pantheon COO OS repo, apply improvements, run tests,
prepare diff, and (after explicit confirmation) push to main.

This is a safety-first implementation:
  - Always creates a backup branch on origin before pushing main
  - Always runs full pytest before allowing push
  - Requires explicit confirmation ("haan") to push
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agents.model_router import call_model
from config import settings
from tools import terminal as term_tool
from tools import filesystem as fs_tool


@dataclass
class PendingSelfUpdate:
    token: str
    repo: str
    local_path: str
    backup_branch: str
    commit_sha: str
    diff: str
    files_affected: list[str]
    instruction: str
    created_at: float


_PENDING: dict[str, PendingSelfUpdate] = {}


def get_pending(token: str) -> Optional[PendingSelfUpdate]:
    return _PENDING.get(token)


def _clip(s: str, n: int = 9000) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"


async def _run(cmd: str, cwd: str, timeout: int = 1800) -> dict[str, Any]:
    return await term_tool.execute(
        "run_command",
        {"command": cmd, "cwd": cwd, "timeout": timeout},
    )


class SelfUpdateAgent:
    name = "self_update_agent"

    async def pull_repo(self, repo: str, local_path: str) -> dict[str, Any]:
        from agents.github_agent import GitHubAgent

        return await GitHubAgent().pull_repo(repo, local_path)

    async def _plan_changes(self, instruction: str) -> dict[str, Any]:
        """
        Produce a lightweight plan and file hints; actual patching uses subsequent step.
        """
        system = (
            "You are the maintainer of Pantheon COO OS. For the given instruction, return STRICT JSON:\n"
            '{"plan":["..."],"file_globs":["..."],"estimated_time":"..."}\n'
            "Keep it short and realistic."
        )
        r = call_model(system, instruction, use_fast=True, max_tokens=1024)
        raw = (r.text or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if "```" in raw:
                raw = raw[: raw.rfind("```")].rstrip()
        try:
            return json.loads(raw)
        except Exception:
            return {"plan": ["Analyze code", "Make changes", "Run tests", "Prepare diff for confirmation"], "file_globs": [], "estimated_time": "10-20 min"}

    async def _propose_patch(self, instruction: str, codebase: dict[str, str], test_output: str) -> dict[str, Any]:
        """
        Ask model for a patch-set as full file replacements (simple but reliable).
        Returns JSON: {"files":[{"path":"...","content":"..."}], "message":"..."}
        """
        system = (
            "You are an expert Python/FastAPI engineer. You will receive an instruction, a small codebase snapshot, "
            "and failing test output (or empty if none). Return STRICT JSON only:\n"
            '{"message":"commit message","files":[{"path":"relative/path.py","content":"FULL FILE CONTENT"}]}\n'
            "Rules:\n"
            "- Only include files you must change.\n"
            "- content must be full file content.\n"
            "- Keep changes minimal and safe.\n"
        )
        user = (
            f"Instruction:\n{instruction}\n\n"
            f"Test output (if any):\n{_clip(test_output, 12000)}\n\n"
            f"Codebase snapshot (path -> content):\n{_clip(json.dumps(codebase), 180000)}"
        )
        r = call_model(system, user, use_fast=False, max_tokens=4096)
        raw = (r.text or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if "```" in raw:
                raw = raw[: raw.rfind("```")].rstrip()
        return json.loads(raw)

    async def _read_relevant_files(self, repo_root: Path, file_globs: list[str]) -> dict[str, str]:
        """
        Best-effort read of relevant files (capped).
        """
        out: dict[str, str] = {}
        patterns = [g for g in (file_globs or []) if isinstance(g, str) and g.strip()]
        # Default: a few key files
        if not patterns:
            patterns = ["main.py", "orchestrator.py", "security/auth.py", "memory/store.py", "static/dashboard.html", "whatsapp.py"]
        # Convert glob-ish to actual paths (very small matcher)
        candidates: list[Path] = []
        for p in patterns[:20]:
            if "*" in p or "?" in p or "[" in p:
                candidates.extend(repo_root.glob(p))
            else:
                candidates.append(repo_root / p)
        seen = set()
        for fp in candidates:
            try:
                rp = fp.resolve()
            except Exception:
                continue
            if rp in seen:
                continue
            seen.add(rp)
            if not rp.is_file():
                continue
            rel = str(rp.relative_to(repo_root))
            try:
                out[rel] = rp.read_text(encoding="utf-8")[:20000]
            except Exception:
                continue
            if len(out) >= 25:
                break
        return out

    async def prepare_self_update(
        self,
        *,
        repo: str,
        instruction: str,
        local_path: str = "/tmp/pantheon_v2/pantheon_self_update",
    ) -> dict[str, Any]:
        """
        Pull repo, propose and apply patch, run tests, prepare diff, and store pending confirmation token.
        Does NOT push.
        """
        if not (settings.github_token or "").strip():
            raise RuntimeError("GITHUB_TOKEN is required for self-update flow")

        plan = await self._plan_changes(instruction)
        await self.pull_repo(repo, local_path)
        root = Path(local_path).resolve()

        # Ensure we're on main and up to date
        await _run("git fetch origin", str(root), timeout=300)
        await _run("git checkout main", str(root), timeout=60)
        await _run("git reset --hard origin/main", str(root), timeout=60)

        backup_branch = f"backup/self-update-{int(time.time())}"
        await _run(f"git branch {backup_branch} origin/main", str(root), timeout=30)

        # Read relevant files for patch proposal
        codebase = await self._read_relevant_files(root, plan.get("file_globs") or [])

        # First patch proposal (no failing tests yet)
        patch = await self._propose_patch(instruction, codebase, test_output="")
        files = patch.get("files") or []
        message = str(patch.get("message") or "Self-update")

        files_affected: list[str] = []
        for f in files[:30]:
            rel = str(f.get("path") or "").strip().lstrip("/")
            content = str(f.get("content") or "")
            if not rel:
                continue
            abs_path = str((root / rel).resolve())
            await fs_tool.execute("write_file", {"path": abs_path, "content": content})
            files_affected.append(rel)

        # Run tests with auto-fix loop (max 3 tries)
        last_out = ""
        for attempt in range(1, 4):
            tr = await _run("python3 -m pytest tests/ -q", str(root), timeout=1800)
            out = "\n".join([x for x in [tr.get("stdout") or "", tr.get("stderr") or ""] if x]).strip()
            last_out = out
            if int(tr.get("exit_code", 1)) == 0:
                break
            # Propose a fix based on failing output
            codebase2 = await self._read_relevant_files(root, list(set(files_affected))[:10])
            patch2 = await self._propose_patch(
                f"{instruction}\n\nFix failing tests (attempt {attempt})",
                codebase2,
                test_output=out,
            )
            files2 = patch2.get("files") or []
            for f2 in files2[:30]:
                rel2 = str(f2.get("path") or "").strip().lstrip("/")
                content2 = str(f2.get("content") or "")
                if not rel2:
                    continue
                abs_path2 = str((root / rel2).resolve())
                await fs_tool.execute("write_file", {"path": abs_path2, "content": content2})
                if rel2 not in files_affected:
                    files_affected.append(rel2)
            message = str(patch2.get("message") or message)

        # If still failing, return without pending token
        tr_final = await _run("python3 -m pytest tests/ -q", str(root), timeout=1800)
        if int(tr_final.get("exit_code", 1)) != 0:
            out = "\n".join([x for x in [tr_final.get("stdout") or "", tr_final.get("stderr") or ""] if x]).strip()
            return {
                "plan": plan.get("plan") or [],
                "files_affected": files_affected,
                "estimated_time": plan.get("estimated_time") or "unknown",
                "confirmation_needed": False,
                "success": False,
                "error": "Tests are still failing after auto-fix loop (max 3 tries).",
                "test_output": _clip(out, 12000),
            }

        # Commit changes locally (do not push yet)
        await _run("git add -A", str(root), timeout=60)
        await _run(f"git commit -m {json.dumps(message)}", str(root), timeout=60)
        sha = (await _run("git rev-parse HEAD", str(root), timeout=20)).get("stdout") or ""

        diff = (await _run("git diff origin/main...HEAD", str(root), timeout=60)).get("stdout") or ""
        diff = _clip(diff, 20000)

        token = secrets.token_urlsafe(16)
        _PENDING[token] = PendingSelfUpdate(
            token=token,
            repo=repo,
            local_path=str(root),
            backup_branch=backup_branch,
            commit_sha=str(sha).strip(),
            diff=diff,
            files_affected=files_affected,
            instruction=instruction,
            created_at=time.time(),
        )
        return {
            "plan": plan.get("plan") or [],
            "files_affected": files_affected,
            "estimated_time": plan.get("estimated_time") or "unknown",
            "confirmation_needed": True,
            "token": token,
            "diff": diff,
        }

    async def confirm_and_push(self, token: str, decision: str) -> dict[str, Any]:
        p = _PENDING.get(token)
        if not p:
            return {"ok": False, "error": "Unknown or expired token"}
        dec = (decision or "").strip().lower()
        if dec in ("nahi", "no", "cancel"):
            _PENDING.pop(token, None)
            return {"ok": True, "pushed": False, "message": "Cancelled. No changes were pushed."}
        if dec not in ("haan", "yes", "ok", "push"):
            return {"ok": False, "error": "Decision must be 'haan' or 'nahi'."}

        root = p.local_path

        # Safety: run full tests again right before push
        tr = await _run("python3 -m pytest tests/ -q", root, timeout=1800)
        if int(tr.get("exit_code", 1)) != 0:
            out = "\n".join([x for x in [tr.get("stdout") or "", tr.get("stderr") or ""] if x]).strip()
            return {"ok": False, "pushed": False, "error": "Tests failed before push", "test_output": _clip(out, 12000)}

        # Push backup branch first (points to origin/main at time of prepare)
        b1 = await _run(f"git push origin {p.backup_branch}:{p.backup_branch}", root, timeout=300)
        if int(b1.get("exit_code", 1)) != 0:
            return {"ok": False, "pushed": False, "error": "Failed to push backup branch", "details": b1}

        # Push main
        b2 = await _run("git push origin HEAD:main", root, timeout=300)
        if int(b2.get("exit_code", 1)) != 0:
            return {"ok": False, "pushed": False, "error": "Failed to push main", "details": b2}

        _PENDING.pop(token, None)
        return {
            "ok": True,
            "pushed": True,
            "backup_branch": p.backup_branch,
            "commit_sha": p.commit_sha,
            "message": "Pushed to main. Railway should auto-deploy.",
        }

