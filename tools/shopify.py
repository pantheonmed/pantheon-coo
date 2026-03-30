"""
tools/shopify.py — Shopify Admin REST API helpers.
"""
from __future__ import annotations

from typing import Any

import httpx

from config import settings

API_VER = "2024-01"
TIMEOUT = 45.0


def _shop_url() -> str:
    domain = (settings.shopify_store_domain or "").strip().rstrip("/")
    if not domain:
        raise RuntimeError("shopify_store_domain is not configured")
    if not domain.endswith(".myshopify.com"):
        domain = f"{domain}.myshopify.com" if "." not in domain else domain
    return f"https://{domain}/admin/api/{API_VER}"


def _headers() -> dict[str, str]:
    tok = (settings.shopify_access_token or "").strip()
    if not tok:
        raise RuntimeError("shopify_access_token is not configured")
    return {"X-Shopify-Access-Token": tok, "Content-Type": "application/json"}


async def execute(action: str, params: dict[str, Any]) -> Any:
    dispatch = {
        "get_products": _get_products,
        "get_orders": _get_orders,
        "create_product": _create_product,
        "update_inventory": _update_inventory,
        "get_analytics": _get_analytics,
    }
    fn = dispatch.get(action)
    if not fn:
        raise ValueError(f"Unknown shopify action: {action}. Available: {list(dispatch)}")
    return await fn(params)


async def _get_products(p: dict[str, Any]) -> dict[str, Any]:
    limit = min(int(p.get("limit") or 20), 250)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{_shop_url()}/products.json", headers=_headers(), params={"limit": limit})
    r.raise_for_status()
    data = r.json()
    prods = data.get("products") or []
    return {"products": prods, "count": len(prods)}


async def _get_orders(p: dict[str, Any]) -> dict[str, Any]:
    status = p.get("status", "open")
    limit = min(int(p.get("limit") or 20), 250)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(
            f"{_shop_url()}/orders.json",
            headers=_headers(),
            params={"status": status, "limit": limit},
        )
    r.raise_for_status()
    data = r.json()
    orders = data.get("orders") or []
    return {"orders": orders, "count": len(orders)}


async def _create_product(p: dict[str, Any]) -> dict[str, Any]:
    title = p.get("title", "Product")
    body_html = p.get("description", "")
    price = str(p.get("price", "0"))
    inv = int(p.get("inventory") or 0)
    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "variants": [{"price": price, "inventory_quantity": inv}],
        }
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{_shop_url()}/products.json", headers=_headers(), json=payload)
    r.raise_for_status()
    data = r.json()
    prod = data.get("product") or {}
    return {"product_id": prod.get("id"), "title": prod.get("title")}


async def _update_inventory(p: dict[str, Any]) -> dict[str, Any]:
    product_id = int(p["product_id"])
    quantity = int(p["quantity"])
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{_shop_url()}/products/{product_id}.json", headers=_headers())
    r.raise_for_status()
    prod = r.json().get("product") or {}
    variants = prod.get("variants") or []
    if not variants:
        raise ValueError("Product has no variants")
    vid = variants[0]["id"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r2 = await c.post(
            f"{_shop_url()}/inventory_levels/set.json",
            headers=_headers(),
            json={
                "location_id": p.get("location_id") or 1,
                "inventory_item_id": variants[0].get("inventory_item_id"),
                "available": quantity,
            },
        )
    if r2.is_success:
        return {"product_id": product_id, "quantity": quantity, "ok": True}
    return {"product_id": product_id, "quantity": quantity, "ok": False, "detail": r2.text[:200]}


async def _get_analytics(p: dict[str, Any]) -> dict[str, Any]:
    period = p.get("period", "day")
    return {"period": period, "note": "Use ShopifyQL or Analytics API in production; summary placeholder."}
