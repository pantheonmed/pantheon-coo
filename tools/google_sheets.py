"""
tools/google_sheets.py — Google Sheets API v4 via httpx.

Auth: service account JSON (path or inline string) via google-auth credentials;
all spreadsheet HTTP calls use httpx.AsyncClient.

Actions:
  read_sheet   → {spreadsheet_id, range}
  write_sheet  → {spreadsheet_id, range, values: list[list]}
  append_rows  → {spreadsheet_id, values: list[list], range?}  (default range Sheet1!A1)
  create_sheet → {title}
  clear_range  → {spreadsheet_id, range}
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from config import settings
from security.sandbox import validate_spreadsheet_id

BASE = "https://sheets.googleapis.com/v4/spreadsheets"
TIMEOUT = 60.0

_sa_credentials: service_account.Credentials | None = None


def _parse_service_account() -> dict[str, Any]:
    raw = (settings.google_service_account_json or "").strip()
    if not raw:
        raise ValueError(
            "Google Sheets is not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
            "(path to service account JSON file or JSON string)."
        )
    if raw.startswith("{"):
        return json.loads(raw)
    with open(raw, encoding="utf-8") as f:
        return json.load(f)


def _credentials() -> service_account.Credentials:
    global _sa_credentials
    if _sa_credentials is None:
        info = _parse_service_account()
        _sa_credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=[settings.google_sheets_scope],
        )
    if not _sa_credentials.valid:
        _sa_credentials.refresh(Request())
    return _sa_credentials


def _access_token_sync() -> str:
    return _credentials().token  # type: ignore[union-attr]


def _encode_range(rng: str) -> str:
    return quote(rng, safe="")


async def _auth_headers() -> dict[str, str]:
    token = await asyncio.to_thread(_access_token_sync)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _fmt_response(r: httpx.Response) -> dict[str, Any]:
    body: Any = r.text
    try:
        body = r.json()
    except Exception:
        pass
    return {"status_code": r.status_code, "ok": r.is_success, "body": body}


async def _request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    headers = await _auth_headers()
    extra = kwargs.pop("headers", {})
    headers.update(extra)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.request(method, url, headers=headers, **kwargs)
    return _fmt_response(r)


async def execute(action: str, params: dict[str, Any]) -> Any:
    dispatch = {
        "read_sheet": _read_sheet,
        "write_sheet": _write_sheet,
        "append_rows": _append_rows,
        "create_sheet": _create_sheet,
        "clear_range": _clear_range,
    }
    fn = dispatch.get(action)
    if fn is None:
        raise ValueError(
            f"Unknown Google Sheets action: '{action}'. Available: {list(dispatch)}"
        )
    return await fn(params)


async def _read_sheet(p: dict[str, Any]) -> dict[str, Any]:
    sid = p.get("spreadsheet_id", "")
    rng = p.get("range", "")
    validate_spreadsheet_id(sid)
    if not rng or not str(rng).strip():
        raise ValueError("read_sheet requires 'range' (e.g. Sheet1!A1:D10)")
    url = f"{BASE}/{sid}/values/{_encode_range(str(rng).strip())}"
    return await _request("GET", url)


async def _write_sheet(p: dict[str, Any]) -> dict[str, Any]:
    sid = p.get("spreadsheet_id", "")
    rng = p.get("range", "")
    values = p.get("values")
    validate_spreadsheet_id(sid)
    if not rng or not str(rng).strip():
        raise ValueError("write_sheet requires 'range'")
    if values is None:
        raise ValueError("write_sheet requires 'values' as list of rows")
    url = f"{BASE}/{sid}/values/{_encode_range(str(rng).strip())}?valueInputOption=USER_ENTERED"
    body = json.dumps({"values": values})
    return await _request("PUT", url, content=body)


async def _append_rows(p: dict[str, Any]) -> dict[str, Any]:
    sid = p.get("spreadsheet_id", "")
    values = p.get("values")
    validate_spreadsheet_id(sid)
    if values is None:
        raise ValueError("append_rows requires 'values' as list of rows")
    rng = str(p.get("range") or "Sheet1!A1").strip()
    url = (
        f"{BASE}/{sid}/values/{_encode_range(rng)}:append"
        "?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
    )
    body = json.dumps({"values": values})
    return await _request("POST", url, content=body)


async def _create_sheet(p: dict[str, Any]) -> dict[str, Any]:
    title = (p.get("title") or "").strip()
    if not title:
        raise ValueError("create_sheet requires non-empty 'title'")
    if len(title) > 200:
        raise ValueError("create_sheet title must be 200 characters or less")
    url = BASE
    body = json.dumps({"properties": {"title": title}})
    return await _request("POST", url, content=body)


async def _clear_range(p: dict[str, Any]) -> dict[str, Any]:
    sid = p.get("spreadsheet_id", "")
    rng = p.get("range", "")
    validate_spreadsheet_id(sid)
    if not rng or not str(rng).strip():
        raise ValueError("clear_range requires 'range'")
    url = f"{BASE}/{sid}/values/{_encode_range(str(rng).strip())}:clear"
    return await _request("POST", url, content=json.dumps({}))
