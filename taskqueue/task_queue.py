"""
taskqueue/task_queue.py — FIFO task queue for worker pool (Task 90).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from config import settings

_lock = asyncio.Lock()
_waiting: list[dict[str, Any]] = []
_task_id_to_position_cache: dict[str, int] = {}


class TaskQueue:
    def __init__(self) -> None:
        self._redis_available = bool(
            getattr(settings, "redis_enabled", False) and (settings.redis_url or "").strip()
        )

    async def enqueue(
        self,
        task_id: str,
        command: str,
        priority: int = 1,
        user_id: str = "",
        context: Optional[dict] = None,
    ) -> int:
        job = {
            "task_id": task_id,
            "command": command,
            "user_id": user_id or "",
            "priority": int(priority),
            "context": dict(context or {}),
        }
        async with _lock:
            _waiting.append(job)
            _waiting.sort(key=lambda j: -j["priority"])
            pos = len(_waiting)
            _task_id_to_position_cache[task_id] = pos
        return pos

    async def dequeue(self) -> Optional[dict[str, Any]]:
        async with _lock:
            if not _waiting:
                return None
            job = _waiting.pop(0)
            _task_id_to_position_cache.pop(job.get("task_id", ""), None)
            for i, j in enumerate(_waiting, start=1):
                _task_id_to_position_cache[j["task_id"]] = i
            return job

    async def queue_depth(self) -> int:
        async with _lock:
            return len(_waiting)

    async def user_position(self, task_id: str) -> int:
        async with _lock:
            for i, j in enumerate(_waiting, start=1):
                if j.get("task_id") == task_id:
                    return i
            return int(_task_id_to_position_cache.get(task_id, 0))


_queue = TaskQueue()


def get_task_queue() -> TaskQueue:
    return _queue


async def _worker_loop(worker_id: str) -> None:
    import orchestrator

    while True:
        try:
            job = await _queue.dequeue()
            if not job:
                await asyncio.sleep(0.25)
                continue
            tid = job["task_id"]
            ctx = dict(job.get("context") or {})
            ctx.setdefault("worker_id", worker_id)
            await orchestrator.run(
                task_id=tid,
                command=job["command"],
                context=ctx,
                dry_run=False,
            )
        except Exception as e:
            print(f"[worker {worker_id}] error: {e}")
            await asyncio.sleep(1.0)


def start_worker_tasks() -> list[asyncio.Task]:
    n = max(1, int(getattr(settings, "worker_count", 2) or 2))
    out: list[asyncio.Task] = []
    for i in range(n):
        out.append(asyncio.create_task(_worker_loop(f"w{i}")))
    return out
