"""Per-task context for tools (user_id during executor run)."""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_task_user_id: ContextVar[Optional[str]] = ContextVar("task_user_id", default=None)


def set_task_user_id(user_id: Optional[str]):
    return _task_user_id.set(user_id)


def get_task_user_id() -> Optional[str]:
    return _task_user_id.get()


def reset_task_user_id(token) -> None:
    _task_user_id.reset(token)
