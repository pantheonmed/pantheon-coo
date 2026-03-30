"""
tools/image_analyzer.py — Claude vision (describe, OCR, compare, documents).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from config import settings


def _read_image_b64(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    mt = mimetypes.types_map.get(ext) or "image/jpeg"
    if ext == ".jpg":
        mt = "image/jpeg"
    raw = path.read_bytes()
    return base64.standard_b64encode(raw).decode("ascii"), mt


def _vision_user_message(image_paths: list[Path], text_prompt: str) -> list[dict[str, Any]]:
    """Single user message with images + text for Claude Messages API."""
    content: list[dict[str, Any]] = []
    for p in image_paths:
        b64, mt = _read_image_b64(p)
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mt, "data": b64},
            }
        )
    content.append({"type": "text", "text": text_prompt})
    return [{"role": "user", "content": content}]


def _call_vision(system: str, messages: list[dict[str, Any]], max_tokens: int = 2048) -> str:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for image analysis.")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    parts = []
    for b in msg.content:
        if b.type == "text":
            parts.append(b.text)
    return "".join(parts).strip()


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def _analyze_image(p: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(p.get("image_path", ""))).resolve()
    q = str(p.get("question") or "What is in this image?")
    blocks = _vision_user_message(
        [path],
        q + '\nRespond with JSON: {"description": "...", "objects_found": [], "text_extracted": ""}',
    )
    raw = _call_vision(
        "You are a vision assistant. Reply with only valid JSON.",
        blocks,
    )
    data = _parse_json_loose(raw)
    return {
        "description": data.get("description") or raw[:2000],
        "objects_found": data.get("objects_found") if isinstance(data.get("objects_found"), list) else [],
        "text_extracted": str(data.get("text_extracted") or ""),
    }


async def _extract_text_from_image(p: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(p.get("image_path", ""))).resolve()
    blocks = _vision_user_message(
        [path],
        'Extract all visible text from this image. Reply with JSON only: {"text": "...", "confidence": "high|medium|low"}',
    )
    raw = _call_vision("OCR assistant. JSON only.", blocks)
    data = _parse_json_loose(raw)
    conf = str(data.get("confidence") or "medium").lower()
    if conf not in ("high", "medium", "low"):
        conf = "medium"
    return {"text": str(data.get("text") or raw), "confidence": conf}


async def _compare_images(p: dict[str, Any]) -> dict[str, Any]:
    p1 = Path(str(p.get("image1_path", ""))).resolve()
    p2 = Path(str(p.get("image2_path", ""))).resolve()
    focus = str(p.get("comparison_focus") or "differences")
    blocks = _vision_user_message(
        [p1, p2],
        f"Compare these two images focusing on: {focus}. "
        'JSON only: {"similarities": [], "differences": [], "summary": "..."}',
    )
    raw = _call_vision("Vision comparison. JSON only.", blocks)
    data = _parse_json_loose(raw)
    return {
        "similarities": data.get("similarities") if isinstance(data.get("similarities"), list) else [],
        "differences": data.get("differences") if isinstance(data.get("differences"), list) else [],
        "summary": str(data.get("summary") or raw[:1500]),
    }


async def _analyze_document_image(p: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(p.get("image_path", ""))).resolve()
    doc_type = str(p.get("document_type") or "report").lower()
    blocks = _vision_user_message(
        [path],
        f"This is a {doc_type} document image. Extract structured fields as JSON appropriate for type {doc_type}.",
    )
    raw = _call_vision("Document understanding. Reply with one JSON object only.", blocks)
    data = _parse_json_loose(raw)
    if not data:
        return {"document_type": doc_type, "raw": raw[:4000]}
    data["document_type"] = doc_type
    return data


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "analyze_image": _analyze_image,
        "extract_text_from_image": _extract_text_from_image,
        "compare_images": _compare_images,
        "analyze_document_image": _analyze_document_image,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown image_analyzer action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
