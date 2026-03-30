"""
branding_runtime.py — optional overrides from workspace/branding.json (white-label).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import settings

_overrides: dict[str, Any] = {}


def load_branding_file() -> None:
    global _overrides
    path = Path(settings.workspace_dir).resolve() / "branding.json"
    if not path.is_file():
        _overrides = {}
        return
    try:
        _overrides = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(_overrides, dict):
            _overrides = {}
    except Exception:
        _overrides = {}


def get_public_branding() -> dict[str, Any]:
    o = _overrides
    return {
        "name": o.get("name", settings.white_label_name),
        "logo_url": o.get("logo_url", settings.white_label_logo_url),
        "primary_color": o.get("primary_color", settings.white_label_primary_color),
        "support_email": o.get("support_email", settings.white_label_support_email),
        "domain": o.get("domain", settings.white_label_domain),
        "powered_by": "Pantheon COO OS",
    }


def update_branding(**kwargs: Any) -> dict[str, Any]:
    global _overrides
    allowed = {"name", "logo_url", "primary_color", "support_email", "domain"}
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            _overrides[k] = v
    path = Path(settings.workspace_dir).resolve() / "branding.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_overrides, indent=2), encoding="utf-8")
    return get_public_branding()


def admin_get_branding() -> dict[str, Any]:
    return {**get_public_branding(), "raw_overrides": dict(_overrides)}
