"""
tools/zoho_crm.py — Zoho CRM REST API v2 (India: zohoapis.in).
"""
from __future__ import annotations

from typing import Any

import httpx

from config import settings

BASE = "https://www.zohoapis.in/crm/v2"


def _headers() -> dict[str, str]:
    if not settings.zoho_access_token:
        raise ValueError("ZOHO_ACCESS_TOKEN is not configured.")
    return {
        "Authorization": f"Zoho-oauthtoken {settings.zoho_access_token}",
        "Content-Type": "application/json",
    }


async def _create_lead(p: dict[str, Any]) -> dict[str, Any]:
    first = str(p.get("first_name", ""))
    last = str(p.get("last_name", ""))
    payload = {
        "data": [
            {
                "First_Name": first,
                "Last_Name": last or "-",
                "Email": str(p.get("email", "")),
                "Phone": str(p.get("phone", "")),
                "Company": str(p.get("company", "")),
                "Lead_Source": str(p.get("source") or "Pantheon COO"),
            }
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/Leads", json=payload, headers=_headers())
        r.raise_for_status()
        data = r.json()
    det = (data.get("data") or [{}])[0]
    lid = det.get("details", {}).get("id") or det.get("id", "")
    return {"lead_id": lid, "url": f"https://crm.zoho.in/crm/tab/Leads/{lid}" if lid else ""}


async def _get_lead(p: dict[str, Any]) -> dict[str, Any]:
    lead_id = str(p.get("lead_id", "")).strip()
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(f"{BASE}/Leads/{lead_id}", headers=_headers())
        r.raise_for_status()
        data = r.json()
    rows = data.get("data") or []
    return rows[0] if rows else {}


async def _search_leads(p: dict[str, Any]) -> list[dict[str, Any]]:
    q = str(p.get("query", "")).replace('"', '\\"')
    limit = min(int(p.get("limit") or 10), 50)
    criteria = f'(Company:contains:{q})or(Last_Name:contains:{q})or(Email:contains:{q})'
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(
            f"{BASE}/Leads/search",
            params={"criteria": criteria, "per_page": limit},
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
    return list(data.get("data") or [])


async def _create_contact(p: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "data": [
            {
                "First_Name": str(p.get("first_name", "")),
                "Last_Name": str(p.get("last_name", "")) or "-",
                "Email": str(p.get("email", "")),
                "Phone": str(p.get("phone", "")),
                "Account_Name": {"name": str(p.get("account_name", ""))},
            }
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/Contacts", json=payload, headers=_headers())
        r.raise_for_status()
        data = r.json()
    det = (data.get("data") or [{}])[0]
    cid = det.get("details", {}).get("id") or det.get("id", "")
    return {"contact_id": cid}


async def _create_deal(p: dict[str, Any]) -> dict[str, Any]:
    if "amount" not in p:
        raise ValueError("amount is required for create_deal.")
    amount = float(p.get("amount") or 0)
    stage = str(p.get("stage") or "")
    if not stage:
        raise ValueError("stage is required for create_deal.")
    payload = {
        "data": [
            {
                "Deal_Name": str(p.get("deal_name", "")),
                "Account_Name": str(p.get("account_name", "")),
                "Amount": amount,
                "Stage": stage,
                "Closing_Date": str(p.get("close_date", "")),
            }
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{BASE}/Deals", json=payload, headers=_headers())
        r.raise_for_status()
        data = r.json()
    det = (data.get("data") or [{}])[0]
    did = det.get("details", {}).get("id") or det.get("id", "")
    return {"deal_id": did}


async def _update_lead_status(p: dict[str, Any]) -> dict[str, Any]:
    lead_id = str(p.get("lead_id", "")).strip()
    status = str(p.get("status", ""))
    notes = str(p.get("notes") or "")
    payload = {"data": [{"id": lead_id, "Lead_Status": status, "Description": notes}]}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.put(f"{BASE}/Leads", json=payload, headers=_headers())
        r.raise_for_status()
    return {"lead_id": lead_id, "status": status, "updated": True}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "create_lead": _create_lead,
        "get_lead": _get_lead,
        "search_leads": _search_leads,
        "create_contact": _create_contact,
        "create_deal": _create_deal,
        "update_lead_status": _update_lead_status,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown zoho_crm action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
