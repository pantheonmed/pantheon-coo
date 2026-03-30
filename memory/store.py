"""
memory/store.py
───────────────
SQLite-backed memory store for the COO OS.

Tables:
  tasks     — task lifecycle (status, plan, results, score)
  logs      — per-task execution logs
  learnings — distilled knowledge from past tasks (the COO's memory)

Live SSE activity events are buffered in-memory per task_id (asyncio.Queue).
"""
import asyncio
import aiosqlite
import json
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

STREAM_EVENT_TYPES = frozenset({
    "agent_start",
    "agent_done",
    "step_start",
    "step_done",
    "loop_start",
    "loop_done",
})

from config import settings
from models import TaskStatus
from memory.db_pool import get_pool

DB = settings.db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    command         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    loop_iterations INTEGER DEFAULT 0,
    eval_score      REAL,
    goal            TEXT DEFAULT '',
    goal_type       TEXT DEFAULT '',
    plan_json       TEXT DEFAULT '{}',
    results_json    TEXT DEFAULT '[]',
    summary         TEXT DEFAULT '',
    error           TEXT,
    source          TEXT DEFAULT 'api',
    user_id         TEXT,
    telegram_chat_id TEXT,
    suggestions_json TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    data_json   TEXT DEFAULT '{}',
    logged_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    goal_type   TEXT NOT NULL,
    learning    TEXT NOT NULL,
    score       REAL DEFAULT 0.0,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status     ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_user       ON tasks(user_id);

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    plan          TEXT NOT NULL DEFAULT 'free',
    api_key       TEXT UNIQUE,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_login    TEXT,
    industry      TEXT DEFAULT 'other'
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    jwt_token    TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email   ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_logs_task        ON logs(task_id);
CREATE INDEX IF NOT EXISTS idx_learnings_type   ON learnings(goal_type);

