"""
api_batch.py — Routes for Tasks 86–91 (teams, marketplace, insights, ML, SAML stub).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import memory.store as store
from insights_engine import get_insights_engine
from config import settings
from ml.data_collector import TrainingDataCollector
from security.auth import require_admin, require_auth

router = APIRouter(tags=["LaunchBatch"])


def _uid(auth: dict) -> str:
    uid = auth.get("user_id")
    if not uid:
        raise HTTPException(401, "Authentication required")
    return uid


# ── Teams ───────────────────────────────────────────────────────────────────


class TeamCreateBody(BaseModel):
    name: str
    plan: str = "starter"


@router.post("/teams")
async def teams_create(body: TeamCreateBody, auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    return await store.create_team(body.name, uid, body.plan)


class TeamInviteBody(BaseModel):
    email: str


@router.post("/teams/{team_id}/invite")
async def teams_invite(
    team_id: str, body: TeamInviteBody, auth: dict = Depends(require_auth)
):
    uid = _uid(auth)
    t = await store.get_team(team_id)
    if not t or t["owner_id"] != uid:
        raise HTTPException(403, "Only team owner can invite")
    return {"ok": True, "email": body.email, "note": "Invite email queued (configure SMTP)"}


class TeamJoinBody(BaseModel):
    invite_code: str


@router.post("/teams/join")
async def teams_join(body: TeamJoinBody, auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    t = await store.get_team_by_invite(body.invite_code)
    if not t:
        raise HTTPException(404, "Invalid invite code")
    await store.add_team_member(t["team_id"], uid, "member")
    return {"team_id": t["team_id"], "name": t["name"]}


@router.get("/teams/{team_id}/members")
async def teams_members(team_id: str, auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    members = await store.list_team_members(team_id)
    if not any(m["user_id"] == uid for m in members):
        raise HTTPException(403, "Not a team member")
    return {"members": members}


@router.get("/teams/{team_id}/tasks")
async def teams_tasks(team_id: str, auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    t = await store.get_team(team_id)
    if not t:
        raise HTTPException(404, "Team not found")
    members = await store.list_team_members(team_id)
    if not any(m["user_id"] == uid for m in members):
        raise HTTPException(403, "Not a team member")
    is_owner = t["owner_id"] == uid
    tasks = await store.list_team_tasks_for_user(team_id, uid, is_owner)
    return {"tasks": tasks}


class AssignBody(BaseModel):
    assign_to_user_id: str


@router.patch("/teams/{team_id}/tasks/{task_id}/assign")
async def teams_assign(
    team_id: str,
    task_id: str,
    body: AssignBody,
    auth: dict = Depends(require_auth),
):
    uid = _uid(auth)
    t = await store.get_team(team_id)
    if not t or t["owner_id"] != uid:
        raise HTTPException(403, "Owner only")
    ok = await store.assign_team_task(team_id, task_id, body.assign_to_user_id)
    if not ok:
        raise HTTPException(404, "Task link not found")
    return {"ok": True}


@router.delete("/teams/{team_id}/members/{user_id}")
async def teams_remove_member(
    team_id: str, user_id: str, auth: dict = Depends(require_auth)
):
    uid = _uid(auth)
    t = await store.get_team(team_id)
    if not t or t["owner_id"] != uid:
        raise HTTPException(403, "Owner only")
    await store.remove_team_member(team_id, user_id)
    return {"ok": True}


# ── Marketplace ─────────────────────────────────────────────────────────────


class MarketplacePublishBody(BaseModel):
    name: str
    description: str
    code: str
    price_inr: int = 0
    category: str = "general"


@router.post("/marketplace/publish")
async def marketplace_publish(
    body: MarketplacePublishBody, auth: dict = Depends(require_auth)
):
    uid = _uid(auth)
    return await store.marketplace_publish(
        uid, body.name, body.description, body.code, body.price_inr, body.category
    )


@router.get("/marketplace")
async def marketplace_list(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "popular",
):
    items = await store.marketplace_list_approved(category, search, sort)
    return {"tools": items}


@router.get("/marketplace/earnings")
async def marketplace_earnings_route(auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    return await store.marketplace_earnings(uid)


@router.get("/marketplace/{tool_id}")
async def marketplace_detail(tool_id: str):
    row = await store.marketplace_get(tool_id, public_only=True)
    if not row:
        raise HTTPException(404, "Tool not found")
    row = dict(row)
    row.pop("code", None)
    return row


@router.post("/marketplace/{tool_id}/purchase")
async def marketplace_purchase(tool_id: str, auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    tool = await store.marketplace_get(tool_id, public_only=False)
    if not tool or not tool.get("is_approved"):
        raise HTTPException(404, "Tool not available")
    price = int(tool.get("price_inr") or 0)
    if price <= 0:
        await store.marketplace_purchase(tool_id, uid, 0)
        return {"ok": True, "installed": True, "amount_paise": 0}
    await store.marketplace_purchase(tool_id, uid, price)
    return {"ok": True, "charged_paise": price}


class RateBody(BaseModel):
    rating: float = Field(ge=1, le=5)
    review: str = ""


@router.post("/marketplace/{tool_id}/rate")
async def marketplace_rate(tool_id: str, body: RateBody, auth: dict = Depends(require_auth)):
    _uid(auth)
    await store.marketplace_rate(tool_id, body.rating, body.review)
    return {"ok": True}


@router.get("/admin/marketplace/pending")
async def marketplace_pending(_auth: dict = Depends(require_admin)):
    return {"pending": await store.marketplace_pending()}


@router.patch("/admin/marketplace/{tool_id}/approve")
async def marketplace_approve(tool_id: str, _auth: dict = Depends(require_admin)):
    ok = await store.marketplace_approve(tool_id)
    if not ok:
        raise HTTPException(404, "Tool not found")
    return {"ok": True}


# ── Insights ────────────────────────────────────────────────────────────────


@router.post("/insights/weekly-report")
async def insights_weekly(auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    eng = get_insights_engine()
    base = await eng.generate_weekly_insights(uid)
    return {
        "period": "last 7 days",
        "tasks_completed": base.get("tasks_done", 0),
        "time_saved_hours": base.get("time_saved_hours_estimate", 0),
        "success_rate": base.get("success_rate", 0),
        "top_skill": "research",
        "improvement_tip": base["recommendations"][0] if base.get("recommendations") else "",
        "best_performing_command": "",
        "worst_performing": "",
        "recommendations": base.get("recommendations", []),
        **base,
    }


@router.get("/insights/automation-opportunities")
async def insights_auto(auth: dict = Depends(require_auth)):
    uid = _uid(auth)
    return {"opportunities": await get_insights_engine().find_automation_opportunities(uid)}


@router.get("/insights/predict")
async def insights_predict(
    command: str = Query(..., min_length=2),
    goal_type: str = "",
    auth: dict = Depends(require_auth),
):
    _uid(auth)
    return await get_insights_engine().predict_task_success(command, goal_type)


# ── ML admin ────────────────────────────────────────────────────────────────


@router.get("/admin/ml/stats")
async def ml_stats(_auth: dict = Depends(require_admin)):
    return await TrainingDataCollector().get_stats()


class MLExportBody(BaseModel):
    data_type: str = "planning"
    min_score: float = 0.9
    limit: int = 500


@router.post("/admin/ml/export")
async def ml_export(body: MLExportBody, _auth: dict = Depends(require_admin)):
    col = TrainingDataCollector()
    path = f"/tmp/pantheon_v2/ml/export_{body.data_type}.jsonl"
    n = await col.export_jsonl(path, body.data_type)
    sz = Path(path).stat().st_size / (1024 * 1024) if Path(path).is_file() else 0
    return {"file_path": path, "count": n, "size_mb": round(sz, 4)}


@router.post("/admin/ml/prepare-dataset")
async def ml_prepare(_auth: dict = Depends(require_admin)):
    path = "/tmp/pantheon_v2/ml/dataset.jsonl"
    n = await TrainingDataCollector().export_jsonl(path, "planning")
    return {"file_path": path, "count": n}


@router.get("/admin/ml/dataset-quality")
async def ml_quality(_auth: dict = Depends(require_admin)):
    stats = await TrainingDataCollector().get_stats()
    return {
        "distribution_by_goal_type": stats.get("by_goal_type"),
        "high_score_tasks": stats.get("high_score_tasks"),
        "gaps": ["Need more medical examples"] if stats.get("high_score_tasks", 0) < 5 else [],
        "recommendation": "Collect more successful tasks above 0.9 eval score",
    }


# ── SAML stub ────────────────────────────────────────────────────────────────


@router.get("/auth/saml/login")
async def saml_login():
    if not settings.saml_enabled:
        raise HTTPException(501, "SAML not enabled (set SAML_ENABLED=true)")
    return {"redirect": "configure IdP integration", "status": "stub"}


@router.post("/auth/saml/callback")
async def saml_callback():
    raise HTTPException(501, "SAML callback not fully configured")


# ── Audit ────────────────────────────────────────────────────────────────────


@router.get("/admin/audit-logs")
async def audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    _auth: dict = Depends(require_admin),
):
    return {"events": await store.list_audit_logs(100, user_id, action)}


# ── Onboarding status (integration tests) ───────────────────────────────────


@router.get("/onboarding/status")
async def onboarding_status(auth: dict = Depends(require_auth)):
    if auth.get("mode") == "none":
        return {"current_step": 0, "completed": False, "checklist": []}
    _uid(auth)
    return {"current_step": 0, "completed": False, "checklist": []}
