"""
ml/data_collector.py — Export high-quality task traces as JSONL for fine-tuning (Task 91).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import memory.store as store


class TrainingDataCollector:
    async def collect_successful_tasks(
        self,
        limit: int = 1000,
        min_score: float = 0.9,
    ) -> list[dict[str, Any]]:
        async with store.get_pool().acquire() as db:
            async with db.execute(
                """SELECT command, plan_json FROM tasks
                   WHERE status='done' AND eval_score >= ?
                   ORDER BY created_at DESC LIMIT ?""",
                (min_score, int(limit)),
            ) as cur:
                rows = await cur.fetchall()
        out: list[dict[str, Any]] = []
        for cmd, plan_json in rows:
            out.append(
                {
                    "messages": [
                        {"role": "user", "content": cmd},
                        {"role": "assistant", "content": plan_json or "{}"},
                    ]
                }
            )
        return out

    async def collect_reasoning_examples(self) -> list[dict[str, Any]]:
        async with store.get_pool().acquire() as db:
            async with db.execute(
                "SELECT command, goal_type FROM tasks WHERE status='done' LIMIT 200"
            ) as cur:
                rows = await cur.fetchall()
        return [
            {"command": r[0], "goal_type": r[1] or "unknown", "pair_type": "reasoning"}
            for r in rows
        ]

    async def export_jsonl(
        self,
        output_path: str,
        data_type: str = "planning",
    ) -> int:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if data_type == "reasoning":
            rows = await self.collect_reasoning_examples()
        else:
            rows = await self.collect_successful_tasks(limit=500, min_score=0.85)
        n = 0
        with p.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, default=str) + "\n")
                n += 1
        return n

    async def get_stats(self) -> dict[str, Any]:
        async with store.get_pool().acquire() as db:
            async with db.execute("SELECT COUNT(*) FROM tasks") as cur:
                total = int((await cur.fetchone())[0])
            async with db.execute(
                "SELECT COUNT(*) FROM tasks WHERE status='done' AND eval_score>=0.9"
            ) as cur:
                hi = int((await cur.fetchone())[0])
            async with db.execute(
                "SELECT goal_type, COUNT(*) FROM tasks GROUP BY goal_type"
            ) as cur:
                gt_rows = await cur.fetchall()
        by_gt = {r[0] or "unknown": int(r[1]) for r in gt_rows}
        return {
            "total_tasks": total,
            "high_score_tasks": hi,
            "by_goal_type": by_gt,
            "exportable": hi,
        }
