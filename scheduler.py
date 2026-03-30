"""
scheduler.py — Phase 3 Autonomous Scheduler

Runs recurring tasks on a cron-like schedule.
Schedules live in SQLite and the loop checks every 60 seconds.

API (register via POST /schedules):
  {
    "name":    "Daily disk report",
    "command": "Check disk space and save a report to workspace",
    "cron":    "0 9 * * *",   ← 9am UTC daily
    "enabled": true
  }

Cron format: minute hour day_of_month month day_of_week
  Examples:
    "*/5 * * * *"  → every 5 minutes
    "0 9 * * 1"    → every Monday at 9am
    "0 0 1 * *"    → first of every month at midnight
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

import aiosqlite
from fastapi import APIRouter

from config import settings

router = APIRouter(prefix="/schedules", tags=["Scheduler"])
DB = settings.db_path

async def init_scheduler() -> None:
    """Tables created by store.init() — this just validates and prints ready."""
    print("[Scheduler] Ready.")


async def insert_oneshot_schedule(
    name: str,
    command: str,
    run_at_iso: str,
    timezone_name: str = "Asia/Kolkata",
) -> dict:
    """
    One-shot schedule: fires once at run_at_iso (ISO 8601), then disables itself.
    Name must start with [oneshot] for scheduler_loop to recognize it.
    """
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    raw = (run_at_iso or "").strip().replace("Z", "+00:00")
    try:
        nxt = datetime.fromisoformat(raw)
    except ValueError:
        nxt = datetime.now(timezone.utc) + timedelta(hours=1)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    oneshot_name = name if name.startswith("[oneshot]") else f"[oneshot] {name}"
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """INSERT INTO schedules (schedule_id, name, command, cron, enabled, next_run_at, created_at, timezone)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                sid,
                oneshot_name,
                command,
                "0 * * * *",
                1,
                nxt.isoformat(),
                now,
                timezone_name.strip() or "Asia/Kolkata",
            ),
        )
        await db.commit()
    return {"schedule_id": sid, "next_run_at": nxt.isoformat(), "name": oneshot_name}


# ─────────────────────────────────────────────────────────────────────────────
# API routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("")
async def create_schedule(body: dict):
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    tz_name = (body.get("timezone") or "Asia/Kolkata").strip() or "Asia/Kolkata"
    next_run = _next_run(body.get("cron", "0 * * * *"), tz_name)

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            """INSERT INTO schedules (schedule_id, name, command, cron, enabled, next_run_at, created_at, timezone)
               VALUES (?,?,?,?,?,?,?,?)""",
            (sid, body["name"], body["command"],
             body.get("cron", "0 * * * *"),
             1 if body.get("enabled", True) else 0,
             next_run.isoformat(), now, tz_name),
        )
        await db.commit()
    return {"schedule_id": sid, "next_run_at": next_run.isoformat(), "timezone": tz_name}


@router.get("")
async def list_schedules():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM schedules ORDER BY created_at DESC") as cur:
            rows = await cur.fetchall()
    return {"schedules": [dict(r) for r in rows]}


