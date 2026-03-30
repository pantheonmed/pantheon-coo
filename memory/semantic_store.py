"""
memory/semantic_store.py — Long-term semantic-ish memory (tags + keyword recall).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from config import settings


class SemanticMemory:
    def __init__(self, db_path: str):
        self._db_path = db_path

    async def store_memory(
        self,
        task_id: str,
        content: str,
        memory_type: str,
        tags: list[str],
        importance: float = 0.5,
        owner_user_id: Optional[str] = None,
    ) -> str:
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO semantic_memories
                (memory_id, task_id, owner_user_id, content, memory_type,
                 tags_json, importance, access_count, created_at, deleted)
                VALUES (?,?,?,?,?,?,?,0,?,0)
                """,
                (
                    memory_id,
                    task_id,
                    owner_user_id,
                    content,
                    memory_type,
                    json.dumps(list(tags or [])),
                    float(importance),
                    now,
                ),
            )
            await db.commit()
        return memory_id

    async def _extract_keywords(self, query: str) -> list[str]:
        q = (query or "").strip()
        if not q:
            return []
        if not settings.anthropic_api_key:
            return [w.lower() for w in q.replace(",", " ").split() if len(w) > 2][:16]

        def _call() -> str:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            msg = client.messages.create(
                model=settings.claude_model_fast,
                max_tokens=120,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Extract 5-12 lowercase keywords from this query for memory search. "
                            "Reply with JSON only: {\"keywords\":[\"a\",\"b\"]}\n\n" + q
                        ),
                    }
                ],
            )
            block = msg.content[0]
            return getattr(block, "text", str(block))

        raw = await asyncio.to_thread(_call)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                kws = data.get("keywords") or []
                return [str(x).lower() for x in kws if x][:16]
        except Exception:
            pass
        return [w.lower() for w in q.replace(",", " ").split() if len(w) > 2][:16]

    async def recall(
        self,
        query: str,
        memory_type: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        kws = await self._extract_keywords(query)
        if not kws:
            kws = ["__none__"]
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM semantic_memories WHERE deleted=0 ORDER BY importance DESC, created_at DESC LIMIT 200",
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        mt = (memory_type or "").strip().lower()
        scored: list[tuple[float, dict]] = []
        for r in rows:
            if mt and str(r.get("memory_type") or "").lower() != mt:
                continue
            try:
                tags = json.loads(r.get("tags_json") or "[]")
            except Exception:
                tags = []
            tags_l = [str(t).lower() for t in tags]
            content_l = (r.get("content") or "").lower()
            score = float(r.get("importance") or 0.5)
            for kw in kws:
                if kw in content_l:
                    score += 0.4
                if any(kw in t for t in tags_l):
                    score += 0.6
            scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        out = []
        for _, r in scored[:limit]:
            out.append(
                {
                    "memory_id": r["memory_id"],
                    "task_id": r.get("task_id"),
                    "content": r.get("content"),
                    "memory_type": r.get("memory_type"),
                    "tags": json.loads(r.get("tags_json") or "[]"),
                    "importance": r.get("importance"),
                    "created_at": r.get("created_at"),
                }
            )
        return out
