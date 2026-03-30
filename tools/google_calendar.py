"""
tools/google_calendar.py — Google Calendar API v3 via service account (httpx).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from config import settings

BASE = "https://www.googleapis.com/calendar/v3"

_cal_creds: service_account.Credentials | None = None


def _parse_sa() -> dict[str, Any]:
    raw = (settings.google_service_account_json or "").strip()
    if not raw:
        raise ValueError("Set GOOGLE_SERVICE_ACCOUNT_JSON for Calendar API.")
    if raw.startswith("{"):
        return json.loads(raw)
    with open(raw, encoding="utf-8") as f:
        return json.load(f)


def _credentials() -> service_account.Credentials:
    global _cal_creds
    scopes = [settings.google_calendar_scope]
    if _cal_creds is None:
        _cal_creds = service_account.Credentials.from_service_account_info(_parse_sa(), scopes=scopes)
    if not _cal_creds.valid:
        _cal_creds.refresh(Request())
    return _cal_creds


async def _token() -> str:
    return await asyncio.to_thread(lambda: _credentials().token)  # type: ignore[union-attr]


async def _create_event(p: dict[str, Any]) -> dict[str, Any]:
    cal_id = str(p.get("calendar_id") or "primary")
    body: dict[str, Any] = {
        "summary": str(p.get("title", "")),
        "description": str(p.get("description", "")),
        "location": str(p.get("location", "")),
        "start": {"dateTime": str(p.get("start_datetime")), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": str(p.get("end_datetime")), "timeZone": "Asia/Kolkata"},
    }
    atts = p.get("attendees") or []
    if atts:
        body["attendees"] = [{"email": str(e)} for e in atts]
    params = {}
    if bool(p.get("meet_link", False)):
        body["conferenceData"] = {
            "createRequest": {"requestId": f"pantheon-{int(datetime.now(timezone.utc).timestamp())}"}
        }
        params["conferenceDataVersion"] = "1"
    headers = {"Authorization": f"Bearer {await _token()}", "Content-Type": "application/json"}
    url = f"{BASE}/calendars/{cal_id}/events"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=body, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
    meet = ""
    if data.get("conferenceData", {}).get("entryPoints"):
        for ep in data["conferenceData"]["entryPoints"]:
            if ep.get("entryPointType") == "video":
                meet = ep.get("uri", "")
                break
    return {"event_id": data.get("id", ""), "url": data.get("htmlLink", ""), "meet_link": meet}


async def _get_events(p: dict[str, Any]) -> list[dict[str, Any]]:
    cal_id = str(p.get("calendar_id") or "primary")
    start = str(p.get("start_date", ""))
    end = str(p.get("end_date", ""))
    headers = {"Authorization": f"Bearer {await _token()}"}
    params = {"timeMin": start, "timeMax": end, "singleEvents": "true"}
    url = f"{BASE}/calendars/{cal_id}/events"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
    out: list[dict[str, Any]] = []
    for ev in data.get("items", []):
        out.append(
            {
                "title": ev.get("summary", ""),
                "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date", ""),
                "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date", ""),
                "attendees": [a.get("email", "") for a in (ev.get("attendees") or [])],
            }
        )
    return out


async def _update_event(p: dict[str, Any]) -> dict[str, Any]:
    event_id = str(p.get("event_id", ""))
    cal_id = str(p.get("calendar_id") or "primary")
    updates = dict(p.get("updates") or {})
    headers = {"Authorization": f"Bearer {await _token()}", "Content-Type": "application/json"}
    url = f"{BASE}/calendars/{cal_id}/events/{event_id}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.patch(url, json=updates, headers=headers)
        r.raise_for_status()
        data = r.json()
    return {"event_id": data.get("id", ""), "updated": True}


async def _delete_event(p: dict[str, Any]) -> dict[str, Any]:
    event_id = str(p.get("event_id", ""))
    cal_id = str(p.get("calendar_id") or "primary")
    headers = {"Authorization": f"Bearer {await _token()}"}
    url = f"{BASE}/calendars/{cal_id}/events/{event_id}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.delete(url, headers=headers)
        r.raise_for_status()
    return {"deleted": event_id}


async def _find_free_slot(p: dict[str, Any]) -> list[dict[str, Any]]:
    duration = int(p.get("duration_minutes") or 30)
    dates = p.get("preferred_dates") or []
    wh = p.get("working_hours") or {"start": "09:00", "end": "18:00"}
    start_h, start_m = map(int, str(wh.get("start", "09:00")).split(":"))
    end_h, end_m = map(int, str(wh.get("end", "18:00")).split(":"))
    slots: list[dict[str, Any]] = []
    for d in dates[:14]:
        ds = str(d).strip()
        try:
            day = datetime.fromisoformat(ds.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        t = datetime.combine(day, datetime.min.time().replace(hour=start_h, minute=start_m))
        end_day = datetime.combine(day, datetime.min.time().replace(hour=end_h, minute=end_m))
        while t + timedelta(minutes=duration) <= end_day:
            e = t + timedelta(minutes=duration)
            slots.append({"start": t.isoformat(), "end": e.isoformat()})
            t += timedelta(minutes=max(duration, 30))
        if len(slots) >= 20:
            break
    return slots[:20]


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "create_event": _create_event,
        "get_events": _get_events,
        "update_event": _update_event,
        "delete_event": _delete_event,
        "find_free_slot": _find_free_slot,
    }
    fn = dispatch.get(act)
    if fn is None:
        raise ValueError(f"Unknown google_calendar action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)
