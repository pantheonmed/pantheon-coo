"""
main.py
────────
Pantheon COO OS v2 — FastAPI Application

The Command Interface layer. Every request becomes a task that the
Orchestrator processes asynchronously through the multi-agent loop.

Endpoints:
  POST /execute              Submit a natural language command
  GET  /tasks/{id}           Poll task status + results
  GET  /tasks/{id}/logs      Execution logs for a task
  GET  /tasks/{id}/stream    SSE: logs + live activity (agents, steps, loops)
  GET  /tasks                List recent tasks
  GET  /health               Health check
  GET  /stats                Dashboard statistics
  GET  /memory/learnings     Inspect what the COO has learned

Run:
  uvicorn main:app --reload --host 0.0.0.0 --port 8002
"""
import json
import uuid
import asyncio
import hashlib
import hmac
import os
import time
import secrets
import shlex
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Depends, File, UploadFile, Query, Body
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, Response, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

_start_time = time.monotonic()

from config import PLAN_LIMITS, settings
from models import (
    CommandRequest, CommandResponse, TaskStatus,
    PlanningOutput, StepResult,
    AuthRegisterBody, AuthLoginBody, TemplateRunBody,
)
import memory.store as store
from memory.db_pool import get_pool
import orchestrator

try:
    from whatsapp import router as whatsapp_router
except Exception as e:
    print(f"[Import] whatsapp router skipped: {e}")
    whatsapp_router = None

try:
    from telegram_bot import router as telegram_router
except Exception as e:
    print(f"[Import] telegram_bot router skipped: {e}")
    telegram_router = None
from scheduler import router as scheduler_router, init_scheduler, scheduler_loop
from tools.registry import load_all_custom_tools
from monitor import monitor_loop, get_metrics
from agents.prompt_optimizer import init_prompt_store, get_prompt_history
from agents.model_router import router_status
from security.auth import require_admin, require_auth
from security.rate_limit import (
    rate_limit,
    execute_rate_limit,
    current_usage,
    current_usage_for_request,
    plan_limits_for_auth,
)
from agents.decomposer import decompose
from agents.briefing import generate_briefing, send_briefing
from project_runner import run_project
from logging_config import setup_logging
from billing import router as billing_router


class TerminalRunBody(BaseModel):
    command: str = Field(..., min_length=1, max_length=4000)
    cwd: Optional[str] = None
    timeout: Optional[int] = None


def _terminal_validate_command(cmd: str) -> None:
    """
    Validate a terminal command using the same sandbox rules as plan steps.
    """
    from models import ExecutionStep, ToolName
    from security.sandbox import validate_step

    step = ExecutionStep(
        step_id=1,
        tool=ToolName.TERMINAL,
        action="run_command",
        params={"command": cmd},
        depends_on=[],
        description="terminal.run",
    )
    validate_step(step)
from api_batch import router as api_batch_router
from templates import (
    TEMPLATES,
    filter_by_category,
    get_template_by_id,
    group_by_category,
    prioritize_medical_first,
    substitute_variables,
    validate_industry,
)

SUGGESTED_COMMANDS_DEFAULT = [
    "Check system health and save report",
    "Create a hello world Python script",
    "List all files in workspace",
]
SUGGESTED_COMMANDS_MEDICAL = [
    "Check disk space and generate system health report",
    "Create a sample inventory CSV with 10 medical items",
    "Write a supplier email template for HBOT equipment",
]

ONBOARDING_SAMPLES_BY_INDUSTRY: dict[str, list[str]] = {
    "medical": [
        "Generate CDSCO compliance checklist for HBOT device",
        "Write professional email to medical equipment supplier",
        "Create inventory report for medical devices",
        "Research HBOT therapy market in India",
        "Draft patient information brochure for HBOT therapy",
    ],
    "retail": [
        "Analyze sales data and identify top products",
        "Write product descriptions for 5 items",
        "Create weekly inventory report",
        "Draft customer follow-up email template",
        "Research competitor pricing for similar products",
    ],
    "tech": [
        "Review this Python code for bugs and improvements",
        "Write unit tests for our API endpoints",
        "Create technical documentation for our system",
        "Set up monitoring alerts for server health",
        "Generate weekly development progress report",
    ],
    "finance": [
        "Generate a monthly cashflow summary and save to workspace",
        "Categorize last month’s expenses and flag anomalies",
        "Draft investor update email with key metrics placeholders",
        "Create GST-ready invoice checklist for this quarter",
        "Summarize accounts receivable aging from sample CSV in workspace",
    ],
    "other": [
        "Check system health and save a report to the workspace",
        "Summarize open tasks and next actions in one paragraph",
        "Draft a professional email to follow up with a client",
        "List workspace files and suggest an organization plan",
        "Create a one-page weekly status update in markdown",
    ],
}


from memory.redis_client import cached


@cached(ttl=300, key_prefix="perf_report")
async def _cached_performance_report(period: str, uid_key: str):
    from performance_report import build_performance_report

    return await build_performance_report(period)


@cached(ttl=600, key_prefix="admin_analytics")
async def _cached_admin_analytics(period: str):
    from analytics import build_admin_report

    return await build_admin_report(period)


# ─────────────────────────────────────────────────────────────────────────────
# Startup / shutdown
# ─────────────────────────────────────────────────────────────────────────────