@router.delete("/{sid}")
async def delete_schedule(sid: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM schedules WHERE schedule_id=?", (sid,))
        await db.commit()
    return {"deleted": sid}


@router.patch("/{sid}/toggle")
async def toggle_schedule(sid: str):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT enabled FROM schedules WHERE schedule_id=?", (sid,)) as cur:
            row = await cur.fetchone()
        if not row:
            return {"error": "not found"}
        new = 0 if row[0] else 1
        await db.execute("UPDATE schedules SET enabled=? WHERE schedule_id=?", (new, sid))
        await db.commit()
    return {"schedule_id": sid, "enabled": bool(new)}


@router.patch("/{sid}")
async def update_schedule(sid: str, body: dict):
    fields, vals = [], []
    for k in ("name", "command", "cron", "timezone"):
        if k in body:
            fields.append(f"{k}=?"); vals.append(body[k])
    if not fields:
        return {"error": "Nothing to update"}
    vals.append(sid)
    async with aiosqlite.connect(DB) as db:
        await db.execute(f"UPDATE schedules SET {', '.join(fields)} WHERE schedule_id=?", vals)
        await db.commit()
    return {"updated": sid}


# ─────────────────────────────────────────────────────────────────────────────
# Background loop
# ─────────────────────────────────────────────────────────────────────────────

async def scheduler_loop() -> None:
    """Checks every 60s for due schedules and fires them as tasks."""
    print("[Scheduler] Loop started.")
    while True:
        try:
            await _tick()
        except Exception as e:
            print(f"[Scheduler] Error: {e}")
        await asyncio.sleep(60)


async def _tick() -> None:
    now = datetime.now(timezone.utc)

    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM schedules WHERE enabled=1") as cur:
            schedules = [dict(r) for r in await cur.fetchall()]

    for s in schedules:
        nxt_str = s.get("next_run_at")
        if not nxt_str:
            continue
        nxt = datetime.fromisoformat(nxt_str)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)

        if now >= nxt:
            print(f"[Scheduler] Firing '{s['name']}'")
            asyncio.create_task(_run_schedule(s))

            if str(s.get("name", "")).startswith("[oneshot]"):
                async with aiosqlite.connect(DB) as db:
                    await db.execute(
                        """UPDATE schedules SET enabled=0, last_run_at=?, run_count=run_count+1
                           WHERE schedule_id=?""",
                        (now.isoformat(), s["schedule_id"]),
                    )
                    await db.commit()
                continue

            tz_s = (s.get("timezone") or "UTC").strip() or "UTC"
            next_next = _next_run(s["cron"], tz_s)
            async with aiosqlite.connect(DB) as db:
                await db.execute(
                    """UPDATE schedules SET last_run_at=?, next_run_at=?, run_count=run_count+1
                       WHERE schedule_id=?""",
                    (now.isoformat(), next_next.isoformat(), s["schedule_id"]),
                )
                await db.commit()


async def _run_schedule(s: dict) -> None:
    task_id = str(uuid.uuid4())
    import memory.store as store
    await store.create_task(task_id, s["command"], source=f"scheduler:{s['name']}")
    import orchestrator
    await orchestrator.run(
        task_id=task_id,
        command=s["command"],
        context={"scheduled": True, "schedule_name": s["name"]},
        dry_run=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cron parser
# ─────────────────────────────────────────────────────────────────────────────

def _next_run(cron: str, tz_name: str = "UTC") -> datetime:
    """Compute next fire time in UTC. Cron fields match wall time in *tz_name* (or UTC)."""
    parts = cron.strip().split()
    if len(parts) != 5:
        parts = ["0", "*", "*", "*", "*"]

    minute, hour, dom, month, dow = parts

    def matches(val: str, cur: int) -> bool:
        if val == "*":
            return True
        if val.startswith("*/"):
            try:
                step = int(val[2:])
                return cur % step == 0
            except ValueError:
                return False
        try:
            return cur == int(val)
        except ValueError:
            return False

    if not tz_name or tz_name.upper() == "UTC":
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        candidate = now + timedelta(minutes=1)
        for _ in range(525_600):
            if (matches(month, candidate.month) and
                    matches(dom, candidate.day) and
                    matches(dow, candidate.weekday()) and
                    matches(hour, candidate.hour) and
                    matches(minute, candidate.minute)):
                return candidate
            candidate += timedelta(minutes=1)
        return now + timedelta(hours=1)

    import pytz

    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.UTC
    utc = pytz.UTC
    now_utc = datetime.now(utc)
    local_now = now_utc.astimezone(tz).replace(second=0, microsecond=0)
    candidate = local_now + timedelta(minutes=1)
    for _ in range(525_600):
        if (matches(month, candidate.month) and
                matches(dom, candidate.day) and
                matches(dow, candidate.weekday()) and
                matches(hour, candidate.hour) and
                matches(minute, candidate.minute)):
            return candidate.astimezone(utc)
        candidate += timedelta(minutes=1)
    return (local_now + timedelta(hours=1)).astimezone(utc)
