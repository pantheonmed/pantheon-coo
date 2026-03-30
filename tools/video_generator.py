"""
tools/video_generator.py — Video scripts, HTML previews, optional D-ID / ffmpeg.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

from agents.model_router import call_model
from config import settings

_DID_API = "https://api.d-id.com"


def _out_dir() -> Path:
    d = Path(settings.workspace_dir).resolve() / "video"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(s: str, n: int = 40) -> str:
    x = re.sub(r"[^a-zA-Z0-9_-]+", "_", (s or "vid").strip())[:n].strip("_")
    return x or "video"


async def _text_to_video(p: dict[str, Any]) -> dict[str, Any]:
    script = str(p.get("script", "")).strip()
    style = str(p.get("style") or "professional")
    duration = int(p.get("duration_seconds") or 60)
    voice = str(p.get("voice") or "female")
    language = str(p.get("language") or "en")
    base = _out_dir() / _slug(script[:30])
    script_path = base.with_suffix(".txt")
    script_path.write_text(script, encoding="utf-8")
    html_path = base.with_suffix(".html")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Video preview</title></head>
<body style="font-family:system-ui;max-width:720px;margin:2rem auto;">
<h1>Video preview (fallback)</h1>
<p><b>Style:</b> {style} | <b>Duration target:</b> {duration}s | <b>Voice:</b> {voice} | <b>Lang:</b> {language}</p>
<pre style="white-space:pre-wrap;background:#f4f4f4;padding:1rem;">{script}</pre>
<p><i>Configure DID_API_KEY or SYNTHESIA_API_KEY and VIDEO_GENERATION_ENABLED for API rendering.</i></p>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    video_url = ""
    if settings.video_generation_enabled and settings.did_api_key:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{_DID_API}/talks",
                    headers={
                        "Authorization": f"Bearer {settings.did_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "script": {
                            "type": "text",
                            "input": script,
                            "provider": {"type": "microsoft", "voice_id": voice},
                        }
                    },
                )
                if r.status_code < 400:
                    data = r.json()
                    video_url = str(data.get("result_url") or data.get("url") or "")
        except httpx.HTTPError:
            pass
    return {
        "video_url": video_url,
        "video_path": str(html_path),
        "duration": duration,
        "script_path": str(script_path),
    }


async def _images_to_slideshow(p: dict[str, Any]) -> dict[str, Any]:
    paths = [str(x) for x in (p.get("image_paths") or [])]
    per = int(p.get("duration_per_image") or 3)
    transition = str(p.get("transition") or "fade")
    _music = bool(p.get("background_music", False))
    out_name = str(p.get("output_filename") or "slideshow.mp4")
    ws = Path(settings.workspace_dir).resolve()
    resolved = []
    for ps in paths:
        pp = Path(ps).resolve()
        if not str(pp).startswith(str(ws)):
            raise ValueError("image_paths must be under workspace_dir")
        resolved.append(pp)
    out_dir = _out_dir()
    total_dur = per * max(len(resolved), 1)
    # Try ffmpeg concat
    stem = Path(out_name).stem[:60] or "slideshow"
    mp4_path = out_dir / f"{stem}.mp4"
    if resolved:
        list_file = out_dir / "ffmpeg_concat.txt"
        lines = [f"file '{p}'\nduration {per}" for p in resolved]
        if lines:
            lines[-1] = f"file '{resolved[-1]}'"
        list_file.write_text("\n".join(lines), encoding="utf-8")
        try:
            await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_file),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(mp4_path),
                ],
                capture_output=True,
                timeout=300,
                check=False,
            )
            if mp4_path.is_file() and mp4_path.stat().st_size > 0:
                return {"output_path": str(mp4_path), "total_duration": total_dur}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    # HTML fallback
    html_path = out_dir / (Path(out_name).stem + "_slideshow.html")
    imgs = "\n".join(f'<img src="file://{p}" style="max-width:100%;display:block;margin:1rem auto;" />' for p in resolved)
    html_path.write_text(
        f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Slideshow</title>
<style>body{{font-family:sans-serif}} .slide{{min-height:400px}}</style></head><body>
<h1>Slideshow ({transition})</h1>{imgs or "<p>No images</p>"}
<p>~{per}s per image suggested. total ~{total_dur}s</p></body></html>""",
        encoding="utf-8",
    )
    return {"output_path": str(html_path), "total_duration": total_dur}


async def _create_product_demo(p: dict[str, Any]) -> dict[str, Any]:
    name = str(p.get("product_name", ""))
    feats = p.get("features") or []
    aud = str(p.get("target_audience", ""))
    cta = str(p.get("cta", ""))
    feat_txt = ", ".join(str(x) for x in feats)
    resp = call_model(
        system="You write tight product demo voiceover scripts.",
        user=f"Product: {name}\nFeatures: {feat_txt}\nAudience: {aud}\nCTA: {cta}\nWrite 45–90s spoken script.",
        use_fast=True,
    )
    sp = _out_dir() / f"demo_script_{_slug(name)}.md"
    sp.write_text(resp.text, encoding="utf-8")
    vid = await _text_to_video({"script": resp.text, "style": "professional", "duration_seconds": 60})
    return {"script_path": str(sp), "video_path": vid.get("video_path", "")}


async def _create_social_video(p: dict[str, Any]) -> dict[str, Any]:
    platform = str(p.get("platform") or "instagram")
    topic = str(p.get("topic", ""))
    dur = int(p.get("duration_seconds") or 30)
    resp = call_model(
        system="You write short-form vertical video scripts for social platforms in India.",
        user=f"Platform: {platform}\nTopic: {topic}\nTarget length: {dur}s\nInclude hook, body, CTA. Add 5–12 hashtags line at end.",
        use_fast=True,
    )
    base = _out_dir() / f"social_{_slug(platform)}_{_slug(topic)}"
    sp = base.with_suffix(".md")
    sp.write_text(resp.text, encoding="utf-8")
    tags = re.findall(r"#[\w\u0900-\u097F]+", resp.text)
    meta = {"platform": platform, "topic": topic, "duration_seconds": dur, "hashtags": tags}
    base.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"script_path": str(sp), "recommended_hashtags": tags[:15]}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "text_to_video": _text_to_video,
        "images_to_slideshow": _images_to_slideshow,
        "create_product_demo": _create_product_demo,
        "create_social_video": _create_social_video,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown video_generator action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
