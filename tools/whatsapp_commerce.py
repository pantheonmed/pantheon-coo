"""
tools/whatsapp_commerce.py — Catalog, orders, and campaigns via WhatsApp Cloud API.
"""
from __future__ import annotations

import re
from typing import Any

import whatsapp


_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


async def execute(action: str, params: dict[str, Any]) -> Any:
    a = (action or "").strip().lower()

    if a == "send_order_confirmation":
        return await whatsapp.send_order_confirmation(
            to_number=params.get("to_number") or "",
            order_id=params.get("order_id") or "",
            items=params.get("items") or [],
            total=float(params.get("total") or 0),
        )

    if a == "send_shipping_update":
        return await whatsapp.send_shipping_update(
            to_number=params.get("to_number") or "",
            order_id=params.get("order_id") or "",
            status=params.get("status") or "",
            tracking_url=params.get("tracking_url") or "",
        )

    if a == "broadcast_offer":
        phones = params.get("phone_numbers") or []
        invalid = [p for p in phones if not _E164.match(str(p).strip())]
        if invalid:
            raise ValueError(f"Invalid E.164 phone numbers: {invalid}")
        offer = params.get("offer_text") or ""
        cat = params.get("catalog_id") or ""
        sent = []
        for p in phones:
            sent.append(await whatsapp.send(str(p).strip(), offer))
        return {"sent": len(sent), "catalog_id": cat, "results": sent}

    raise ValueError(f"Unknown whatsapp_commerce action: {action}")
