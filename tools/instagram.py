"""
tools/instagram.py — Instagram content + DM helpers (stubs; requires Meta Graph in production).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from config import settings
from security.sandbox import workspace_root


async def _post_image(p: dict[str, Any]) -> dict[str, Any]:
    path = str(p.get("image_path", "")).strip()
    if not path:
        raise ValueError("image_path is required")
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise ValueError("image_path must exist")
    ws = workspace_root()
    if not str(resolved).startswith(str(ws)) and not str(resolved).startswith("/tmp/pantheon_v2"):
        raise ValueError("image must be under workspace")
    return {"status": "planned", "caption_len": len(str(p.get("caption", "")))}


async def _post_reel_script(p: dict[str, Any]) -> dict[str, Any]:
    ws = workspace_root()
    out = ws / "instagram_reel_script.md"
    text = f"# Reel\n\nHook: {p.get('hook','')}\n\nScript:\n{p.get('script','')}\n\nCTA: {p.get('cta','')}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return {"saved_to": str(out)}


async def _send_dm(p: dict[str, Any]) -> dict[str, Any]:
    if not settings.instagram_username:
        return {"status": "skipped", "reason": "INSTAGRAM_USERNAME not set"}
    return {"status": "queued", "to": p.get("username")}


async def _reply_to_comments(p: dict[str, Any]) -> dict[str, Any]:
    return {"status": "template_ready", "post_url": p.get("post_url")}


async def _get_analytics(p: dict[str, Any]) -> dict[str, Any]:
    period = str(p.get("period", "week"))
    return {"followers": 0, "reach": 0, "engagement_rate": 0.0, "period": period}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "post_image": _post_image,
        "post_reel_script": _post_reel_script,
        "send_dm": _send_dm,
        "reply_to_comments": _reply_to_comments,
        "get_analytics": _get_analytics,
    }
    fn = dispatch.get(act)
    if not fn:
        raise ValueError(f"Unknown instagram action '{action}'")
    return await fn(params)