CREATE TABLE IF NOT EXISTS custom_tools (
    tool_id      TEXT PRIMARY KEY,
    tool_name    TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL,
    module_path  TEXT NOT NULL,
    trigger_pattern TEXT NOT NULL,
    created_from TEXT,
    usage_count  INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_patterns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL,
    goal_type    TEXT,
    step_sequence TEXT NOT NULL,
    recorded_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_custom_tools_name ON custom_tools(tool_name);
CREATE INDEX IF NOT EXISTS idx_patterns_type ON task_patterns(goal_type);

CREATE TABLE IF NOT EXISTS briefings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at         TEXT NOT NULL,
    period_hours         INTEGER DEFAULT 24,
    headline             TEXT DEFAULT '',
    health               TEXT DEFAULT 'unknown',
    sections_json        TEXT DEFAULT '[]',
    recommendations_json TEXT DEFAULT '[]',
    full_text            TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    command      TEXT NOT NULL,
    cron         TEXT NOT NULL DEFAULT '0 * * * *',
    enabled      INTEGER DEFAULT 1,
    last_run_at  TEXT,
    next_run_at  TEXT,
    run_count    INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_prompts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name   TEXT NOT NULL,
    goal_type    TEXT NOT NULL,
    prompt_text  TEXT NOT NULL,
    version      INTEGER DEFAULT 1,
    avg_score    REAL DEFAULT 0.0,
    task_count   INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT NOT NULL,
    notes        TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_prompts_agent ON agent_prompts(agent_name, goal_type, is_active);

CREATE TABLE IF NOT EXISTS orders (
    order_id              TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL,
    razorpay_order_id     TEXT,
    razorpay_payment_id   TEXT,
    plan                  TEXT NOT NULL,
    amount                INTEGER NOT NULL,
    currency              TEXT DEFAULT 'INR',
    status                TEXT DEFAULT 'pending',
    created_at            TEXT NOT NULL,
    completed_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_rzp ON orders(razorpay_order_id);

CREATE TABLE IF NOT EXISTS analytics_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,
    user_id      TEXT DEFAULT '',
    properties   TEXT DEFAULT '{}',
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    webhook_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    url           TEXT NOT NULL,
    events        TEXT NOT NULL DEFAULT '["task.completed","task.failed"]',
    secret        TEXT NOT NULL,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_fired    TEXT,
    failure_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload_json TEXT,
    status_code  INTEGER,
    success      INTEGER DEFAULT 0,
    fired_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS affiliates (
    affiliate_id   TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    referral_code  TEXT NOT NULL UNIQUE,
    commission_pct REAL DEFAULT 20.0,
    total_referred INTEGER DEFAULT 0,
    total_earned   REAL DEFAULT 0.0,
    link_clicks    INTEGER DEFAULT 0,
    is_active      INTEGER DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS referrals (
    referral_id     TEXT PRIMARY KEY,
    affiliate_id    TEXT NOT NULL,
    referred_email    TEXT NOT NULL,
    referred_user_id  TEXT,
    status            TEXT DEFAULT 'pending',
    commission_inr    REAL DEFAULT 0.0,
    converted_at      TEXT,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_affiliates_code ON affiliates(referral_code);
CREATE INDEX IF NOT EXISTS idx_referrals_affiliate ON referrals(affiliate_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referred_user ON referrals(referred_user_id);

CREATE TABLE IF NOT EXISTS affiliate_payout_requests (
    request_id    TEXT PRIMARY KEY,
    affiliate_id  TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    upi_id        TEXT NOT NULL,
    amount        REAL NOT NULL,
    status        TEXT DEFAULT 'pending',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_memories (
    memory_id     TEXT PRIMARY KEY,
    task_id       TEXT,
    owner_user_id TEXT,
    content       TEXT NOT NULL,
    memory_type   TEXT NOT NULL,
    tags_json     TEXT DEFAULT '[]',
    importance    REAL DEFAULT 0.5,
    access_count  INTEGER DEFAULT 0,
    last_accessed TEXT,
    deleted       INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_smem_type ON semantic_memories(memory_type, importance DESC);

CREATE TABLE IF NOT EXISTS task_shares (
    token       TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    user_id     TEXT,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_shares_task ON task_shares(task_id);
CREATE INDEX IF NOT EXISTS idx_task_shares_expires ON task_shares(expires_at);
"""


async def _ensure_task_user_id_column() -> None:
    """Upgrade legacy DBs missing tasks.user_id."""
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(tasks)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "user_id" not in cols:
            await db.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT")
            await db.commit()


async def _ensure_user_industry_column() -> None:
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(users)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "industry" not in cols:
            await db.execute("ALTER TABLE users ADD COLUMN industry TEXT DEFAULT 'other'")
            await db.commit()


async def _ensure_suggestions_json_column() -> None:
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(tasks)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "suggestions_json" not in cols:
            await db.execute(
                "ALTER TABLE tasks ADD COLUMN suggestions_json TEXT DEFAULT '[]'"
            )
            await db.commit()


async def _ensure_telegram_chat_id_column() -> None:
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(tasks)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "telegram_chat_id" not in cols:
            await db.execute("ALTER TABLE tasks ADD COLUMN telegram_chat_id TEXT")
            await db.commit()
        async with db.execute("PRAGMA table_info(tasks)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "telegram_chat_id" in cols:
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_telegram ON tasks(telegram_chat_id)"
            )
            await db.commit()


async def _ensure_user_global_profile_columns() -> None:
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(users)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        alters = []
        if "language" not in cols:
            alters.append("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
        if "currency" not in cols:
            alters.append("ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'INR'")
        if "country_code" not in cols:
            alters.append("ALTER TABLE users ADD COLUMN country_code TEXT DEFAULT 'IN'")
        if "timezone" not in cols:
            alters.append("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Asia/Kolkata'")
        if "locale" not in cols:
            alters.append("ALTER TABLE users ADD COLUMN locale TEXT DEFAULT 'en-IN'")
        for sql in alters:
            await db.execute(sql)
        if alters:
            await db.commit()


async def _ensure_orders_payment_columns() -> None:
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(orders)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        alters = []
        if "stripe_payment_intent_id" not in cols:
            alters.append("ALTER TABLE orders ADD COLUMN stripe_payment_intent_id TEXT")
        if "payment_gateway" not in cols:
            alters.append("ALTER TABLE orders ADD COLUMN payment_gateway TEXT DEFAULT 'razorpay'")
        for sql in alters:
            await db.execute(sql)
        if alters:
            await db.commit()


async def _ensure_schedules_timezone_column() -> None:
    async with get_pool().acquire() as db:
        async with db.execute("PRAGMA table_info(schedules)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "timezone" not in cols:
            await db.execute(
                "ALTER TABLE schedules ADD COLUMN timezone TEXT DEFAULT 'Asia/Kolkata'"
            )
            await db.commit()


async def _ensure_perf_indexes() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0017_perf_indexes.sql"
    if sql_path.is_file():
        script = sql_path.read_text(encoding="utf-8")
    else:
        script = """
        CREATE INDEX IF NOT EXISTS idx_tasks_user_created ON tasks(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_logs_task_level ON logs(task_id, level);
        CREATE INDEX IF NOT EXISTS idx_analytics_type_user ON analytics_events(event_type, user_id, created_at);
        """
    async with get_pool().acquire() as db:
        await db.executescript(script)
        await db.commit()


async def init() -> None:
    async with get_pool().acquire() as db:
        await db.executescript(SCHEMA)
        await db.commit()
    await _ensure_task_user_id_column()
    await _ensure_user_industry_column()
    await _ensure_user_global_profile_columns()
    await _ensure_telegram_chat_id_column()
    await _ensure_suggestions_json_column()
    await _ensure_orders_payment_columns()
    await _ensure_schedules_timezone_column()
    await _ensure_perf_indexes()
    await _ensure_launch_migrations()
    print(f"[Memory] DB ready → {DB}")


# ─────────────────────────────────────────────────────────────────────────────
# Task operations
# ─────────────────────────────────────────────────────────────────────────────

async def create_task(
    task_id: str,
    command: str,
    source: str = "api",
    user_id: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT OR IGNORE INTO tasks (task_id, command, status, source, user_id, telegram_chat_id, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                task_id,
                command,
                "queued",
                source,
                user_id,
                telegram_chat_id,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()


async def list_tasks_by_telegram_chat(chat_id: str, limit: int = 3) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM tasks WHERE telegram_chat_id=? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def track_event(
    event_type: str,
    user_id: str = "",
    properties: Optional[dict] = None,
) -> None:
    props = json.dumps(properties or {})
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO analytics_events (event_type, user_id, properties, created_at)
               VALUES (?,?,?,?)""",
            (event_type, user_id or "", props, now),
        )
        await db.commit()


async def save_suggestions(task_id: str, suggestions: list[str]) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE tasks SET suggestions_json=? WHERE task_id=?",
            (json.dumps(suggestions), task_id),
        )
        await db.commit()


async def get_suggestions(task_id: str) -> list[str]:
    row = await get_task(task_id)
    if not row:
        return []
    raw = row.get("suggestions_json") or "[]"
    try:
        data = json.loads(raw)
        return list(data) if isinstance(data, list) else []
    except Exception:
        return []


async def update_status(
    task_id: str,
    status: TaskStatus,
    *,
    summary: str = "",
    eval_score: Optional[float] = None,
    iterations: int = 0,
    results_json: str = "[]",
    error: Optional[str] = None,
) -> None:
    completed_at = (
        datetime.utcnow().isoformat()
        if status in (TaskStatus.DONE, TaskStatus.FAILED)
        else None
    )
    async with get_pool().acquire() as db:
        await db.execute(
            """UPDATE tasks
               SET status=?, summary=?, eval_score=?, loop_iterations=?,
                   results_json=?, error=?, completed_at=?
               WHERE task_id=?""",
            (status.value, summary, eval_score, iterations,
             results_json, error, completed_at, task_id),
        )
        await db.commit()


async def update_plan(task_id: str, plan_json: str, goal_type: str, goal: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE tasks SET plan_json=?, goal_type=?, goal=? WHERE task_id=?",
            (plan_json, goal_type, goal, task_id),
        )
        await db.commit()


async def get_task(task_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_tasks(
    limit: int = 20,
    status: Optional[str] = None,
    *,
    user_id: Optional[str] = None,
    is_admin: bool = False,
) -> list[dict]:
    async with get_pool().acquire() as db:
        if is_admin:
            if status:
                q, p = "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
            else:
                q, p = "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        elif user_id is not None:
            if status:
                q, p = (
                    "SELECT * FROM tasks WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
                    (user_id, status, limit),
                )
            else:
                q, p = (
                    "SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                )
        else:
            if status:
                q, p = "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
            else:
                q, p = "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        async with db.execute(q, p) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def insert_user_session(
    session_id: str,
    user_id: str,
    jwt_token: str,
    expires_at: str,
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT OR REPLACE INTO user_sessions (session_id, user_id, jwt_token, expires_at, created_at)
               VALUES (?,?,?,?,?)""",
            (session_id, user_id, jwt_token, expires_at, now),
        )
        await db.commit()


async def delete_user_session(session_id: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute("DELETE FROM user_sessions WHERE session_id=?", (session_id,))
        await db.commit()


async def get_user_by_email(email: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM users WHERE lower(email)=lower(?)", (email.strip(),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_api_key(api_key: str) -> Optional[dict]:
    if not api_key:
        return None
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM users WHERE api_key=?", (api_key,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_id(user_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def insert_user(
    user_id: str,
    email: str,
    name: str,
    password_hash: str,
    role: str = "user",
    plan: str = "free",
    api_key: str = "",
    industry: str = "other",
    *,
    language: str = "en",
    currency: str = "INR",
    country_code: str = "IN",
    timezone: str = "Asia/Kolkata",
    locale: str = "en-IN",
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO users (user_id, email, name, password_hash, role, plan, api_key, is_active, created_at, industry,
               language, currency, country_code, timezone, locale)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                email.strip().lower(),
                name,
                password_hash,
                role,
                plan,
                api_key or None,
                1,
                now,
                industry or "other",
                language or "en",
                currency or "INR",
                (country_code or "IN").upper(),
                timezone or "Asia/Kolkata",
                locale or "en-IN",
            ),
        )
        await db.commit()


async def update_user_language(user_id: str, language: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute("UPDATE users SET language=? WHERE user_id=?", (language, user_id))
        await db.commit()


async def update_user_timezone(user_id: str, timezone: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute("UPDATE users SET timezone=? WHERE user_id=?", (timezone, user_id))
        await db.commit()


async def update_user_api_key(user_id: str, api_key: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute("UPDATE users SET api_key=? WHERE user_id=?", (api_key, user_id))
        await db.commit()


async def update_last_login(user_id: str) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute("UPDATE users SET last_login=? WHERE user_id=?", (now, user_id))
        await db.commit()


async def count_users() -> int:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            return int((await cur.fetchone())[0])


async def list_all_users(limit: int = 500) -> list[dict[str, Any]]:
    """All users for password-protected /admin UI (email, plan, created_at)."""
    async with get_pool().acquire() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, email, plan, created_at FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def count_tasks_for_user(user_id: str) -> int:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id=?", (user_id,)
        ) as cur:
            return int((await cur.fetchone())[0])


async def count_tasks_for_user_this_month(user_id: str) -> int:
    """Count tasks created since the first day of the current UTC month."""
    from datetime import datetime

    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id=? AND created_at >= ?",
            (user_id, start),
        ) as cur:
            return int((await cur.fetchone())[0])


async def update_user_plan(user_id: str, plan: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute("UPDATE users SET plan=? WHERE user_id=?", (plan, user_id))
        await db.commit()


async def insert_order(
    order_id: str,
    user_id: str,
    plan: str,
    amount: int,
    currency: str = "INR",
    status: str = "pending",
    *,
    razorpay_order_id: Optional[str] = None,
    stripe_payment_intent_id: Optional[str] = None,
    payment_gateway: str = "razorpay",
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO orders (order_id, user_id, razorpay_order_id, plan, amount, currency, status, created_at,
               stripe_payment_intent_id, payment_gateway)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                order_id,
                user_id,
                razorpay_order_id,
                plan,
                amount,
                currency,
                status,
                now,
                stripe_payment_intent_id,
                payment_gateway,
            ),
        )
        await db.commit()


async def get_order_by_razorpay_order_id(razorpay_order_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM orders WHERE razorpay_order_id=?", (razorpay_order_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_order_by_stripe_payment_intent_id(stripe_pi: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM orders WHERE stripe_payment_intent_id=?", (stripe_pi,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_order_by_internal_id(order_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_order_paid(
    order_id: str,
    provider_payment_id: str,
    *,
    gateway: str = "razorpay",
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        if gateway == "stripe":
            await db.execute(
                """UPDATE orders SET stripe_payment_intent_id=?, status='paid', completed_at=?,
                   payment_gateway='stripe' WHERE order_id=?""",
                (provider_payment_id, now, order_id),
            )
        else:
            await db.execute(
                """UPDATE orders SET razorpay_payment_id=?, status='paid', completed_at=?,
                   payment_gateway='razorpay' WHERE order_id=?""",
                (provider_payment_id, now, order_id),
            )
        await db.commit()


async def mark_order_failed(order_id: str) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE orders SET status='failed', completed_at=? WHERE order_id=?",
            (now, order_id),
        )
        await db.commit()


async def list_orders_for_user(user_id: str, limit: int = 50) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


STUCK_TASK_STATUSES = ("reasoning", "planning", "executing", "evaluating")


async def recover_stuck_tasks() -> list[dict]:
    """
    Mark in-flight tasks as failed after a server restart.
    Returns rows as they were *before* update: task_id, command, status.
    """
    out: list[dict] = []
    now = datetime.utcnow().isoformat()
    placeholders = ",".join("?" * len(STUCK_TASK_STATUSES))
    async with get_pool().acquire() as db:
        async with db.execute(
            f"SELECT task_id, command, status FROM tasks WHERE status IN ({placeholders})",
            STUCK_TASK_STATUSES,
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            tid = r["task_id"]
            err = f"Server restarted mid-execution. Use POST /tasks/{tid}/retry to resume."
            summ = f"Task was interrupted. Use POST /tasks/{tid}/retry to resume."
            await db.execute(
                """UPDATE tasks SET status='failed', error=?, summary=?, completed_at=?
                   WHERE task_id=?""",
                (err, summ, now, tid),
            )
            out.append({"task_id": tid, "command": r["command"], "status": r["status"]})
        await db.commit()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

async def log(task_id: str, message: str, level: str = "info", data: dict = {}) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "INSERT INTO logs (task_id, level, message, data_json, logged_at) VALUES (?,?,?,?,?)",
            (task_id, level, message, json.dumps(data, default=str),
             datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_logs(task_id: str) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM logs WHERE task_id=? ORDER BY logged_at", (task_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# Live stream events (SSE — orchestrator + executor push, /tasks/{id}/stream pulls)
# ─────────────────────────────────────────────────────────────────────────────

# Per-task list of subscriber queues (multi-viewer SSE). Legacy get_stream_queue uses [0] as primary.
_stream_queues: dict[str, list[asyncio.Queue]] = {}


def get_stream_queue(task_id: str) -> asyncio.Queue:
    """Primary queue for tests / single consumer; same task_id reuses lst[0]."""
    lst = _stream_queues.setdefault(task_id, [])
    if not lst:
        lst.append(asyncio.Queue(maxsize=0))
    return lst[0]


def subscribe_task_stream(task_id: str) -> asyncio.Queue:
    """Register a new SSE subscriber; events are broadcast to all subscribers."""
    q = asyncio.Queue(maxsize=0)
    lst = _stream_queues.setdefault(task_id, [])
    lst.append(q)
    return q


def unsubscribe_task_stream(task_id: str, q: asyncio.Queue) -> None:
    lst = _stream_queues.get(task_id)
    if not lst:
        return
    try:
        lst.remove(q)
    except ValueError:
        pass
    if not lst:
        _stream_queues.pop(task_id, None)


def stream_subscriber_count(task_id: str) -> int:
    return len(_stream_queues.get(task_id, []))


async def push_stream_event(task_id: str, event_type: str, data: dict[str, Any]) -> None:
    """
    Push a structured event for GET /tasks/{id}/stream (type: activity).

    event_type: agent_start | agent_done | step_start | step_done | loop_start | loop_done
    """
    if event_type not in STREAM_EVENT_TYPES:
        raise ValueError(f"Invalid stream event_type {event_type!r}; expected one of {STREAM_EVENT_TYPES}")
    payload = {
        "event_type": event_type,
        "data": dict(data) if data is not None else {},
        "ts": datetime.utcnow().isoformat(),
    }
    lst = _stream_queues.setdefault(task_id, [])
    if not lst:
        lst.append(asyncio.Queue(maxsize=0))
    for q in list(lst):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def insert_task_share(token: str, task_id: str, user_id: Optional[str], expires_at_iso: str) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            "INSERT INTO task_shares (token, task_id, user_id, expires_at, created_at) VALUES (?,?,?,?,?)",
            (token, task_id, user_id, expires_at_iso, now),
        )
        await db.commit()


async def get_task_share_row(token: str) -> Optional[dict[str, Any]]:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM task_shares WHERE token=?", (token,)) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
    if d["expires_at"] < datetime.utcnow().isoformat():
        return None
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Learnings (COO institutional memory)
# ─────────────────────────────────────────────────────────────────────────────

async def save_learning(task_id: str, goal_type: str, learning: str, score: float) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "INSERT INTO learnings (task_id, goal_type, learning, score, created_at) VALUES (?,?,?,?,?)",
            (task_id, goal_type, learning, score, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_learnings(goal_type: str = "general", limit: int = 5) -> list[str]:
    """Return the most recent high-quality learnings for a goal type."""
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT learning FROM learnings
               WHERE goal_type=? OR goal_type='general'
               ORDER BY score DESC, created_at DESC
               LIMIT ?""",
            (goal_type, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [r["learning"] for r in rows]


async def get_stats() -> dict:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status") as cur:
            by_status = {r[0]: r[1] for r in await cur.fetchall()}
        async with db.execute("SELECT COUNT(*) FROM learnings") as cur:
            total_learnings = (await cur.fetchone())[0]
        async with db.execute("SELECT AVG(eval_score) FROM tasks WHERE eval_score IS NOT NULL") as cur:
            avg_score = (await cur.fetchone())[0] or 0.0

    return {
        "tasks": by_status,
        "total": sum(by_status.values()),
        "learnings": total_learnings,
        "avg_eval_score": round(avg_score, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Custom tools (Phase 3 — Tool Builder)
# ─────────────────────────────────────────────────────────────────────────────

async def save_custom_tool(
    tool_id: str, tool_name: str, description: str,
    module_path: str, trigger_pattern: str, created_from: str
) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT OR REPLACE INTO custom_tools
               (tool_id, tool_name, description, module_path, trigger_pattern, created_from, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (tool_id, tool_name, description, module_path,
             trigger_pattern, created_from, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_custom_tools() -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM custom_tools ORDER BY usage_count DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def increment_tool_usage(tool_name: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE custom_tools SET usage_count = usage_count + 1 WHERE tool_name=?",
            (tool_name,),
        )
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Pattern recording (Phase 3 — Pattern Detector)
# ─────────────────────────────────────────────────────────────────────────────

async def record_pattern(task_id: str, goal_type: str, step_sequence: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "INSERT INTO task_patterns (task_id, goal_type, step_sequence, recorded_at) VALUES (?,?,?,?)",
            (task_id, goal_type, step_sequence, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def get_repeated_patterns(min_occurrences: int = 3) -> list[dict]:
    """Return step sequences that have been used >= min_occurrences times."""
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT step_sequence, goal_type, COUNT(*) as count
               FROM task_patterns
               GROUP BY step_sequence
               HAVING count >= ?
               ORDER BY count DESC
               LIMIT 10""",
            (min_occurrences,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# Projects (Phase 5 — long-running multi-task goals)
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    goal         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    task_ids     TEXT DEFAULT '[]',
    progress     REAL DEFAULT 0.0,
    created_at   TEXT NOT NULL,
    completed_at TEXT
);
"""


async def init_projects() -> None:
    async with get_pool().acquire() as db:
        await db.executescript(PROJECT_SCHEMA)
        await db.commit()


async def create_project(project_id: str, name: str, goal: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "INSERT OR IGNORE INTO projects (project_id, name, goal, created_at) VALUES (?,?,?,?)",
            (project_id, name, goal, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def add_task_to_project(project_id: str, task_id: str) -> None:
    import json as _json
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT task_ids FROM projects WHERE project_id=?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        ids = _json.loads(row[0] or "[]")
        ids.append(task_id)
        await db.execute(
            "UPDATE projects SET task_ids=? WHERE project_id=?",
            (_json.dumps(ids), project_id),
        )
        await db.commit()


async def update_project_progress(project_id: str) -> float:
    import json as _json
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT task_ids FROM projects WHERE project_id=?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return 0.0
        ids = _json.loads(row[0] or "[]")
        if not ids:
            return 0.0
        placeholders = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT COUNT(*) FROM tasks WHERE task_id IN ({placeholders}) AND status='done'",
            ids,
        ) as cur:
            done = (await cur.fetchone())[0]
        progress = done / len(ids)
        status = "completed" if progress >= 1.0 else "active"
        completed_at = datetime.utcnow().isoformat() if progress >= 1.0 else None
        await db.execute(
            "UPDATE projects SET progress=?, status=?, completed_at=? WHERE project_id=?",
            (progress, status, completed_at, project_id),
        )
        await db.commit()
        return progress


async def get_project(project_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM projects WHERE project_id=?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_projects(status: Optional[str] = None) -> list[dict]:
    async with get_pool().acquire() as db:
        if status:
            q, p = "SELECT * FROM projects WHERE status=? ORDER BY created_at DESC", (status,)
        else:
            q, p = "SELECT * FROM projects ORDER BY created_at DESC LIMIT 50", ()
        async with db.execute(q, p) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# Webhooks
# ─────────────────────────────────────────────────────────────────────────────


async def insert_webhook_subscription(
    webhook_id: str,
    user_id: str,
    url: str,
    events_json: str,
    secret: str,
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO webhook_subscriptions
               (webhook_id, user_id, url, events, secret, is_active, created_at, failure_count)
               VALUES (?,?,?,?,?,?,?,0)""",
            (webhook_id, user_id, url, events_json, secret, 1, now),
        )
        await db.commit()


async def list_webhooks_for_user(user_id: str) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT webhook_id, user_id, url, events, is_active, created_at, last_fired, failure_count, "
            "SUBSTR(secret, LENGTH(secret)-3, 4) AS secret_tail FROM webhook_subscriptions WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def list_active_webhooks_for_user(user_id: str, event_type: str) -> list[dict]:
    rows = await list_webhooks_for_user_full(user_id)
    out = []
    for r in rows:
        if not r.get("is_active"):
            continue
        try:
            evs = json.loads(r.get("events") or "[]")
        except Exception:
            evs = []
        if event_type in evs:
            out.append(r)
    return out


async def list_webhooks_for_user_full(user_id: str) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM webhook_subscriptions WHERE user_id=?", (user_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def deactivate_webhook(webhook_id: str, user_id: str) -> bool:
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE webhook_subscriptions SET is_active=0 WHERE webhook_id=? AND user_id=?",
            (webhook_id, user_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT is_active FROM webhook_subscriptions WHERE webhook_id=? AND user_id=?",
            (webhook_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return row is not None and int(row[0]) == 0


async def append_webhook_log(
    webhook_id: str,
    event_type: str,
    payload_json: str,
    status_code: Optional[int],
    success: int,
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO webhook_logs (webhook_id, event_type, payload_json, status_code, success, fired_at)
               VALUES (?,?,?,?,?,?)""",
            (webhook_id, event_type, payload_json[:8000], status_code, success, now),
        )
        await db.commit()


async def increment_webhook_failure(webhook_id: str) -> None:
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE webhook_subscriptions SET failure_count = failure_count + 1 WHERE webhook_id=?",
            (webhook_id,),
        )
        async with db.execute(
            "SELECT failure_count FROM webhook_subscriptions WHERE webhook_id=?", (webhook_id,)
        ) as cur:
            row = await cur.fetchone()
            n = int(row[0]) if row else 0
        if n >= 5:
            await db.execute(
                "UPDATE webhook_subscriptions SET is_active=0 WHERE webhook_id=?",
                (webhook_id,),
            )
        await db.commit()


async def get_webhook_logs(webhook_id: str, user_id: str, limit: int = 20) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT 1 FROM webhook_subscriptions WHERE webhook_id=? AND user_id=?",
            (webhook_id, user_id),
        ) as cur:
            if not await cur.fetchone():
                return []
        async with db.execute(
            """SELECT id, webhook_id, event_type, status_code, success, fired_at
               FROM webhook_logs WHERE webhook_id=? ORDER BY id DESC LIMIT ?""",
            (webhook_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


def _gen_referral_code() -> str:
    return secrets.token_hex(4)[:8].upper()


async def get_affiliate_by_user(user_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM affiliates WHERE user_id=? AND is_active=1", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_affiliate_by_code(code: str) -> Optional[dict]:
    c = (code or "").strip().upper()
    if not c:
        return None
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM affiliates WHERE UPPER(referral_code)=? AND is_active=1", (c,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_affiliate_for_user(user_id: str, commission_pct: Optional[float] = None) -> dict:
    existing = await get_affiliate_by_user(user_id)
    if existing:
        return existing
    pct = float(commission_pct if commission_pct is not None else settings.default_affiliate_commission)
    aid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    for _ in range(20):
        rc = _gen_referral_code()
        try:
            async with get_pool().acquire() as db:
                await db.execute(
                    """INSERT INTO affiliates
                    (affiliate_id, user_id, referral_code, commission_pct, total_referred,
                     total_earned, link_clicks, is_active, created_at)
                    VALUES (?,?,?,?,0,0,0,1,?)""",
                    (aid, user_id, rc, pct, now),
                )
                await db.commit()
            row = await get_affiliate_by_user(user_id)
            return row or {"affiliate_id": aid, "referral_code": rc, "commission_pct": pct}
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Could not allocate unique referral code")


async def record_affiliate_link_click(code: str) -> None:
    aff = await get_affiliate_by_code(code)
    if not aff:
        return
    async with get_pool().acquire() as db:
        await db.execute(
            "UPDATE affiliates SET link_clicks = link_clicks + 1 WHERE affiliate_id=?",
            (aff["affiliate_id"],),
        )
        await db.commit()


async def attach_referral_from_code(ref_code: Optional[str], new_user_id: str, email: str) -> None:
    if not ref_code or not str(ref_code).strip():
        return
    aff = await get_affiliate_by_code(str(ref_code))
    if not aff or aff.get("user_id") == new_user_id:
        return
    rid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO referrals
            (referral_id, affiliate_id, referred_email, referred_user_id, status, commission_inr, created_at)
            VALUES (?,?,?,?, 'registered', 0.0, ?)""",
            (rid, aff["affiliate_id"], email.lower(), new_user_id, now),
        )
        await db.execute(
            "UPDATE affiliates SET total_referred = total_referred + 1 WHERE affiliate_id=?",
            (aff["affiliate_id"],),
        )
        await db.commit()


async def count_converted_referrals(affiliate_id: str) -> int:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM referrals WHERE affiliate_id=? AND status='converted'",
            (affiliate_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


async def sum_pending_payout_amount(affiliate_id: str) -> float:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM affiliate_payout_requests "
            "WHERE affiliate_id=? AND status='pending'",
            (affiliate_id,),
        ) as cur:
            row = await cur.fetchone()
            return float(row[0] or 0)


async def list_recent_referrals_for_affiliate(affiliate_id: str, limit: int = 20) -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT referred_email, status, created_at FROM referrals
               WHERE affiliate_id=? ORDER BY created_at DESC LIMIT ?""",
            (affiliate_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def apply_affiliate_commission_on_payment(user_id: str, amount_paise: int) -> None:
    amt_inr = float(amount_paise) / 100.0
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT r.referral_id, r.affiliate_id, a.commission_pct
               FROM referrals r
               JOIN affiliates a ON a.affiliate_id = r.affiliate_id
               WHERE r.referred_user_id=? AND r.status IN ('registered','pending')
               ORDER BY r.created_at ASC LIMIT 1""",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        referral_id, affiliate_id, pct = row[0], row[1], float(row[2] or 20.0)
        commission = round(amt_inr * (pct / 100.0), 2)
        now = datetime.utcnow().isoformat()
        await db.execute(
            "UPDATE referrals SET status='converted', commission_inr=?, converted_at=? WHERE referral_id=?",
            (commission, now, referral_id),
        )
        await db.execute(
            "UPDATE affiliates SET total_earned = total_earned + ? WHERE affiliate_id=?",
            (commission, affiliate_id),
        )
        await db.commit()


async def insert_affiliate_payout_request(
    affiliate_id: str, user_id: str, upi_id: str, amount: float
) -> dict:
    rid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO affiliate_payout_requests
            (request_id, affiliate_id, user_id, upi_id, amount, status, created_at)
            VALUES (?,?,?,?,?,'pending',?)""",
            (rid, affiliate_id, user_id, upi_id.strip(), float(amount), now),
        )
        await db.commit()
    return {"request_id": rid, "status": "pending"}


async def list_affiliates_admin() -> list[dict]:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM affiliates ORDER BY created_at DESC") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    out = []
    for a in rows:
        aid = a["affiliate_id"]
        a = dict(a)
        a["converted"] = await count_converted_referrals(aid)
        out.append(a)
    return out


async def count_learnings_rows() -> int:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT COUNT(*) FROM learnings") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


async def count_semantic_memories_rows(include_deleted: bool = False) -> int:
    async with get_pool().acquire() as db:
        if include_deleted:
            q = "SELECT COUNT(*) FROM semantic_memories"
            async with db.execute(q) as cur:
                row = await cur.fetchone()
        else:
            q = "SELECT COUNT(*) FROM semantic_memories WHERE deleted=0"
            async with db.execute(q) as cur:
                row = await cur.fetchone()
        return int(row[0]) if row else 0


async def semantic_memory_aggregate_stats() -> dict[str, Any]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT AVG(importance) FROM semantic_memories WHERE deleted=0"
        ) as cur:
            row = await cur.fetchone()
            avg_imp = float(row[0] or 0.0)
        async with db.execute(
            """SELECT memory_type, COUNT(*) as c FROM semantic_memories WHERE deleted=0
               GROUP BY memory_type ORDER BY c DESC LIMIT 8"""
        ) as cur:
            types = [{"memory_type": r[0], "count": int(r[1])} for r in await cur.fetchall()]
    return {
        "total_learnings": await count_learnings_rows(),
        "total_semantic_memories": await count_semantic_memories_rows(),
        "top_memory_types": types,
        "avg_importance": round(avg_imp, 4),
    }


async def get_semantic_memory(memory_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM semantic_memories WHERE memory_id=?", (memory_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def soft_delete_semantic_memory(memory_id: str) -> bool:
    async with get_pool().acquire() as db:
        cur = await db.execute(
            "UPDATE semantic_memories SET deleted=1 WHERE memory_id=? AND deleted=0",
            (memory_id,),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Queue + admin metrics (Tasks 79–81)
# ─────────────────────────────────────────────────────────────────────────────


async def get_queue_depth() -> int:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


async def get_admin_dashboard_stats() -> dict[str, Any]:
    """Aggregate metrics for founder admin dashboard (single round-trip style)."""
    from config import PLAN_PRICING

    now = datetime.utcnow().isoformat()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    week_ago = datetime.utcfromtimestamp(
        datetime.utcnow().timestamp() - 7 * 86400
    ).isoformat()

    async with get_pool().acquire() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = int((await cur.fetchone())[0])
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE substr(created_at,1,10)=?", (today,)
        ) as cur:
            new_today = int((await cur.fetchone())[0])
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (week_ago,)
        ) as cur:
            active_week = int((await cur.fetchone())[0])
        async with db.execute(
            "SELECT plan, COUNT(*) as c FROM users GROUP BY plan"
        ) as cur:
            plan_rows = await cur.fetchall()
        plan_breakdown = {r[0]: int(r[1]) for r in plan_rows}
        async with db.execute(
            "SELECT COALESCE(country_code,'') as cc, COUNT(*) as c FROM users GROUP BY cc ORDER BY c DESC LIMIT 12"
        ) as cur:
            by_country = [{"country": r[0] or "unknown", "count": int(r[1])} for r in await cur.fetchall()]

        async with db.execute(
            """SELECT COUNT(*) FROM tasks
               WHERE status IN ('reasoning','planning','executing','evaluating')"""
        ) as cur:
            active_tasks = int((await cur.fetchone())[0])

        cutoff_day = datetime.utcfromtimestamp(
            datetime.utcnow().timestamp() - 24 * 3600
        ).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (cutoff_day,)
        ) as cur:
            tasks_today = int((await cur.fetchone())[0])
        cutoff_week = datetime.utcfromtimestamp(
            datetime.utcnow().timestamp() - 7 * 86400
        ).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (cutoff_week,)
        ) as cur:
            tasks_week = int((await cur.fetchone())[0])
        cutoff_month = datetime.utcfromtimestamp(
            datetime.utcnow().timestamp() - 30 * 86400
        ).isoformat()
        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (cutoff_month,)
        ) as cur:
            tasks_month = int((await cur.fetchone())[0])

        async with db.execute(
            """SELECT
                SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
                AVG(eval_score) as avg_score
               FROM tasks WHERE created_at >= ?""",
            (cutoff_month,),
        ) as cur:
            row = await cur.fetchone()
            done_m = int(row[0] or 0)
            failed_m = int(row[1] or 0)
            avg_score = float(row[2] or 0.0)
        tot_m = done_m + failed_m
        success_rate = round(done_m / max(tot_m, 1), 4)

        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='paid'"
        ) as cur:
            total_revenue_paise = int((await cur.fetchone())[0])
        month_prefix = datetime.utcnow().strftime("%Y-%m")
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='paid' AND substr(created_at,1,7)=?",
            (month_prefix,),
        ) as cur:
            month_revenue_paise = int((await cur.fetchone())[0])

    mrr_paise = 0
    for plan_name, cnt in plan_breakdown.items():
        p = PLAN_PRICING.get(plan_name)
        if p:
            mrr_paise += int(p["amount"]) * int(cnt)

    paid_users = sum(
        plan_breakdown.get(p, 0) for p in ("starter", "pro", "pro_monthly", "enterprise")
    )
    arpu = round((total_revenue_paise / 100.0) / max(paid_users, 1), 2)

    feed: list[dict[str, Any]] = []
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT email, created_at FROM users ORDER BY created_at DESC LIMIT 8"
        ) as cur:
            for r in await cur.fetchall():
                feed.append(
                    {
                        "type": "user_registered",
                        "message": f"User {r[0]} registered",
                        "at": r[1],
                    }
                )
        async with db.execute(
            """SELECT task_id, status, eval_score, user_id, created_at
               FROM tasks ORDER BY created_at DESC LIMIT 12"""
        ) as cur:
            for r in await cur.fetchall():
                st = r[1]
                if st == "done":
                    sc = r[2]
                    feed.append(
                        {
                            "type": "task_done",
                            "message": f"Task #{str(r[0])[:8]} DONE (score {float(sc or 0):.2f})",
                            "at": r[4],
                            "task_id": r[0],
                        }
                    )

    feed.sort(key=lambda x: x.get("at") or "", reverse=True)
    feed = feed[:20]

    import os

    try:
        dbs = os.path.getsize(settings.db_path)
    except Exception:
        dbs = 0

    return {
        "generated_at": now,
        "system": {
            "active_tasks": active_tasks,
            "db_size_bytes": dbs,
            "last_backup": None,
        },
        "users": {
            "total": total_users,
            "new_today": new_today,
            "active_this_week": active_week,
            "plan_breakdown": plan_breakdown,
            "by_country": by_country,
        },
        "revenue": {
            "mrr_inr": round(mrr_paise / 100.0, 2),
            "mrr_paise": mrr_paise,
            "total_revenue_inr": round(total_revenue_paise / 100.0, 2),
            "month_revenue_inr": round(month_revenue_paise / 100.0, 2),
            "churn_estimated": 0,
            "arpu_inr": arpu,
        },
        "usage": {
            "tasks_today": tasks_today,
            "tasks_week": tasks_week,
            "tasks_month": tasks_month,
            "success_rate_month": success_rate,
            "avg_eval_score_month": round(avg_score, 4),
            "top_tools": [],
            "top_templates": [],
        },
        "activity_feed": feed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Launch batch — teams, marketplace, audit (Tasks 86–87, 89)
# ─────────────────────────────────────────────────────────────────────────────


async def _ensure_launch_migrations() -> None:
    root = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    for name in ("0018_teams.sql", "0019_marketplace.sql", "0020_audit_gem.sql"):
        p = root / name
        if not p.is_file():
            continue
        sql = p.read_text(encoding="utf-8")
        async with get_pool().acquire() as db:
            await db.executescript(sql)
            await db.commit()


async def insert_audit_log(
    user_id: str,
    action: str,
    resource: str = "",
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO audit_logs (user_id, action, resource, ip_address, user_agent, created_at)
               VALUES (?,?,?,?,?,?)""",
            (user_id, action, resource or "", ip_address or "", user_agent or "", now),
        )
        await db.commit()


async def list_audit_logs(
    limit: int = 100,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
) -> list[dict]:
    lim = max(1, min(int(limit), 500))
    q = "SELECT * FROM audit_logs WHERE 1=1"
    args: list[Any] = []
    if user_id:
        q += " AND user_id=?"
        args.append(user_id)
    if action:
        q += " AND action=?"
        args.append(action)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(lim)
    async with get_pool().acquire() as db:
        db.row_factory = sqlite3.Row
        async with db.execute(q, tuple(args)) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def create_team(name: str, owner_id: str, plan: str = "starter") -> dict[str, Any]:
    tid = str(uuid.uuid4())
    code = secrets.token_urlsafe(8)[:12]
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO teams (team_id, name, owner_id, plan, invite_code, created_at)
               VALUES (?,?,?,?,?,?)""",
            (tid, name.strip(), owner_id, plan, code, now),
        )
        await db.execute(
            """INSERT INTO team_members (team_id, user_id, role, joined_at) VALUES (?,?,?,?)""",
            (tid, owner_id, "owner", now),
        )
        await db.commit()
    return {"team_id": tid, "name": name, "invite_code": code}


async def get_team(team_id: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute("SELECT * FROM teams WHERE team_id=?", (team_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_team_by_invite(code: str) -> Optional[dict]:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT * FROM teams WHERE invite_code=?", (code.strip(),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_team_member(team_id: str, user_id: str, role: str = "member") -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT OR IGNORE INTO team_members (team_id, user_id, role, joined_at)
               VALUES (?,?,?,?)""",
            (team_id, user_id, role, now),
        )
        await db.commit()


async def list_team_members(team_id: str) -> list[dict]:
    async with get_pool().acquire() as db:
        db.row_factory = sqlite3.Row
        async with db.execute(
            "SELECT * FROM team_members WHERE team_id=?", (team_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def remove_team_member(team_id: str, user_id: str) -> bool:
    async with get_pool().acquire() as db:
        cur = await db.execute(
            "DELETE FROM team_members WHERE team_id=? AND user_id=? AND role!='owner'",
            (team_id, user_id),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def link_team_task(team_id: str, task_id: str, assigned_to: str = "") -> None:
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO team_tasks (team_id, task_id, assigned_to, created_at)
               VALUES (?,?,?,?)""",
            (team_id, task_id, assigned_to, now),
        )
        await db.commit()


async def assign_team_task(team_id: str, task_id: str, assign_to_user_id: str) -> bool:
    async with get_pool().acquire() as db:
        cur = await db.execute(
            """UPDATE team_tasks SET assigned_to=? WHERE team_id=? AND task_id=?""",
            (assign_to_user_id, team_id, task_id),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def list_team_tasks_for_user(team_id: str, viewer_id: str, is_owner: bool) -> list[dict]:
    async with get_pool().acquire() as db:
        db.row_factory = sqlite3.Row
        if is_owner:
            async with db.execute(
                """SELECT t.* FROM tasks t
                   JOIN team_tasks tt ON tt.task_id = t.task_id
                   WHERE tt.team_id=? ORDER BY t.created_at DESC LIMIT 200""",
                (team_id,),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                """SELECT t.* FROM tasks t
                   JOIN team_tasks tt ON tt.task_id = t.task_id
                   WHERE tt.team_id=? AND t.user_id=? ORDER BY t.created_at DESC LIMIT 200""",
                (team_id, viewer_id),
            ) as cur:
                rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def marketplace_publish(
    author_user_id: str,
    name: str,
    description: str,
    code: str,
    price_inr: int,
    category: str,
) -> dict[str, Any]:
    tid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO marketplace_tools
               (tool_id, name, description, author_user_id, price_inr, category, code, is_approved, created_at)
               VALUES (?,?,?,?,?,?,?,0,?)""",
            (tid, name, description, author_user_id, int(price_inr), category or "general", code, now),
        )
        await db.commit()
    return {"tool_id": tid, "status": "pending_review"}


async def marketplace_list_approved(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "popular",
) -> list[dict]:
    q = "SELECT tool_id, name, description, author_user_id, price_inr, category, downloads, rating, is_approved, created_at FROM marketplace_tools WHERE is_approved=1"
    args: list[Any] = []
    if category:
        q += " AND category=?"
        args.append(category)
    if search:
        q += " AND (name LIKE ? OR description LIKE ?)"
        args.extend([f"%{search}%", f"%{search}%"])
    q += " ORDER BY downloads DESC" if sort == "popular" else " ORDER BY created_at DESC"
    async with get_pool().acquire() as db:
        db.row_factory = sqlite3.Row
        async with db.execute(q, tuple(args)) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def marketplace_get(tool_id: str, public_only: bool = True) -> Optional[dict]:
    async with get_pool().acquire() as db:
        db.row_factory = sqlite3.Row
        if public_only:
            async with db.execute(
                "SELECT * FROM marketplace_tools WHERE tool_id=? AND is_approved=1",
                (tool_id,),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with db.execute(
                "SELECT * FROM marketplace_tools WHERE tool_id=?", (tool_id,)
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None


async def marketplace_pending() -> list[dict]:
    async with get_pool().acquire() as db:
        db.row_factory = sqlite3.Row
        async with db.execute(
            "SELECT * FROM marketplace_tools WHERE is_approved=0 ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def marketplace_approve(tool_id: str) -> bool:
    async with get_pool().acquire() as db:
        cur = await db.execute(
            "UPDATE marketplace_tools SET is_approved=1 WHERE tool_id=?", (tool_id,)
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def marketplace_purchase(
    tool_id: str, buyer_id: str, amount_paise: int
) -> dict[str, Any]:
    now = datetime.utcnow().isoformat()
    author_share = int(amount_paise * 0.7)
    platform_share = amount_paise - author_share
    async with get_pool().acquire() as db:
        await db.execute(
            """INSERT INTO tool_purchases (tool_id, buyer_id, amount, author_share, platform_share, purchased_at)
               VALUES (?,?,?,?,?,?)""",
            (tool_id, buyer_id, amount_paise, author_share, platform_share, now),
        )
        await db.execute(
            "UPDATE marketplace_tools SET downloads=downloads+1 WHERE tool_id=?", (tool_id,)
        )
        await db.commit()
    return {"author_share_paise": author_share, "platform_share_paise": platform_share}


async def marketplace_rate(tool_id: str, rating: float, review: str) -> None:
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT rating, downloads FROM marketplace_tools WHERE tool_id=?", (tool_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        old_r, dls = float(row[0] or 0), int(row[1] or 0)
        n = max(1, dls)
        new_r = round((old_r * (n - 1) + rating) / n, 2)
        await db.execute(
            "UPDATE marketplace_tools SET rating=? WHERE tool_id=?", (new_r, tool_id)
        )
        await db.commit()


async def marketplace_earnings(author_user_id: str) -> dict[str, Any]:
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT COALESCE(SUM(tp.author_share),0) FROM tool_purchases tp
               JOIN marketplace_tools m ON m.tool_id = tp.tool_id
               WHERE m.author_user_id=?""",
            (author_user_id,),
        ) as cur:
            total = int((await cur.fetchone())[0])
    return {"author_user_id": author_user_id, "total_earnings_paise": total}


async def count_active_running_tasks() -> int:
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT COUNT(*) FROM tasks
               WHERE status IN ('reasoning','planning','executing','evaluating')"""
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0
