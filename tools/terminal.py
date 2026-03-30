"""tools/terminal.py — Safe subprocess execution."""
import asyncio
from typing import Any
from config import settings


async def execute(action: str, params: dict[str, Any]) -> Any:
    if action != "run_command":
        raise ValueError(f"Unknown terminal action: '{action}'. Available: ['run_command']")
    return await _run(params)


async def _run(p: dict) -> dict:
    cmd: str = p["command"]
    cwd: str | None = p.get("cwd")
    timeout: int = p.get("timeout", settings.agent_timeout_seconds)

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"exit_code": -1, "stdout": "", "stderr": f"Timed out after {timeout}s", "success": False}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e), "success": False}

    return {
        "exit_code": proc.returncode,
        "stdout": out.decode(errors="replace").strip(),
        "stderr": err.decode(errors="replace").strip(),
        "success": proc.returncode == 0,
    }
