"""
agents/auto_fixer.py
────────────────────
AutoFixer — save, run, auto-fix loop for generated code.

Designed for autonomous developer flows:
  - write code to file (workspace)
  - execute it (terminal tool)
  - if error: ask model for a corrected full file
  - repeat up to max_attempts
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agents.model_router import call_model
from config import settings
from tools import filesystem as fs_tool
from tools import terminal as term_tool


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str


class AutoFixer:
    name = "auto_fixer"
    max_attempts = 5

    system_prompt = (
        "You are an expert software developer. You will be given a full source file and an error.\n"
        "Return ONLY the full corrected code for the file. No markdown fences. No explanation.\n"
        "Keep behavior the same except for fixing the error.\n"
    )

    def _clip(self, s: str, n: int = 8000) -> str:
        if not s:
            return ""
        return s if len(s) <= n else s[: n - 1] + "…"

    async def _write(self, file_path: str, code: str) -> None:
        await fs_tool.execute("write_file", {"path": file_path, "content": code})

    async def _run(self, file_path: str, *, cwd: Optional[str] = None) -> RunResult:
        res = await term_tool.execute(
            "run_command",
            {
                "command": f"python3 {file_path}",
                "cwd": cwd,
                "timeout": int(getattr(settings, "agent_timeout_seconds", 90) or 90),
            },
        )
        return RunResult(
            exit_code=int(res.get("exit_code", -1)),
            stdout=str(res.get("stdout") or ""),
            stderr=str(res.get("stderr") or ""),
        )

    async def _fix(self, code: str, error: str, *, attempt: int) -> str:
        user = (
            "Fix the error in this code. Return ONLY the full fixed code.\n\n"
            f"Attempt: {attempt}\n\n"
            f"Error:\n{self._clip(error, 6000)}\n\n"
            f"Code:\n{self._clip(code, 14000)}\n"
        )
        r = call_model(self.system_prompt, user, use_fast=True, max_tokens=4096)
        fixed = (r.text or "").strip()
        if fixed.startswith("```"):
            fixed = "\n".join(fixed.split("\n")[1:])
            if "```" in fixed:
                fixed = fixed[: fixed.rfind("```")].rstrip()
        return fixed

    async def fix_and_run(
        self,
        *,
        code: str,
        language: str = "python",
        file_path: str,
        cwd: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Loop:
          1) Save code to file_path
          2) Run it
          3) If error: model fixes full file
          4) Repeat until success or max_attempts
        """
        if (language or "").lower() != "python":
            return {"success": False, "attempts": 0, "last_error": "AutoFixer currently supports python only"}

        if not file_path:
            return {"success": False, "attempts": 0, "last_error": "file_path is required"}

        # Ensure parent exists (best-effort)
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        last: RunResult | None = None
        current = code or ""

        base_cwd = cwd or str(Path(settings.workspace_dir).resolve())

        for attempt in range(1, int(self.max_attempts) + 1):
            await self._write(file_path, current)
            last = await self._run(file_path, cwd=base_cwd)
            if last.exit_code == 0:
                return {
                    "success": True,
                    "output": last.stdout,
                    "stderr": last.stderr,
                    "exit_code": last.exit_code,
                    "attempts": attempt,
                    "final_code": current,
                    "file_path": file_path,
                }
            current = await self._fix(current, last.stderr or last.stdout, attempt=attempt)

        return {
            "success": False,
            "attempts": int(self.max_attempts),
            "last_error": (last.stderr if last else "") or "Unknown error",
            "exit_code": (last.exit_code if last else -1),
            "file_path": file_path,
        }