async def _background_startup_rest() -> None:
    """Optional services after DB + scheduler (does not block /health)."""
    t0 = time.monotonic()
    try:
        if settings.white_label_enabled:
            import branding_runtime

            branding_runtime.load_branding_file()
    except Exception as e:
        print(f"White label warning: {e}")
    try:
        if settings.otel_enabled:
            from monitoring import tracing as tracing_mod

            tracing_mod.init_tracing()
    except Exception as e:
        print(f"[OTel] init skipped: {e}")
    try:
        recovered = await store.recover_stuck_tasks()
        if recovered:
            print(f"[Startup] Recovered {len(recovered)} stuck task(s) from previous session")
            for row in recovered:
                print(f"  → {row['task_id'][:8]}… was {row['status']!r}: {row['command'][:60]!r}")
    except Exception as e:
        print(f"Stuck-task recovery warning: {e}")
    try:
        await store.init_projects()
    except Exception as e:
        print(f"Projects init warning: {e}")
    try:
        await init_prompt_store()
    except Exception as e:
        print(f"Prompt store warning: {e}")
    try:
        await load_all_custom_tools()
        print("  [Startup] Optional heavy tool modules can be lazy-loaded via tools.lazy_loader.get_tool")
    except Exception as e:
        print(f"Custom tools warning: {e}")
    try:
        asyncio.create_task(monitor_loop())
    except Exception as e:
        print(f"Monitor warning: {e}")
    try:
        if getattr(settings, "distributed_task_queue", False):
            from taskqueue.task_queue import start_worker_tasks

            start_worker_tasks()
    except Exception as e:
        print(f"Task queue warning: {e}")
    startup_ms = int((time.monotonic() - t0) * 1000)
    print(f"  [Startup] Optional services completed in {startup_ms}ms")
    print(f"\n{settings.app_name} v{settings.app_version} services ready. "
          f"Backend:{settings.port}  Frontend:{settings.frontend_port}\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import pathlib

    for d in ["/tmp/pantheon_v2", "/tmp/pantheon_v2/logs",
              "/tmp/pantheon_v2/screenshots", "/tmp/pantheon_v2/users",
              "tools/custom"]:
        pathlib.Path(d).mkdir(parents=True, exist_ok=True)
    pathlib.Path(settings.workspace_dir, "users").mkdir(parents=True, exist_ok=True)
    try:
        setup_logging(dev_mode=settings.debug)
    except Exception as e:
        print(f"Logging warning: {e}")
    try:
        await store.init()
    except Exception as e:
        print(f"DB init warning: {e}")
    try:
        await init_scheduler()
        app.state.scheduler_task = asyncio.create_task(scheduler_loop())
    except Exception as e:
        print(f"Scheduler warning: {e}")
    try:
        from security.self_protector import SelfProtector

        app.state.self_protector = SelfProtector()
        app.state.self_protector_task = asyncio.create_task(app.state.self_protector.monitor_continuously())
    except Exception as e:
        print(f"SelfProtector warning: {e}")
    asyncio.create_task(_background_startup_rest())
    print("[Startup] Accepting HTTP; optional services initializing in background…")
    yield
    print("Shutting down...")
    try:
        t = getattr(app.state, "scheduler_task", None)
        if t is not None:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    except Exception:
        pass
    try:
        st = getattr(app.state, "self_protector_task", None)
        if st is not None:
            st.cancel()
    except Exception:
        pass
    try:
        from memory.redis_client import close_redis

        await close_redis()
    except Exception:
        pass
    try:
        from tools.browser import close_all

        await close_all()
        print("  Browser sessions closed.")
    except Exception:
        pass
    print("Shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Autonomous AI Chief Operating Officer — Multi-Agent System",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Auth", "description": "Registration, login, JWT, profile"},
        {"name": "Tasks", "description": "Execute commands, poll status, logs, SSE"},
        {"name": "Billing", "description": "Plans, checkout, payment verification"},
        {"name": "Admin", "description": "Operator analytics and dashboard"},
        {"name": "Projects", "description": "Multi-step project goals"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://trycooai.com"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def blocked_ip_guard(request: Request, call_next):
    try:
        ip = (request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else ""
        if ip and await store.is_ip_blocked(ip):
            await store.log_security_event(
                "IP_BLOCKED_REQUEST",
                ip,
                f"Blocked request to {request.url.path}",
                severity="high",
            )
            return Response(content="Access denied", status_code=403)
    except Exception:
        pass
    return await call_next(request)


@app.middleware("http")
async def api_call_counter(request: Request, call_next):
    try:
        await store.record_api_call()
    except Exception:
        pass
    return await call_next(request)


@app.middleware("http")
async def admin_protection(request: Request, call_next):
    if request.url.path.startswith("/admin"):
        try:
            allowed = [x.strip() for x in (settings.admin_allowed_ips or "").split(",") if x.strip()]
            if allowed:
                ip = (request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
                if not ip:
                    ip = request.client.host if request.client else ""
                if ip and ip not in allowed:
                    await store.log_security_event(
                        "ADMIN_UNAUTHORIZED_ACCESS",
                        ip,
                        f"Blocked admin access from {ip}",
                        severity="high",
                    )
                    return Response(
                        content=json.dumps({"error": "Access denied"}),
                        media_type="application/json",
                        status_code=403,
                    )
        except Exception:
            pass
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # CSP must allow inline dashboard scripts + Razorpay/Stripe embeds
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://checkout.razorpay.com https://js.stripe.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' https://trycooai.com; "
        "frame-src https://checkout.razorpay.com https://js.stripe.com; "
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    try:
        response.headers.pop("server", None)
    except Exception:
        pass
    return response


@app.middleware("http")
async def pantheon_error_tracking_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        from fastapi import HTTPException
        from fastapi.exceptions import RequestValidationError

        if isinstance(e, (HTTPException, RequestValidationError)):
            raise
        try:
            from monitoring.error_tracker import track_error

            await track_error(e, context={"path": request.url.path})
        except Exception:
            pass
        raise


@app.middleware("http")
async def language_context_middleware(request: Request, call_next):
    from i18n.translations import get_supported_languages, parse_accept_language

    allowed = {x["code"] for x in get_supported_languages()}
    lang = request.query_params.get("lang")
    if (not lang) or (lang not in allowed):
        auth_h = request.headers.get("authorization", "")
        if auth_h.startswith("Bearer "):
            try:
                from security import user_auth

                if settings.jwt_secret:
                    tok = auth_h.split(" ", 1)[1].strip()
                    pl = user_auth.verify_jwt(tok)
                    uid = pl and pl.get("sub")
                    if uid:
                        u = await store.get_user_by_id(uid)
                        if u and u.get("language"):
                            lang = u["language"]
            except Exception:
                pass
    if (not lang) or (lang not in allowed):
        lang = parse_accept_language(request.headers.get("accept-language", ""), allowed)
    if (not lang) or (lang not in allowed):
        lang = settings.default_language
    request.state.lang = lang
    return await call_next(request)


# ── Password-protected /admin HTML (ADMIN_PASSWORD) ─────────────────────────
ADMIN_UI_COOKIE = "pantheon_admin_ui"


def _admin_session_token() -> str:
    key = (settings.jwt_secret or "pantheon") + (settings.admin_password or "")
    return hmac.new(key.encode(), b"pantheon-admin-ui-v1", hashlib.sha256).hexdigest()


def _admin_cookie_ok(request: Request) -> bool:
    if not (settings.admin_password or "").strip():
        return False
    c = request.cookies.get(ADMIN_UI_COOKIE)
    if not c:
        return False
    try:
        return secrets.compare_digest(c, _admin_session_token())
    except Exception:
        return False


ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Admin — Pantheon COO OS</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f1117;color:#e8eaef;min-height:100vh;display:flex;align-items:center;justify-content:center;margin:0;}
form{background:#1a1d27;border:1px solid #2a2f3d;border-radius:12px;padding:28px;max-width:360px;width:100%;}
h1{font-size:1.1rem;color:#7c6ff7;margin:0 0 16px;}
label{display:block;font-size:12px;color:#8b92a8;margin-bottom:6px;}
input{width:100%;padding:10px;border-radius:8px;border:1px solid #2a2f3d;background:#0f1117;color:#e8eaef;box-sizing:border-box;}
button{margin-top:16px;width:100%;padding:10px;border:none;border-radius:8px;background:linear-gradient(135deg,#7c6ff7,#5a4fd4);color:#fff;font-weight:600;cursor:pointer;}
</style></head>
<body>
<form method="post" action="/admin/login">
<h1>Admin login</h1>
<label>Password</label>
<input type="password" name="password" required autocomplete="current-password"/>
<button type="submit">Sign in</button>
</form>
</body></html>"""


# Dashboard
import os as _os
if _os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/admin/login", include_in_schema=False)
async def admin_password_login(request: Request):
    """Set HttpOnly cookie after checking ADMIN_PASSWORD (form or JSON)."""
    if not (settings.admin_password or "").strip():
        raise HTTPException(503, "Admin UI not configured (set ADMIN_PASSWORD)")
    pwd = ""
    ct = (request.headers.get("content-type") or "").lower()
    if "application/json" in ct:
        try:
            body = await request.json()
            pwd = str((body or {}).get("password") or "")
        except Exception:
            pwd = ""
    else:
        form = await request.form()
        pwd = str(form.get("password") or "")
    if not secrets.compare_digest(pwd.strip(), settings.admin_password.strip()):
        raise HTTPException(401, "Invalid password")
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie(
        ADMIN_UI_COOKIE,
        _admin_session_token(),
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
        path="/",
    )
    return resp


@app.get("/admin/logout", include_in_schema=False)
async def admin_logout():
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.delete_cookie(ADMIN_UI_COOKIE, path="/")
    return resp


@app.get("/admin/data", include_in_schema=False)
async def admin_data_json(request: Request):
    if not _admin_cookie_ok(request):
        raise HTTPException(401, "Admin login required")
    users_raw = await store.list_all_users(500)
    users_out = []
    for u in users_raw:
        uid = u["user_id"]
        tc = await store.count_tasks_for_user(uid)
        users_out.append(
            {
                "user_id": uid,
                "email": u.get("email"),
                "plan": u.get("plan") or "free",
                "created_at": u.get("created_at"),
                "task_count": tc,
            }
        )
    st = await store.get_stats()
    total = int(st.get("total") or 0)
    by = st.get("tasks") or {}
    done = int(by.get("done") or 0)
    failed = int(by.get("failed") or 0)
    success_rate = round(100.0 * done / max(total, 1), 2)
    return {
        "users": users_out,
        "allowed_plans": sorted(PLAN_LIMITS.keys()),
        "stats": {
            "total_tasks": total,
            "done": done,
            "failed": failed,
            "success_rate_pct": success_rate,
            "avg_eval_score": st.get("avg_eval_score"),
        },
    }


class AdminSetPlanBody(BaseModel):
    plan: str = Field(..., min_length=2, max_length=32)


@app.post("/admin/users/{user_id}/plan", include_in_schema=False)
async def admin_set_user_plan(request: Request, user_id: str, body: AdminSetPlanBody):
    if not _admin_cookie_ok(request):
        raise HTTPException(401, "Admin login required")
    plan = body.plan.strip().lower()
    if plan not in PLAN_LIMITS:
        raise HTTPException(400, f"Invalid plan. Allowed: {', '.join(sorted(PLAN_LIMITS))}")
    u = await store.get_user_by_id(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    await store.update_user_plan(user_id, plan)
    return {"ok": True, "user_id": user_id, "plan": plan}


@app.get("/admin", include_in_schema=False)
async def admin_html_page(request: Request):
    """Password-protected admin dashboard (static/admin_panel.html)."""
    if not (settings.admin_password or "").strip():
        return HTMLResponse(
            "<h1>Admin UI disabled</h1><p>Set <code>ADMIN_PASSWORD</code> in the environment.</p>",
            status_code=503,
        )
    if not _admin_cookie_ok(request):
        return HTMLResponse(ADMIN_LOGIN_HTML)
    path = "static/admin_panel.html"
    if _os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<p>Missing static/admin_panel.html</p>", status_code=500)

@app.get("/")
async def home():
    """Marketing landing page (static/landing.html)."""
    return FileResponse("static/landing.html")


@app.get("/dashboard")
async def dashboard():
    """Main COO dashboard UI (static/dashboard.html)."""
    return FileResponse("static/dashboard.html")


@app.get("/app")
async def app_entry():
    return FileResponse("static/dashboard.html")


@app.get("/landing")
async def landing_page():
    """Alias: same marketing page as ``GET /``."""
    return FileResponse("static/landing.html")


@app.get("/docs-page", summary="Static developer documentation (HTML)")
async def docs_page():
    return FileResponse("static/docs.html")


@app.get("/sitemap.xml", summary="Sitemap for crawlers")
async def sitemap_xml():
    base = "https://pantheon.ai"
    paths = ["/", "/dashboard", "/docs-page", "/landing", "/auth/login", "/auth/register"]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for p in paths:
        parts.append(f"<url><loc>{base}{p}</loc></url>")
    parts.append("</urlset>")
    return Response(content="".join(parts), media_type="application/xml")


@app.get("/robots.txt", summary="Robots rules")
async def robots_txt():
    return FileResponse("static/robots.txt")


@app.get("/i18n/languages")
async def http_i18n_languages():
    from i18n.translations import get_supported_languages

    return {"languages": get_supported_languages()}


@app.get("/i18n/translations/{lang_code}")
async def http_i18n_translations(lang_code: str):
    from i18n.translations import TRANSLATIONS

    d = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])
    return {"lang": lang_code, "translations": d}


class LanguagePatchBody(BaseModel):
    language: str = Field(..., min_length=2, max_length=8)


class TimezonePatchBody(BaseModel):
    timezone: str = Field(..., min_length=3, max_length=64)


# WhatsApp / Telegram (optional — import may be skipped if deps fail)
if whatsapp_router is not None:
    app.include_router(whatsapp_router)
if telegram_router is not None:
    app.include_router(telegram_router)
app.include_router(scheduler_router)
app.include_router(billing_router)
app.include_router(api_batch_router)


# ─────────────────────────────────────────────────────────────────────────────
# Voice — Whisper + TTS (requires OPENAI_API_KEY)
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/voice/transcribe")
async def voice_transcribe(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auto_execute: bool = Query(False),
    auth: dict = Depends(require_auth),
    _rate: None = Depends(execute_rate_limit),
):
    """
    Upload audio; transcribe with Whisper.
    If auto_execute=true, queues a COO task with the transcribed text.
    """
    from agents.voice import transcribe_audio

    data = await file.read()
    mime = file.content_type or "audio/ogg"
    text = await transcribe_audio(data, mime)
    out: dict = {"text": text}
    if not auto_execute:
        return out

    task_id = str(uuid.uuid4())
    uid = auth.get("user_id")
    ctx: dict = {"language": getattr(request.state, "lang", settings.default_language)}
    if uid:
        ctx["user_id"] = uid
    await store.create_task(task_id, text, source="api", user_id=uid)
    try:
        from analytics import track as track_analytics

        await track_analytics("task_submitted", uid or "", source="api", goal_type="voice")
    except Exception:
        pass
    background_tasks.add_task(
        orchestrator.run,
        task_id=task_id,
        command=text,
        context=ctx,
        dry_run=False,
    )
    out["task_id"] = task_id
    return out


@app.get("/voice/speak")
async def voice_speak(
    text: str = Query(..., min_length=1),
    auth: dict = Depends(require_auth),
):
    """TTS: returns MP3 bytes for dashboard / clients."""
    from agents.voice import text_to_speech

    try:
        audio = await text_to_speech(text[:4096])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return Response(content=audio, media_type="audio/mpeg")


# ─────────────────────────────────────────────────────────────────────────────
# Brand — personal brand / viral content (Claude)
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/brand/strategy")
async def brand_strategy_endpoint(
    body: dict = Body(...),
    _auth: dict = Depends(require_auth),
):
    from agents.brand_agent import BrandAgent

    ag = BrandAgent()
    return await ag.create_brand_strategy(
        str(body.get("name") or ""),
        str(body.get("profession") or ""),
        list(body.get("goals") or []),
        str(body.get("audience") or ""),
    )


@app.post("/brand/viral-ideas")
async def brand_viral_ideas(
    body: dict = Body(...),
    _auth: dict = Depends(require_auth),
):
    from agents.brand_agent import BrandAgent

    ag = BrandAgent()
    n = int(body.get("count") or 10)
    return await ag.generate_viral_ideas(str(body.get("niche") or ""), n)


@app.post("/brand/content-pack")
async def brand_content_pack(
    body: dict = Body(...),
    _auth: dict = Depends(require_auth),
):
    from agents.brand_agent import BrandAgent

    ag = BrandAgent()
    return await ag.create_content_pack(
        str(body.get("brand_name") or ""),
        int(body.get("week_number") or 1),
        list(body.get("topics") or []),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auth — multi-user (JWT + per-user API keys)
# ─────────────────────────────────────────────────────────────────────────────

def _auth_user_filter(auth: dict) -> tuple[Optional[str], bool]:
    """For list_tasks: user_id filter (None = legacy unscoped) and admin flag."""
    if auth.get("mode") == "none":
        return None, False
    if auth.get("role") == "admin":
        return None, True
    uid = auth.get("user_id")
    if uid is None:
        return None, False
    return uid, False


def _can_view_task(auth: dict, row: dict) -> bool:
    if auth.get("mode") == "none":
        return True
    if auth.get("role") == "admin":
        return True
    uid = auth.get("user_id")
    if uid is None:
        return True
    ruid = row.get("user_id")
    if ruid is None:
        return False
    return ruid == uid


def _require_authenticated_user(auth: dict) -> str:
    uid = auth.get("user_id")
    if not uid:
        raise HTTPException(401, "Authentication required")
    return uid


@app.post("/auth/register")
async def auth_register(body: AuthRegisterBody):
    from security import user_auth

    try:
        ind = validate_industry(body.industry)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        u = await user_auth.create_user(
            body.email,
            body.name,
            body.password,
            industry=ind,
            ref_code=body.ref_code,
            country_code=body.country_code,
            timezone=body.timezone,
        )
        try:
            from analytics import track as track_analytics

            await track_analytics(
                "user_registered",
                u["user_id"],
                plan=u.get("plan", "free"),
                industry=u.get("industry", ind),
            )
        except Exception:
            pass
        return {
            "user_id": u["user_id"],
            "email": u["email"],
            "name": u["name"],
            "api_key": u["api_key"],
            "plan": u["plan"],
            "industry": u.get("industry", ind),
            "country_code": u.get("country_code", "IN"),
            "currency": u.get("currency", "INR"),
            "timezone": u.get("timezone", "Asia/Kolkata"),
            "locale": u.get("locale", "en-IN"),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/auth/login")
async def auth_login(request: Request, body: AuthLoginBody):
    from security import user_auth

    u = await user_auth.authenticate_user(body.email, body.password)
    if not u:
        raise HTTPException(401, "Invalid email or password")
    token = user_auth.create_jwt(u["user_id"], u["email"], u["role"])
    await user_auth.update_last_login(u["user_id"])
    exp = datetime.utcnow() + timedelta(hours=settings.jwt_expiry_hours)
    await store.insert_user_session(
        str(uuid.uuid4()),
        u["user_id"],
        token,
        exp.isoformat(),
    )
    ip = request.client.host if request.client else ""
    await store.insert_audit_log(
        u["user_id"],
        "login",
        "session",
        ip,
        request.headers.get("user-agent", "") or "",
    )
    return {
        "token": token,
        "user_id": u["user_id"],
        "email": u["email"],
        "name": u["name"],
        "role": u.get("role") or "user",
        "plan": u["plan"],
        "api_key": u.get("api_key") or "",
        "industry": u.get("industry") or "other",
        "language": u.get("language") or "en",
        "currency": u.get("currency") or "INR",
        "country_code": u.get("country_code") or "IN",
        "timezone": u.get("timezone") or "Asia/Kolkata",
        "locale": u.get("locale") or "en-IN",
    }


@app.post("/auth/logout")
async def auth_logout(auth: dict = Depends(require_auth)):
    from security import user_auth

    jti = auth.get("jti")
    if jti:
        user_auth.revoke_jwt_jti(jti)
    return {"ok": True}


@app.get("/auth/me")
async def auth_me(auth: dict = Depends(require_auth)):
    if auth.get("mode") == "none":
        raise HTTPException(401, "Authentication required (use AUTH_MODE=jwt)")
    uid = auth.get("user_id")
    if not uid:
        raise HTTPException(401, "Authentication required")
    u = await store.get_user_by_id(uid)
    if not u:
        raise HTTPException(404, "User not found")
    tasks_n = await store.count_tasks_for_user(uid)
    return {
        "user_id": u["user_id"],
        "email": u["email"],
        "name": u["name"],
        "role": u["role"],
        "plan": u["plan"],
        "industry": u.get("industry") or "other",
        "is_active": bool(u.get("is_active", 1)),
        "last_login": u.get("last_login"),
        "usage": {"tasks_total": tasks_n},
        "language": u.get("language") or "en",
        "currency": u.get("currency") or "INR",
        "country_code": u.get("country_code") or "IN",
        "timezone": u.get("timezone") or "Asia/Kolkata",
        "locale": u.get("locale") or "en-IN",
    }


@app.patch("/auth/me/language")
async def auth_patch_language(body: LanguagePatchBody, auth: dict = Depends(require_auth)):
    from i18n.translations import get_supported_languages

    uid = _require_authenticated_user(auth)
    allowed = {x["code"] for x in get_supported_languages()}
    if body.language not in allowed:
        raise HTTPException(400, "Unsupported language")
    await store.update_user_language(uid, body.language)
    return {"language": body.language}


@app.patch("/auth/me/timezone")
async def auth_patch_timezone(body: TimezonePatchBody, auth: dict = Depends(require_auth)):
    import pytz

    from utils.timezone import now_for_user

    uid = _require_authenticated_user(auth)
    try:
        pytz.timezone(body.timezone)
    except Exception:
        raise HTTPException(400, "Invalid timezone")
    await store.update_user_timezone(uid, body.timezone)
    return {
        "timezone": body.timezone,
        "current_time_for_user": now_for_user(body.timezone).isoformat(),
    }


@app.post("/auth/refresh")
async def auth_refresh(auth: dict = Depends(require_auth)):
    from security import user_auth

    if auth.get("jti") is None:
        raise HTTPException(400, "Refresh requires a JWT bearer token")
    uid = _require_authenticated_user(auth)
    u = await store.get_user_by_id(uid)
    if not u:
        raise HTTPException(404, "User not found")
    return {"token": user_auth.create_jwt(u["user_id"], u["email"], u["role"])}


@app.post("/auth/reset-api-key")
async def auth_reset_api_key(auth: dict = Depends(require_auth)):
    from security import user_auth

    uid = _require_authenticated_user(auth)
    new_key = user_auth.generate_api_key()
    await store.update_user_api_key(uid, new_key)
    return {"api_key": new_key}


@app.get("/onboarding/samples")
async def onboarding_samples(
    industry: str = Query("other", description="medical | retail | tech | finance | other"),
) -> dict[str, Any]:
    """Public sample commands for onboarding emails and landing helpers."""
    key = (industry or "other").strip().lower()
    if key not in ONBOARDING_SAMPLES_BY_INDUSTRY:
        key = "other"
    samples = ONBOARDING_SAMPLES_BY_INDUSTRY[key]
    return {"industry": key, "samples": samples, "count": len(samples)}


@app.get("/tutorials")
async def list_tutorials() -> dict[str, Any]:
    """Markdown tutorials under static/tutorials/."""
    from pathlib import Path

    base = Path("static/tutorials")
    if not base.is_dir():
        return {"tutorials": []}
    out: list[dict[str, str]] = []
    for p in sorted(base.glob("*.md")):
        title = p.stem.replace("_", " ").title()
        body = p.read_text(encoding="utf-8", errors="replace")
        for line in body.splitlines():
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                break
        out.append(
            {
                "id": p.stem,
                "title": title,
                "path": f"/static/tutorials/{p.name}",
            }
        )
    return {"tutorials": out}


@app.get("/onboarding/suggested-commands")
async def onboarding_suggested_commands(auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    u = await store.get_user_by_id(uid)
    ind = (u.get("industry") or "other").lower() if u else "other"
    if ind == "medical":
        cmds = list(SUGGESTED_COMMANDS_MEDICAL)
    else:
        cmds = list(SUGGESTED_COMMANDS_DEFAULT)
    return {"industry": ind, "commands": cmds}


@app.get("/templates")
async def http_list_templates(category: Optional[str] = None, auth: dict = Depends(require_auth)):
    industry = None
    uid = auth.get("user_id")
    if uid:
        u = await store.get_user_by_id(uid)
        if u:
            industry = u.get("industry") or "other"
    ckey = "templates:all"
    try:
        from memory.redis_client import cache_get, cache_set

        hit = await cache_get(ckey)
        if hit:
            blob = json.loads(hit)
            items = filter_by_category(blob["templates"], category)
            items = prioritize_medical_first(items, industry)
            return {"templates": items, "grouped": group_by_category(items)}
    except Exception:
        pass
    items = filter_by_category(TEMPLATES, category)
    items = prioritize_medical_first(items, industry)
    out = {"templates": items, "grouped": group_by_category(items)}
    try:
        from memory.redis_client import cache_set

        full_items = filter_by_category(TEMPLATES, None)
        await cache_set(
            ckey,
            json.dumps({"templates": full_items}),
            ttl=3600,
        )
    except Exception:
        pass
    return out


@app.get("/templates/{template_id}")
async def http_get_template(template_id: str, auth: dict = Depends(require_auth)):
    t = get_template_by_id(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@app.post("/templates/{template_id}/run", response_model=CommandResponse, status_code=202)
async def http_run_template(
    request: Request,
    template_id: str,
    body: TemplateRunBody,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    _rate: None = Depends(execute_rate_limit),
):
    t = get_template_by_id(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    command = substitute_variables(t["command"], body.variables or {})
    task_id = str(uuid.uuid4())
    ctx: dict = {"language": getattr(request.state, "lang", settings.default_language)}
    uid = _auth.get("user_id")
    if uid:
        ctx["user_id"] = uid
    await store.create_task(task_id, command, "template", user_id=uid)
    try:
        from analytics import track as track_analytics

        await track_analytics(
            "template_used",
            uid or "",
            template_id=template_id,
            category=t.get("category") or "",
        )
    except Exception:
        pass
    background_tasks.add_task(
        orchestrator.run,
        task_id=task_id,
        command=command,
        context=ctx,
        dry_run=False,
    )
    return CommandResponse(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        goal=command[:120],
        summary="Queued from template.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /execute — main entry point
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/execute", response_model=CommandResponse, status_code=202)
async def execute(
    request: Request,
    req: CommandRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    _rate: None = Depends(execute_rate_limit),
):
    """
    Submit a natural language command to the COO.
    Returns immediately with a task_id. Poll /tasks/{id} for status.

    Set dry_run=true to get the AI plan without executing anything.
    """
    from monitoring.tracing import span

    with span(
        "api.execute",
        {"user_id": str(_auth.get("user_id") or ""), "goal_type": "unknown"},
    ):
        pass
    if bool(getattr(settings, "execution_paused", False)):
        raise HTTPException(503, "Execution paused temporarily")
    try:
        from security.sandbox import SecurityError, sanitize_command

        sanitize_command(req.command)
    except SecurityError as e:
        ip = (request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else ""
        await store.log_security_event("INJECTION_BLOCKED", ip, str(e), severity="high", user_id=str(_auth.get("user_id") or ""))
        raise HTTPException(400, str(e))
    task_id = str(uuid.uuid4())
    ctx = dict(req.context or {})
    ctx["language"] = getattr(request.state, "lang", settings.default_language)
    uid = _auth.get("user_id")
    if uid:
        ctx["user_id"] = uid
    if req.team_id and uid:
        ctx["team_id"] = req.team_id
    await store.create_task(task_id, req.command, req.source, user_id=uid)
    if req.team_id and uid:
        try:
            await store.link_team_task(req.team_id, task_id)
        except Exception:
            pass
    try:
        from analytics import track as track_analytics

        await track_analytics(
            "task_submitted",
            uid or "",
            source=req.source or "api",
            goal_type="unknown",
        )
    except Exception:
        pass

    qpos: Optional[int] = None
    if getattr(settings, "distributed_task_queue", False) and not req.dry_run:
        from taskqueue.task_queue import get_task_queue

        tq = get_task_queue()
        d = await tq.queue_depth()
        if d >= int(getattr(settings, "max_queue_depth", 100) or 100):
            raise HTTPException(
                status_code=503,
                detail="System busy. Try again later.",
            )
        qpos = await tq.enqueue(task_id, req.command, user_id=uid or "", context=ctx)
    else:
        background_tasks.add_task(
            orchestrator.run,
            task_id=task_id,
            command=req.command,
            context=ctx,
            dry_run=req.dry_run,
        )

    return CommandResponse(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        goal=req.command[:120],
        summary="Queued. The COO agent loop is starting.",
        queue_position=qpos,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /tasks/{task_id}
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tasks/{task_id}", response_model=CommandResponse)
async def get_task(task_id: str, auth: dict = Depends(require_auth)):
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    if not _can_view_task(auth, row):
        raise HTTPException(404, "Task not found")
    resp = _row_to_response(row)
    if (
        getattr(settings, "distributed_task_queue", False)
        and row.get("status") == "queued"
    ):
        from taskqueue.task_queue import get_task_queue

        pos = await get_task_queue().user_position(task_id)
        if pos:
            if hasattr(resp, "model_copy"):
                resp = resp.model_copy(update={"queue_position": pos})
            else:
                d = resp.model_dump()
                d["queue_position"] = pos
                resp = CommandResponse(**d)
    return resp



@app.post("/tasks/{task_id}/retry", response_model=CommandResponse, status_code=202)
async def retry_task(
    request: Request,
    task_id: str,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    _rate: None = Depends(execute_rate_limit),
):
    """
    Retry a failed or stuck task using the same original command.

    Creates a NEW task (new task_id) that re-runs the same command,
    so the original task record is preserved for audit purposes.
    The new task gets the original task_id in its context so agents
    can access the prior failure for smarter retry reasoning.

    Only tasks with status 'failed' can be retried.
    """
    import uuid as _uuid
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")

    retryable = {"failed"}
    if row["status"] not in retryable:
        raise HTTPException(
            400,
            f"Task status is '{row['status']}'. Only 'failed' tasks can be retried. "
            "Use POST /execute to submit a new command.",
        )

    if not _can_view_task(_auth, row):
        raise HTTPException(404, "Task not found")

    new_task_id = str(_uuid.uuid4())
    original_command = row["command"]
    owner = row.get("user_id") or _auth.get("user_id")

    await store.create_task(
        new_task_id, original_command, source=f"retry:{task_id}", user_id=owner,
    )
    await store.log(
        new_task_id,
        f"Retry of task {task_id[:8]} — original status: {row['status']}",
        "info",
    )

    retry_ctx = {
        "retry_of": task_id,
        "prior_error": row.get("error", ""),
        "prior_summary": row.get("summary", ""),
        "language": getattr(request.state, "lang", settings.default_language),
    }
    if owner:
        retry_ctx["user_id"] = owner

    background_tasks.add_task(
        orchestrator.run,
        task_id=new_task_id,
        command=original_command,
        context=retry_ctx,
        dry_run=False,
    )

    return CommandResponse(
        task_id=new_task_id,
        status=TaskStatus.QUEUED,
        goal=original_command[:120],
        summary=f"Retry of {task_id[:8]}. Prior error: {(row.get('error') or '')[:80]}",
    )


@app.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, auth: dict = Depends(require_auth)):
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    if not _can_view_task(auth, row):
        raise HTTPException(404, "Task not found")
    logs = await store.get_logs(task_id)
    return {"task_id": task_id, "count": len(logs), "logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# GET /tasks/{task_id}/stream  — SSE real-time log stream
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str, auth: dict = Depends(require_auth)):
    """
    Server-Sent Events stream for real-time task monitoring.

    Message types:
      - type=log — same as /tasks/{id}/logs rows
      - type=status — task status, eval_score, loop_iterations
      - type=activity — event_type in agent_start|agent_done|step_start|step_done|loop_start|loop_done
      - type=done — terminal status when task finished

    Usage (JS):
      const es = new EventSource('/tasks/{id}/stream');
      es.onmessage = e => console.log(JSON.parse(e.data));
    """
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    if not _can_view_task(auth, row):
        raise HTTPException(404, "Task not found")

    async def generator():
        q = store.subscribe_task_stream(task_id)
        try:
            seen_logs = 0
            terminal_statuses = {TaskStatus.DONE.value, TaskStatus.FAILED.value}

            while True:
                try:
                    while True:
                        ev = await asyncio.wait_for(q.get(), timeout=0.12)
                        activity_payload = json.dumps({
                            "type": "activity",
                            "event_type": ev["event_type"],
                            "data": ev["data"],
                            "ts": ev["ts"],
                        })
                        yield f"data: {activity_payload}\n\n"
                except asyncio.TimeoutError:
                    pass

                logs = await store.get_logs(task_id)
                for log_entry in logs[seen_logs:]:
                    payload = json.dumps({
                        "type": "log",
                        "level": log_entry["level"],
                        "message": log_entry["message"],
                        "data": json.loads(log_entry.get("data_json", "{}")),
                        "ts": log_entry["logged_at"],
                    })
                    yield f"data: {payload}\n\n"
                seen_logs = len(logs)

                task_row = await store.get_task(task_id)
                if task_row:
                    status_payload = json.dumps({
                        "type": "status",
                        "status": task_row["status"],
                        "summary": task_row.get("summary", ""),
                        "eval_score": task_row.get("eval_score"),
                        "loop_iterations": task_row.get("loop_iterations", 0),
                    })
                    yield f"data: {status_payload}\n\n"

                    if task_row["status"] in terminal_statuses:
                        yield f"data: {json.dumps({'type': 'done', 'status': task_row['status']})}\n\n"
                        break

                await asyncio.sleep(1)
        finally:
            store.unsubscribe_task_stream(task_id, q)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/tasks/{task_id}/watchers")
async def task_stream_watchers(task_id: str, auth: dict = Depends(require_auth)):
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    if not _can_view_task(auth, row):
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, "watching": store.stream_subscriber_count(task_id)}


@app.post("/tasks/{task_id}/share")
async def create_task_share(task_id: str, request: Request, auth: dict = Depends(require_auth)):
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    if not _can_view_task(auth, row):
        raise HTTPException(404, "Task not found")
    uid = _require_authenticated_user(auth)
    token = secrets.token_urlsafe(24)
    expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    await store.insert_task_share(token, task_id, uid, expires_at)
    base = str(request.base_url).rstrip("/")
    return {"share_url": f"{base}/shared/{token}", "expires_at": expires_at, "token": token}


@app.get("/shared/{share_token}")
async def get_shared_task_view(share_token: str):
    shr = await store.get_task_share_row(share_token)
    if not shr:
        raise HTTPException(404, "Invalid or expired share link")
    task_id = shr["task_id"]
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")
    logs = await store.get_logs(task_id)
    return {
        "task": _row_to_response(row).model_dump(mode="json"),
        "logs": logs,
        "expires_at": shr["expires_at"],
    }


@app.get("/shared/{share_token}/stream")
async def shared_task_stream(share_token: str):
    shr = await store.get_task_share_row(share_token)
    if not shr:
        raise HTTPException(404, "Invalid or expired share link")
    task_id = shr["task_id"]
    row = await store.get_task(task_id)
    if row is None:
        raise HTTPException(404, "Task not found")

    async def generator():
        q = store.subscribe_task_stream(task_id)
        try:
            seen_logs = 0
            terminal_statuses = {TaskStatus.DONE.value, TaskStatus.FAILED.value}
            while True:
                try:
                    while True:
                        ev = await asyncio.wait_for(q.get(), timeout=0.12)
                        activity_payload = json.dumps({
                            "type": "activity",
                            "event_type": ev["event_type"],
                            "data": ev["data"],
                            "ts": ev["ts"],
                        })
                        yield f"data: {activity_payload}\n\n"
                except asyncio.TimeoutError:
                    pass
                logs = await store.get_logs(task_id)
                for log_entry in logs[seen_logs:]:
                    payload = json.dumps({
                        "type": "log",
                        "level": log_entry["level"],
                        "message": log_entry["message"],
                        "data": json.loads(log_entry.get("data_json", "{}")),
                        "ts": log_entry["logged_at"],
                    })
                    yield f"data: {payload}\n\n"
                seen_logs = len(logs)
                task_row = await store.get_task(task_id)
                if task_row:
                    status_payload = json.dumps({
                        "type": "status",
                        "status": task_row["status"],
                        "summary": task_row.get("summary", ""),
                        "eval_score": task_row.get("eval_score"),
                        "loop_iterations": task_row.get("loop_iterations", 0),
                    })
                    yield f"data: {status_payload}\n\n"
                    if task_row["status"] in terminal_statuses:
                        yield f"data: {json.dumps({'type': 'done', 'status': task_row['status']})}\n\n"
                        break
                await asyncio.sleep(1)
        finally:
            store.unsubscribe_task_stream(task_id, q)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ZapierWebhookBody(BaseModel):
    command: str = Field(..., min_length=3)
    user_email: str = ""
    data: dict = Field(default_factory=dict)


@app.post("/webhook/zapier")
async def webhook_zapier(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ZapierWebhookBody,
    _rate: None = Depends(execute_rate_limit),
):
    if not settings.zapier_webhook_secret:
        raise HTTPException(503, "Zapier webhook not configured (set ZAPIER_WEBHOOK_SECRET)")
    hdr = request.headers.get("x-zapier-secret") or request.headers.get("X-Zapier-Secret") or ""
    if not hdr or not secrets.compare_digest(hdr, settings.zapier_webhook_secret):
        raise HTTPException(401, "Invalid Zapier secret")
    uid = None
    if body.user_email:
        u = await store.get_user_by_email(body.user_email.strip().lower())
        if u:
            uid = u["user_id"]
    task_id = str(uuid.uuid4())
    ctx: dict = {"language": getattr(request.state, "lang", settings.default_language)}
    if uid:
        ctx["user_id"] = uid
    cmd = body.command.strip()
    await store.create_task(task_id, cmd, source="zapier", user_id=uid)
    background_tasks.add_task(
        orchestrator.run,
        task_id=task_id,
        command=cmd,
        context=ctx,
        dry_run=False,
    )
    base = str(request.base_url).rstrip("/")
    return {"task_id": task_id, "status": "queued", "status_url": f"{base}/tasks/{task_id}"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /tasks — list recent
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tasks")
async def list_tasks(
    limit: int = 20,
    status: Optional[str] = None,
    auth: dict = Depends(require_auth),
    _rate: None = Depends(rate_limit),
):
    uid, is_admin = _auth_user_filter(auth)
    rows = await store.list_tasks(limit=limit, status=status, user_id=uid, is_admin=is_admin)
    return {"count": len(rows), "tasks": [_row_to_response(r) for r in rows]}


# ─────────────────────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "Pantheon COO OS",
        "version": "2.0.0",
    }


@app.get("/ready")
async def ready_probe():
    qd = await store.get_queue_depth()
    if getattr(settings, "distributed_task_queue", False):
        from taskqueue.task_queue import get_task_queue

        qd = await get_task_queue().queue_depth()
    max_q = int(getattr(settings, "max_queue_depth", 100) or 100)
    if qd > max_q:
        raise HTTPException(503, "overloaded")
    return {"ok": True, "queue_depth": qd}


# ─────────────────────────────────────────────────────────────────────────────
# GET /stats
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stats")
async def stats(
    _auth: dict = Depends(require_auth),
    _rate: None = Depends(rate_limit),
):
    """Dashboard stats — task counts, success rate, COO memory size."""
    data = await store.get_stats()
    data["rate_limit"] = current_usage()
    return data


@app.get(
    "/report",
    tags=["Tasks"],
    summary="Performance report for dashboard",
    description="Aggregated task quality and activity for 24h / 7d / 30d windows.",
)
async def performance_report(
    period: str = "24h",
    _auth: dict = Depends(require_auth),
    _rate: None = Depends(rate_limit),
):
    """
    Structured performance summary for the dashboard Report tab.
    Query: period=24h | 7d | 30d
    """
    from performance_report import PERIOD_HOURS

    if period.lower() not in PERIOD_HOURS:
        raise HTTPException(400, "period must be one of: 24h, 7d, 30d")
    uid = _auth.get("user_id") or "anon"
    return await _cached_performance_report(period.lower(), uid)


@app.get(
    "/admin/analytics",
    tags=["Admin"],
    summary="Product analytics (admin)",
    description="Signups, tasks, success rate — cached when Redis enabled.",
)
async def admin_analytics(period: str = "7d", _auth=Depends(require_admin)):
    if period not in ("7d", "30d", "90d"):
        raise HTTPException(400, "period must be 7d|30d|90d")
    return await _cached_admin_analytics(period)


_admin_dashboard_cache: dict[str, Any] = {"t": 0.0, "data": None}


@app.get(
    "/admin/dashboard-stats",
    tags=["Admin"],
    summary="Founder dashboard snapshot",
    description="System, users, revenue, usage, activity feed. Cached ~60s.",
)
async def admin_dashboard_stats(_auth=Depends(require_admin)):
    import time as _time

    from memory.redis_client import cache_get, cache_set

    tnow = _time.monotonic()
    try:
        hit = await cache_get("admin:dashboard:stats")
        if hit:
            return json.loads(hit)
    except Exception:
        pass
    if tnow - float(_admin_dashboard_cache["t"]) < 60.0 and _admin_dashboard_cache["data"]:
        return _admin_dashboard_cache["data"]
    data = await store.get_admin_dashboard_stats()
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        mem_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
    except Exception:
        mem_mb = 0.0
    data["system"]["memory_mb"] = mem_mb
    data["system"]["uptime_seconds"] = int(_time.monotonic() - _start_time)
    qd = await store.get_queue_depth()
    data["system"]["queue_depth"] = qd
    _admin_dashboard_cache["t"] = tnow
    _admin_dashboard_cache["data"] = data
    try:
        await cache_set("admin:dashboard:stats", json.dumps(data, default=str), ttl=60)
    except Exception:
        pass
    return data


@app.get(
    "/admin/errors",
    tags=["Admin"],
    summary="Recent tracked errors",
    description="In-memory error buffer for operators (not a substitute for Sentry).",
)
async def admin_errors(limit: int = 50, _auth=Depends(require_admin)):
    from monitoring.error_tracker import get_tracker

    return {"errors": get_tracker().get_recent(limit)}


@app.get("/admin/analytics/export")
async def admin_analytics_export(period: str = "7d", _auth=Depends(require_admin)):
    from analytics import export_events_csv_for_period

    if period not in ("7d", "30d", "90d"):
        raise HTTPException(400, "period must be 7d|30d|90d")
    csv_text = await export_events_csv_for_period(period)
    return Response(content=csv_text, media_type="text/csv")


@app.get("/config/branding")
async def public_branding():
    import branding_runtime

    b = branding_runtime.get_public_branding()
    return {
        "name": b["name"],
        "logo_url": b["logo_url"],
        "primary_color": b["primary_color"],
        "support_email": b["support_email"],
        "powered_by": b["powered_by"],
    }


@app.get("/admin/branding")
async def admin_get_branding(_auth=Depends(require_admin)):
    import branding_runtime

    return branding_runtime.admin_get_branding()


@app.patch("/admin/branding")
async def admin_patch_branding(body: dict, _auth=Depends(require_admin)):
    import branding_runtime

    allowed = {k: body.get(k) for k in ("name", "logo_url", "primary_color", "support_email", "domain")}
    allowed = {k: v for k, v in allowed.items() if v is not None}
    return branding_runtime.update_branding(**allowed)


@app.get("/usage")
async def usage_endpoint(request: Request, auth: dict = Depends(require_auth)):
    lim = plan_limits_for_auth(auth)
    use = await current_usage_for_request(request)
    out: dict = {
        "plan": auth.get("plan", "free"),
        "rate_limits": {
            "global_rpm": lim["global_rpm"],
            "execute_rpm": lim["execute_rpm"],
            "current_global_usage": use["global"],
            "current_execute_usage": use["execute"],
        },
    }
    uid = auth.get("user_id")
    if uid:
        out["tasks_total"] = await store.count_tasks_for_user(uid)
    return out


@app.post("/affiliate/join")
async def affiliate_join(auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    row = await store.create_affiliate_for_user(uid)
    code = row["referral_code"]
    return {
        "affiliate_id": row["affiliate_id"],
        "referral_code": code,
        "referral_url": f"/affiliate/link?code={code}",
        "commission_pct": row.get("commission_pct", settings.default_affiliate_commission),
    }


@app.get("/affiliate/dashboard")
async def affiliate_dashboard(auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    aff = await store.get_affiliate_by_user(uid)
    if not aff:
        raise HTTPException(404, "Not an affiliate — POST /affiliate/join first")
    aid = aff["affiliate_id"]
    converted = await store.count_converted_referrals(aid)
    pending = await store.sum_pending_payout_amount(aid)
    recent = await store.list_recent_referrals_for_affiliate(aid, limit=15)
    return {
        "referral_code": aff["referral_code"],
        "referral_url": f"/affiliate/link?code={aff['referral_code']}",
        "total_referred": int(aff.get("total_referred") or 0),
        "total_converted": converted,
        "total_earned_inr": float(aff.get("total_earned") or 0.0),
        "pending_payout": pending,
        "recent_referrals": [
            {"email": r["referred_email"], "status": r["status"], "date": r["created_at"]}
            for r in recent
        ],
    }


@app.get("/affiliate/link")
async def affiliate_link_redirect(code: str = Query(..., min_length=4)):
    await store.record_affiliate_link_click(code)
    dest = (settings.white_label_domain or "").strip() or "/"
    if dest.startswith("http"):
        return RedirectResponse(url=dest, status_code=302)
    return RedirectResponse(url=dest, status_code=302)


@app.post("/affiliate/payout-request")
async def affiliate_payout_request(body: dict, auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    aff = await store.get_affiliate_by_user(uid)
    if not aff:
        raise HTTPException(404, "Not an affiliate")
    upi = (body.get("upi_id") or "").strip()
    amount = float(body.get("amount") or 0)
    if not upi or amount <= 0:
        raise HTTPException(400, "upi_id and positive amount required")
    return await store.insert_affiliate_payout_request(aff["affiliate_id"], uid, upi, amount)


@app.get("/admin/affiliates")
async def admin_list_affiliates(_auth=Depends(require_admin)):
    return {"affiliates": await store.list_affiliates_admin()}


# ─────────────────────────────────────────────────────────────────────────────
# Admin security dashboard APIs
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/admin/security-events")
async def admin_security_events(limit: int = 100, _auth=Depends(require_admin)):
    lim = max(1, min(int(limit), 200))
    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT id, event_type, ip_address, user_id, description, severity, created_at FROM security_events ORDER BY created_at DESC LIMIT ?",
            (lim,),
        ) as cur:
            rows = await cur.fetchall()
            return {"events": [dict(r) for r in rows]}


@app.get("/admin/blocked-ips")
async def admin_blocked_ips(_auth=Depends(require_admin)):
    return {"blocked": await store.list_blocked_ips(200)}


@app.delete("/admin/blocked-ips/{ip}")
async def admin_unblock_ip(ip: str, _auth=Depends(require_admin)):
    await store.unblock_ip(ip)
    await store.log_security_event("IP_UNBLOCKED", "", f"Unblocked {ip}", severity="medium")
    return {"ok": True, "ip": ip}


@app.get("/admin/security-score")
async def admin_security_score(_auth=Depends(require_admin)):
    failed = await store.count_security_events("FAILED_LOGIN", minutes=60)
    inj = await store.count_security_events("INJECTION_BLOCKED", minutes=60)
    blocked = len(await store.list_blocked_ips(200))
    score = 100
    score -= min(40, failed)
    score -= min(40, inj * 5)
    score -= min(20, blocked * 2)
    if getattr(settings, "strict_mode", False):
        score = max(0, score - 5)
    if getattr(settings, "execution_paused", False):
        score = max(0, score - 10)
    return {
        "score": max(0, min(100, int(score))),
        "signals": {"failed_logins_60m": failed, "injection_60m": inj, "blocked_ips": blocked},
    }


@app.get("/memory/semantic")
async def memory_semantic_search(
    query: str = "",
    limit: int = 5,
    auth: dict = Depends(require_auth),
):
    if auth.get("mode") == "public":
        raise HTTPException(401, "Authentication required")
    from memory.semantic_store import SemanticMemory

    sm = SemanticMemory(settings.db_path)
    rows = await sm.recall(query, "", min(limit, 50))
    return {"memories": rows}


@app.get("/memory/stats")
async def memory_stats_aggregate(auth: dict = Depends(require_auth)):
    if auth.get("mode") == "public":
        raise HTTPException(401, "Authentication required")
    return await store.semantic_memory_aggregate_stats()


@app.delete("/memory/semantic/{memory_id}")
async def memory_semantic_delete(memory_id: str, auth: dict = Depends(require_auth)):
    uid = auth.get("user_id")
    row = await store.get_semantic_memory(memory_id)
    if not row:
        raise HTTPException(404, "Memory not found")
    if auth.get("role") != "admin" and (row.get("owner_user_id") or "") != (uid or ""):
        raise HTTPException(403, "Forbidden")
    ok = await store.soft_delete_semantic_memory(memory_id)
    if not ok:
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@app.post("/webhooks")
async def create_webhook(body: dict, auth: dict = Depends(require_auth)):
    import secrets
    from urllib.parse import urlparse

    uid = _require_authenticated_user(auth)
    url = (body.get("url") or "").strip()
    if not url.startswith("https://"):
        raise HTTPException(400, "url must use https://")
    p = urlparse(url)
    if not p.netloc:
        raise HTTPException(400, "Invalid URL")
    events = body.get("events") or ["task.completed", "task.failed"]
    wid = str(uuid.uuid4())
    sec = secrets.token_hex(32)
    await store.insert_webhook_subscription(
        wid, uid, url, json.dumps(list(events)), sec
    )
    return {"webhook_id": wid, "secret": sec}


@app.get("/webhooks")
async def list_webhooks(auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    return {"webhooks": await store.list_webhooks_for_user(uid)}


@app.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    ok = await store.deactivate_webhook(webhook_id, uid)
    if not ok:
        raise HTTPException(404, "Webhook not found")
    return {"ok": True}


@app.get("/webhooks/{webhook_id}/logs")
async def webhook_logs(webhook_id: str, auth: dict = Depends(require_auth)):
    uid = _require_authenticated_user(auth)
    logs = await store.get_webhook_logs(webhook_id, uid)
    return {"logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# GET /memory/learnings
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/memory/learnings")
async def get_learnings(goal_type: str = "general", limit: int = 20):
    """
    Inspect what the COO has learned from past executions.
    This is the institutional memory that makes the COO smarter over time.
    """
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT goal_type, learning, score, created_at
               FROM learnings
               ORDER BY score DESC, created_at DESC
               LIMIT ?""",
            (limit,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return {"count": len(rows), "learnings": rows}






# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Projects API
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/projects", status_code=202)
async def create_project(
    req: Request,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(require_auth),
    _rate: None = Depends(rate_limit),
):
    """
    Create a long-running project from a high-level goal.
    The Decomposer Agent breaks it into sub-tasks, then executes them
    in dependency-respecting parallel waves.

    Body: { "name": "...", "goal": "...", "auto_start": true }
    """
    from models import ProjectRequest, ProjectResponse, ProjectStatus, SubTask
    import uuid as _uuid

    # Parse body manually since we need a custom model
    try:
        body = await req.json()
        project_req = ProjectRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request body: {e}")
    project_id = str(_uuid.uuid4())

    await store.create_project(project_id, project_req.name, project_req.goal)
    await store.log(project_id, f"Project created: {project_req.name}", "info")

    # Decompose in background
    background_tasks.add_task(
        _run_project_pipeline,
        project_id=project_id,
        req=project_req,
    )

    return {
        "project_id": project_id,
        "name": project_req.name,
        "goal": project_req.goal,
        "status": "decomposing",
        "message": "Decomposer Agent is breaking down the goal. Poll /projects/{id} for status.",
    }


@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get project status, progress, and sub-task task IDs."""
    import json as _json
    row = await store.get_project(project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    task_ids = _json.loads(row.get("task_ids") or "[]")
    logs = await store.get_logs(project_id)
    return {**row, "task_ids": task_ids, "log_count": len(logs)}


@app.get("/projects")
async def list_projects(status: Optional[str] = None):
    """List all projects, optionally filtered by status."""
    rows = await store.list_projects(status=status)
    import json as _json
    for r in rows:
        r["task_ids"] = _json.loads(r.get("task_ids") or "[]")
    return {"count": len(rows), "projects": rows}


@app.get("/projects/{project_id}/logs")
async def get_project_logs(project_id: str):
    """Execution logs for all sub-tasks in a project."""
    row = await store.get_project(project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    logs = await store.get_logs(project_id)
    return {"project_id": project_id, "count": len(logs), "logs": logs}


async def _run_project_pipeline(project_id: str, req) -> None:
    """Background: decompose → execute in parallel waves."""
    try:
        await store.log(project_id, "Decomposer Agent running...", "info")
        result = await decompose(req)

        await store.log(
            project_id,
            f"Decomposed into {len(result.sub_tasks)} sub-tasks: {result.summary}",
            "info",
        )

        if not result.sub_tasks:
            await store.log(project_id, "No sub-tasks generated. Check goal clarity.", "warning")
            return

        summary = await run_project(
            project_id=project_id,
            sub_tasks=result.sub_tasks,
            context=req.context,
        )
        await store.log(
            project_id,
            f"Project finished: {summary['done']} done, {summary['failed']} failed",
            "info" if summary["failed"] == 0 else "warning",
        )
    except Exception as e:
        await store.log(project_id, f"Project pipeline error: {e}", "error")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Daily Briefing API
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/briefing")
async def request_briefing(
    background_tasks: BackgroundTasks,
    body: dict = None,
    _auth: dict = Depends(require_auth),
):
    """
    Generate a COO daily briefing and optionally send it.
    Body (optional): { "recipients": ["email@..."], "whatsapp_numbers": ["+91..."], "hours": 24 }
    """
    body = body or {}
    recipients = body.get("recipients", [])
    whatsapp = body.get("whatsapp_numbers", [])
    hours = int(body.get("hours", 24))

    background_tasks.add_task(
        _generate_and_send_briefing, recipients, whatsapp, hours
    )
    return {"status": "generating", "message": "Briefing being generated. GET /briefing/latest for result."}


@app.get("/briefing/latest")
async def get_latest_briefing():
    """Return the most recently generated briefing."""
    try:
        async with get_pool().acquire() as db:
            async with db.execute(
                "SELECT * FROM briefings ORDER BY generated_at DESC LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "No briefings generated yet. POST /briefing to generate one.")
        return dict(row)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, "No briefings generated yet. POST /briefing to generate one.")


async def _generate_and_send_briefing(
    recipients: list[str], whatsapp: list[str], hours: int
) -> None:
    """Background: gather data → generate → store → send."""
    import json as _json

    try:
        metrics = await get_metrics(hours=hours)
        projects = await store.list_projects()
        recent_tasks = await store.list_tasks(limit=20)
        learnings = await store.get_learnings(limit=8)

        report = await generate_briefing(metrics, projects, recent_tasks, learnings)

        # Persist
        async with get_pool().acquire() as db:
            await db.execute(
                """INSERT INTO briefings
                   (generated_at, period_hours, headline, health, sections_json, recommendations_json, full_text)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    report.generated_at.isoformat(),
                    report.period_hours,
                    report.headline,
                    report.health,
                    _json.dumps([s.model_dump() for s in report.sections]),
                    _json.dumps(report.recommendations),
                    report.full_text,
                ),
            )
            await db.commit()

        # Distribute
        if recipients or whatsapp:
            await send_briefing(report, recipients, whatsapp)

        print(f"[Briefing] Done: {report.headline}")

    except Exception as e:
        print(f"[Briefing] Generation failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Self-Monitoring + Model Router API
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/monitor/metrics")
async def metrics(hours: int = 24):
    """
    COO performance metrics for the last N hours.
    Includes health status, score trends, failure rates, and alerts.
    """
    return await get_metrics(hours=hours)


@app.get("/monitor/model-status")
async def model_status():
    """Current state of the multi-model router (circuit breaker status)."""
    return router_status()


@app.get("/monitor/prompts/{agent_name}")
async def prompt_history(agent_name: str):
    """Version history of AI-optimized prompts for an agent."""
    return {"agent": agent_name, "history": await get_prompt_history(agent_name)}


@app.post("/monitor/optimize/{agent_name}/{goal_type}")
async def trigger_optimization(agent_name: str, goal_type: str):
    """
    Manually trigger prompt optimization for an agent + goal type.
    Normally runs automatically when score threshold is breached.
    """
    from agents.prompt_optimizer import optimize_prompt, save_prompt
    from monitor import _AGENT_PROMPTS

    base_prompt = _AGENT_PROMPTS.get(agent_name, "")
    if not base_prompt:
        raise HTTPException(400, f"No base prompt registered for agent '{agent_name}'")

    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT goal, eval_score, results_json FROM tasks WHERE goal_type=? AND status='failed' ORDER BY created_at DESC LIMIT 5",
            (goal_type,),
        ) as cur:
            failures = [dict(r) for r in await cur.fetchall()]

    result = await optimize_prompt(
        agent_name=agent_name, goal_type=goal_type,
        current_prompt=base_prompt, failure_examples=failures, improvement_hints=[]
    )
    if not result:
        raise HTTPException(500, "Optimizer could not produce a valid prompt. Check logs.")

    async with get_pool().acquire() as db:
        async with db.execute(
            "SELECT MAX(version) as v FROM agent_prompts WHERE agent_name=? AND goal_type=?",
            (agent_name, goal_type),
        ) as cur:
            row = await cur.fetchone()
            ver = (row[0] or 0) + 1

    await save_prompt(agent_name, goal_type, result["new_prompt"], ver, notes="Manual trigger")
    return {"optimized": True, "version": ver, "changes": result["changes_made"]}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Tool Builder API
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tools/custom")
async def list_custom_tools():
    """List all tools built by the Tool Builder Agent."""
    from tools.registry import list_custom_tools as _list
    db_tools = await store.get_custom_tools()
    live_tools = _list()
    return {
        "count": len(db_tools),
        "live_in_registry": live_tools,
        "tools": db_tools,
    }


@app.post("/tools/custom/reload")
async def reload_custom_tools():
    """Hot-reload all custom tools from disk without restarting the server."""
    from tools.registry import load_all_custom_tools
    count = await load_all_custom_tools()
    return {"reloaded": count}


@app.get("/tools/patterns")
async def get_patterns():
    """Show repeated step patterns the COO has detected."""
    async with get_pool().acquire() as db:
        async with db.execute(
            """SELECT step_sequence, goal_type, COUNT(*) as count
               FROM task_patterns GROUP BY step_sequence
               ORDER BY count DESC LIMIT 20"""
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    from pattern_detector import describe_pattern
    for r in rows:
        r["description"] = describe_pattern(r["step_sequence"])
        del r["step_sequence"]
    return {"patterns": rows}


# ─────────────────────────────────────────────────────────────────────────────
# Terminal access (dashboard tab)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/terminal/run")
async def terminal_run(body: TerminalRunBody, auth: dict = Depends(require_auth)) -> dict[str, Any]:
    if auth.get("mode") == "none":
        raise HTTPException(401, "Authentication required")
    cmd = (body.command or "").strip()
    _terminal_validate_command(cmd)
    from tools import terminal as term_tool
    res = await term_tool.execute(
        "run_command",
        {
            "command": cmd,
            "cwd": body.cwd,
            "timeout": int(body.timeout or settings.agent_timeout_seconds or 90),
        },
    )
    out = (res.get("stdout") or "").strip()
    err = (res.get("stderr") or "").strip()
    combined = "\n".join([x for x in [out, err] if x])
    return {
        "ok": bool(res.get("success")),
        "exit_code": int(res.get("exit_code", -1)),
        "stdout": out,
        "stderr": err,
        "output": combined,
    }


@app.post("/terminal/run/stream")
async def terminal_run_stream(
    body: TerminalRunBody,
    request: Request,
    auth: dict = Depends(require_auth),
) -> StreamingResponse:
    """
    Streams command output via SSE (best-effort).
    """
    if auth.get("mode") == "none":
        raise HTTPException(401, "Authentication required")
    cmd = (body.command or "").strip()
    _terminal_validate_command(cmd)
    timeout = int(body.timeout or settings.agent_timeout_seconds or 90)

    async def _gen():
        yield f"event: start\ndata: {json.dumps({'command': cmd})}\n\n"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=body.cwd,
            )
            try:
                assert proc.stdout is not None
                while True:
                    if await request.is_disconnected():
                        proc.kill()
                        break
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
                    if not line:
                        break
                    yield f"event: output\ndata: {json.dumps({'line': line.decode(errors='replace')})}\n\n"
            except asyncio.TimeoutError:
                proc.kill()
                yield f"event: error\ndata: {json.dumps({'error': f'Timed out after {timeout}s'})}\n\n"
            rc = await proc.wait()
            yield f"event: done\ndata: {json.dumps({'exit_code': rc})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Self-update (COO improves itself) — requires confirmation before push
# ─────────────────────────────────────────────────────────────────────────────

class SelfUpdateBody(BaseModel):
    instruction: str = Field(..., min_length=3, max_length=8000)


class SelfUpdateConfirmBody(BaseModel):
    token: str = Field(..., min_length=8, max_length=200)
    decision: str = Field(..., min_length=2, max_length=10)  # "haan" | "nahi"


@app.post("/self-update")
async def self_update(body: SelfUpdateBody, auth: dict = Depends(require_auth)) -> dict[str, Any]:
    if auth.get("mode") == "none":
        raise HTTPException(401, "Authentication required")
    from agents.self_update_agent import SelfUpdateAgent

    repo = getattr(settings, "self_repo", "") or "pantheonmed/pantheon-coo"
    agent = SelfUpdateAgent()
    out = await agent.prepare_self_update(repo=repo, instruction=body.instruction)
    # Always return required shape
    return {
        "plan": out.get("plan") or [],
        "files_affected": out.get("files_affected") or [],
        "estimated_time": out.get("estimated_time") or "unknown",
        "confirmation_needed": bool(out.get("confirmation_needed")),
        **{k: v for k, v in out.items() if k not in ("plan", "files_affected", "estimated_time", "confirmation_needed")},
    }


@app.post("/self-update/confirm")
async def self_update_confirm(body: SelfUpdateConfirmBody, auth: dict = Depends(require_auth)) -> dict[str, Any]:
    if auth.get("mode") == "none":
        raise HTTPException(401, "Authentication required")
    from agents.self_update_agent import SelfUpdateAgent

    agent = SelfUpdateAgent()
    return await agent.confirm_and_push(body.token, body.decision)

# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_response(row: dict) -> CommandResponse:
    # Parse plan
    plan = None
    try:
        plan_data = json.loads(row.get("plan_json") or "{}")
        if plan_data.get("steps") is not None:
            plan = PlanningOutput(**plan_data)
    except Exception:
        pass

    # Parse results
    results = []
    try:
        raw = json.loads(row.get("results_json") or "[]")
        results = [StepResult(**r) for r in raw]
    except Exception:
        pass

    sugg: list[str] = []
    try:
        sugg = json.loads(row.get("suggestions_json") or "[]")
        if not isinstance(sugg, list):
            sugg = []
    except Exception:
        sugg = []

    return CommandResponse(
        task_id=row["task_id"],
        status=TaskStatus(row["status"]),
        goal=row.get("goal") or row["command"],
        loop_iterations=row.get("loop_iterations", 0),
        evaluation_score=row.get("eval_score"),
        summary=row.get("summary", ""),
        plan=plan,
        results=results,
        error=row.get("error"),
        suggestions=[str(x) for x in sugg],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row.get("completed_at") else None
        ),
    )
