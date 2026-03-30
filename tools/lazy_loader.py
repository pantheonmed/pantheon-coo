"""
Lazy import helper for heavy tool modules (reduces cold import cost).
"""
from __future__ import annotations

import importlib
from typing import Any

_loaded_tools: dict[str, Any] = {}


async def get_tool(tool_name: str) -> Any:
    """Return the tools.<tool_name> module, importing on first use."""
    if tool_name not in _loaded_tools:
        _loaded_tools[tool_name] = importlib.import_module(f"tools.{tool_name}")
    return _loaded_tools[tool_name]
