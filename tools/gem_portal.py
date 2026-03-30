"""
tools/gem_portal.py — Government e-Marketplace (GeM) India helpers (curated / mock data in sandbox).
"""
from __future__ import annotations

from typing import Any


async def _search_bids(p: dict[str, Any]) -> dict[str, Any]:
    cat = str(p.get("category", "")).strip()
    state = str(p.get("state", "Tamil Nadu"))
    min_v = int(p.get("min_value", 0) or 0)
    return {
        "bids": [
            {
                "bid_id": "GEM-2026-001",
                "title": f"Medical equipment — {cat or 'general'}",
                "state": state,
                "value_inr": max(min_v, 500000),
                "deadline": "2026-04-15",
            }
        ],
        "source": "sandbox_curated",
    }


async def _get_bid_details(p: dict[str, Any]) -> dict[str, Any]:
    bid_id = str(p.get("bid_id", "")).strip()
    if not bid_id:
        raise ValueError("bid_id is required")
    return {
        "bid_id": bid_id,
        "requirements": ["GST registration", "Technical specs PDF"],
        "deadline": "2026-04-15",
        "contact": "procurement@example.gov.in",
    }


async def _prepare_bid_document(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "bid_id": p.get("bid_id"),
        "document_outline": ["Cover", "Technical", "Commercial", "Declarations"],
        "status": "draft_generated",
    }


async def _track_submissions(p: dict[str, Any]) -> dict[str, Any]:
    return {"submissions": []}


async def execute(action: str, params: dict[str, Any]) -> Any:
    act = (action or "").strip().lower()
    dispatch = {
        "search_bids": _search_bids,
        "get_bid_details": _get_bid_details,
        "prepare_bid_document": _prepare_bid_document,
        "track_submissions": _track_submissions,
    }
    fn = dispatch.get(act)
    if not fn:
        raise ValueError(f"Unknown gem_portal action '{action}'")
    return await fn(params)
