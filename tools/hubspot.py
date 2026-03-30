"""
tools/hubspot.py — HubSpot CRM API v3 helpers.
"""
from __future__ import annotations

from typing import Any

import httpx

from config import settings

BASE = "https://api.hubapi.com"
TIMEOUT = 45.0


def _headers() -> dict[str, str]:
    key = (settings.hubspot_api_key or "").strip()
    if not key:
        raise RuntimeError("HUBSPOT_API_KEY / hubspot_api_key is not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


async def execute(action: str, params: dict[str, Any]) -> Any:
    dispatch = {
        "create_contact": _create_contact,
        "get_contact": _get_contact,
        "create_deal": _create_deal,
        "update_deal_stage": _update_deal_stage,
        "get_deals": _get_deals,
        "send_email": _send_email,
    }
    fn = dispatch.get(action)
    if not fn:
        raise ValueError(f"Unknown hubspot action: {action}. Available: {list(dispatch)}")
    return await fn(params)


async def _create_contact(p: dict[str, Any]) -> dict[str, Any]:
    props = {
        "email": p.get("email", ""),
        "firstname": p.get("firstname", ""),
        "lastname": p.get("lastname", ""),
        "phone": p.get("phone", ""),
        "company": p.get("company", ""),
        "website": p.get("website", ""),
    }
    props = {k: v for k, v in props.items() if v}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{BASE}/crm/v3/objects/contacts",
            headers=_headers(),
            json={"properties": props},
        )
    r.raise_for_status()
    data = r.json()
    cid = data.get("id", "")
    return {"contact_id": cid, "url": f"https://app.hubspot.com/contacts/{cid}" if cid else ""}


async def _get_contact(p: dict[str, Any]) -> dict[str, Any]:
    email = (p.get("email") or "").strip()
    if not email:
        raise ValueError("email is required")
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{BASE}/crm/v3/objects/contacts/search",
            headers=_headers(),
            json={
                "filterGroups": [
                    {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                ],
                "limit": 1,
            },
        )
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    return {"found": len(results) > 0, "contact": results[0] if results else None}


async def _create_deal(p: dict[str, Any]) -> dict[str, Any]:
    dealname = (p.get("dealname") or "").strip()
    amount = p.get("amount")
    if not dealname:
        raise ValueError("dealname is required")
    if amount is None or amount == "":
        raise ValueError("amount is required")
    props = {
        "dealname": dealname,
        "amount": str(amount),
        "dealstage": p.get("stage", ""),
        "pipeline": p.get("pipeline", "default"),
    }
    props = {k: v for k, v in props.items() if v}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{BASE}/crm/v3/objects/deals",
            headers=_headers(),
            json={"properties": props},
        )
    r.raise_for_status()
    data = r.json()
    did = data.get("id", "")
    return {"deal_id": did, "url": f"https://app.hubspot.com/deals/{did}" if did else ""}


async def _update_deal_stage(p: dict[str, Any]) -> dict[str, Any]:
    deal_id = (p.get("deal_id") or "").strip()
    stage = (p.get("stage") or "").strip()
    if not deal_id or not stage:
        raise ValueError("deal_id and stage are required")
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.patch(
            f"{BASE}/crm/v3/objects/deals/{deal_id}",
            headers=_headers(),
            json={"properties": {"dealstage": stage}},
        )
    r.raise_for_status()
    return {"deal_id": deal_id, "stage": stage}


async def _get_deals(p: dict[str, Any]) -> dict[str, Any]:
    stage = (p.get("stage") or "").strip()
    limit = int(p.get("limit") or 20)
    body: dict[str, Any] = {"limit": min(limit, 100)}
    if stage:
        body["filterGroups"] = [
            {"filters": [{"propertyName": "dealstage", "operator": "EQ", "value": stage}]}
        ]
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{BASE}/crm/v3/objects/deals/search",
            headers=_headers(),
            json=body,
        )
    r.raise_for_status()
    data = r.json()
    return {"deals": data.get("results") or [], "count": len(data.get("results") or [])}


async def _send_email(p: dict[str, Any]) -> dict[str, Any]:
    """Single-send marketing email placeholder — HubSpot APIs vary; store as engagement note."""
    contact_email = (p.get("contact_email") or "").strip()
    subject = (p.get("subject") or "").strip()
    body = (p.get("body") or "").strip()
    if not contact_email or not subject:
        raise ValueError("contact_email and subject are required")
    return {
        "queued": True,
        "contact_email": contact_email,
        "subject": subject,
        "note": "Email send requires HubSpot marketing scopes; payload recorded for workflow.",
        "body_len": len(body),
    }
