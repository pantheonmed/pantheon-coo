"""
billing.py — Razorpay (INR) + Stripe (global): orders, verify, webhooks, plan catalog.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

import stripe
from config import GLOBAL_PRICING, PLAN_LIMITS, PLAN_PRICING, settings
import memory.store as store
from memory.redis_client import cached
from security.auth import require_auth

log = logging.getLogger(__name__)

router = APIRouter(tags=["Billing"])


class CreateOrderBody(BaseModel):
    plan: str = Field(..., description="starter | pro | pro_monthly | enterprise | team_*")


class VerifyPaymentBody(BaseModel):
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None

    @model_validator(mode="after")
    def _one_gateway(self) -> "VerifyPaymentBody":
        if self.stripe_payment_intent_id:
            return self
        if self.razorpay_order_id and self.razorpay_payment_id and self.razorpay_signature:
            return self
        raise ValueError(
            "Provide razorpay_order_id, razorpay_payment_id, razorpay_signature "
            "or stripe_payment_intent_id"
        )


def _require_uid(auth: dict) -> str:
    uid = auth.get("user_id")
    if not uid:
        raise HTTPException(401, "Authentication required")
    return uid


def get_razorpay_client():
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        return None
    import razorpay

    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def verify_webhook_body(body: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _currency_for_order(request: Request, user_id: str) -> str:
    hdr = request.headers.get("accept-currency") or request.headers.get("Accept-Currency") or ""
    cur = (hdr or "").strip().upper()
    if cur and cur in settings.supported_currencies:
        return cur
    u = await store.get_user_by_id(user_id)
    cur2 = (u or {}).get("currency") or settings.default_currency
    cur2 = str(cur2).upper()
    if cur2 not in settings.supported_currencies:
        return settings.default_currency
    return cur2


def _tier_prices_for_currency(cur: str) -> dict[str, dict[str, Any]]:
    cur = cur.upper()
    if cur in GLOBAL_PRICING:
        return GLOBAL_PRICING[cur]
    return GLOBAL_PRICING["USD"]


@cached(ttl=3600, key_prefix="billing_plans")
async def _billing_plans_payload(currency: Optional[str]) -> dict[str, Any]:
    """Public catalog; optional ?currency=USD for localized paid-tier labels."""
    cur = (currency or "INR").strip().upper()
    if cur not in GLOBAL_PRICING:
        cur = "INR"
    gp = GLOBAL_PRICING[cur]
    return {
        "currency": cur,
        "plans": [
            {
                "id": "free",
                "name": "Free",
                "price": "₹0/month" if cur == "INR" else f"{cur} 0/month",
                "tasks_per_month": 20,
                "features": [
                    "20 tasks/month",
                    "All 19+ tools",
                    "Dashboard access",
                    "Email support",
                    "WhatsApp commands",
                ],
            },
            {
                "id": "starter",
                "name": "Starter",
                "price": gp["starter"]["label"],
                "tasks_per_month": 100,
                "features": [
                    "100 tasks/month",
                    "Everything in Free",
                    "Task templates",
                    "Scheduler (cron jobs)",
                    "Google Sheets integration",
                    "Priority support",
                    "Daily briefings",
                ],
            },
            {
                "id": "pro",
                "name": "Pro",
                "price": gp["pro"]["label"],
                "tasks_per_month": -1,
                "features": [
                    "Unlimited tasks",
                    "Everything in Starter",
                    "Slack + Telegram bots",
                    "Voice commands (WhatsApp)",
                    "Custom tool builder",
                    "Analytics dashboard",
                    "Webhook integration",
                    "Dedicated support",
                    "SLA guarantee",
                ],
            },
            {
                "id": "pro_monthly",
                "name": "PRO (₹999)",
                "price": (gp.get("pro_monthly") or {}).get("label", "₹999/mo"),
                "tasks_per_month": -1,
                "features": [
                    "Unlimited tasks",
                    "All tools + integrations",
                    "Priority execution",
                    "Best for individuals & small teams upgrading from Free",
                ],
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "price": gp["enterprise"]["label"],
                "tasks_per_month": -1,
                "features": [
                    "Unlimited tasks",
                    "Dedicated support",
                    "Custom SLA",
                ],
            },
            {
                "id": "team_5",
                "name": "Team (5 seats)",
                "price": (gp.get("team_5") or {}).get("label", "₹9,999/mo — 5 seats"),
                "tasks_per_month": -1,
                "features": [
                    "5 members",
                    "Unlimited tasks",
                    "Shared team task board",
                ],
            },
            {
                "id": "team_25",
                "name": "Team (25 seats)",
                "price": (gp.get("team_25") or {}).get("label", "₹24,999/mo — 25 seats"),
                "tasks_per_month": -1,
                "features": [
                    "25 members",
                    "Unlimited tasks",
                    "Priority support",
                ],
            },
        ],
    }


@router.get("/billing/plans")
async def billing_plans(currency: Optional[str] = None) -> dict[str, Any]:
    return await _billing_plans_payload(currency)


@router.get("/billing/summary")
async def billing_summary(auth: dict = Depends(require_auth)) -> dict[str, Any]:
    uid = _require_uid(auth)
    u = await store.get_user_by_id(uid)
    if not u:
        raise HTTPException(404, "User not found")
    plan = u.get("plan", "free")
    lim = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])["tasks_per_month"]
    used = await store.count_tasks_for_user_this_month(uid)
    return {
        "plan": plan,
        "tasks_used_this_month": used,
        "tasks_limit": lim,
    }


@router.post("/billing/create-order")
async def create_order(
    body: CreateOrderBody,
    request: Request,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    uid = _require_uid(auth)
    plan = body.plan.strip().lower()
    cur = await _currency_for_order(request, uid)

    if cur == "INR":
        pricing = PLAN_PRICING.get(plan)
        if not pricing:
            raise HTTPException(
                400,
                "Invalid plan. Choose starter, pro, pro_monthly, enterprise, or team plan.",
            )
        client = get_razorpay_client()
        if not client:
            raise HTTPException(
                503,
                "Billing is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
            )
        internal_id = str(uuid.uuid4())
        receipt = internal_id.replace("-", "")[:40]
        try:
            rz_order = client.order.create(
                {
                    "amount": pricing["amount"],
                    "currency": pricing["currency"],
                    "receipt": receipt,
                    "notes": {
                        "user_id": uid,
                        "plan": plan,
                        "internal_order_id": internal_id,
                    },
                }
            )
        except Exception as e:
            log.exception("Razorpay order.create failed")
            raise HTTPException(502, f"Payment provider error: {e}") from e
        rzp_oid = rz_order["id"]
        await store.insert_order(
            internal_id,
            uid,
            plan,
            pricing["amount"],
            pricing["currency"],
            "pending",
            razorpay_order_id=rzp_oid,
            payment_gateway="razorpay",
        )
        return {
            "gateway": "razorpay",
            "order_id": internal_id,
            "razorpay_order_id": rzp_oid,
            "amount": pricing["amount"],
            "currency": pricing["currency"],
            # Frontend (dashboard) expects these names for Razorpay checkout.js
            "key_id": settings.razorpay_key_id,
            "razorpay_key_id": settings.razorpay_key_id,
            "plan_name": pricing.get("label", plan.title()),
            "plan": plan,
        }

    prices = _tier_prices_for_currency(cur)
    tier = prices.get(plan)
    if not tier:
        raise HTTPException(
            400,
            "Invalid plan. Choose starter, pro, pro_monthly, enterprise, or team plan.",
        )
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe is not configured. Set STRIPE_SECRET_KEY.")

    stripe.api_key = settings.stripe_secret_key
    internal_id = str(uuid.uuid4())
    amt = int(tier["amount"])
    try:
        intent = stripe.PaymentIntent.create(
            amount=amt,
            currency=cur.lower(),
            automatic_payment_methods={"enabled": True},
            metadata={
                "user_id": uid,
                "plan": plan,
                "internal_order_id": internal_id,
            },
        )
    except Exception as e:
        log.exception("Stripe PaymentIntent.create failed")
        raise HTTPException(502, f"Stripe error: {e}") from e

    await store.insert_order(
        internal_id,
        uid,
        plan,
        amt,
        cur,
        "pending",
        stripe_payment_intent_id=intent.id,
        payment_gateway="stripe",
    )
    return {
        "gateway": "stripe",
        "order_id": internal_id,
        "client_secret": intent.client_secret,
        "amount": amt,
        "currency": cur,
        "publishable_key": settings.stripe_publishable_key,
    }


@router.post("/billing/verify-payment")
async def verify_payment(
    body: VerifyPaymentBody,
    auth: dict = Depends(require_auth),
) -> dict[str, Any]:
    uid = _require_uid(auth)

    if body.stripe_payment_intent_id:
        if not settings.stripe_secret_key:
            raise HTTPException(503, "Stripe not configured")

        stripe.api_key = settings.stripe_secret_key
        try:
            pi = stripe.PaymentIntent.retrieve(body.stripe_payment_intent_id)
        except Exception as e:
            try:
                from monitoring.error_tracker import track_error

                await track_error(e, context={"billing": "stripe_verify"}, user_id=uid)
            except Exception:
                pass
            raise HTTPException(400, f"Stripe error: {e}") from e
        if pi.status != "succeeded":
            raise HTTPException(400, "Payment not completed")
        row = await store.get_order_by_stripe_payment_intent_id(body.stripe_payment_intent_id)
        if not row or row.get("user_id") != uid:
            raise HTTPException(400, "Order does not belong to this user")
        if row.get("status") == "paid":
            return {"success": True, "plan": row["plan"], "message": "Already upgraded"}
        u_before = await store.get_user_by_id(uid)
        old_plan = (u_before or {}).get("plan", "free")
        await store.mark_order_paid(row["order_id"], body.stripe_payment_intent_id, gateway="stripe")
        await store.update_user_plan(uid, row["plan"])
        try:
            await store.apply_affiliate_commission_on_payment(uid, int(row.get("amount") or 0))
        except Exception:
            pass
        try:
            from analytics import track as track_analytics

            await track_analytics(
                "plan_upgraded",
                uid,
                from_plan=old_plan,
                to_plan=row["plan"],
                gateway="stripe",
            )
        except Exception:
            pass
        return {"success": True, "plan": row["plan"], "message": "Upgraded successfully"}

    client = get_razorpay_client()
    if not client:
        raise HTTPException(503, "Billing not configured")
    params = {
        "razorpay_order_id": body.razorpay_order_id,
        "razorpay_payment_id": body.razorpay_payment_id,
        "razorpay_signature": body.razorpay_signature,
    }
    try:
        client.utility.verify_payment_signature(params)
    except Exception as e:
        try:
            from monitoring.error_tracker import track_error

            await track_error(e, context={"billing": "razorpay_verify"}, user_id=uid)
        except Exception:
            pass
        raise HTTPException(400, f"Invalid payment signature: {e}") from e
    row = await store.get_order_by_razorpay_order_id(body.razorpay_order_id or "")
    if not row or row.get("user_id") != uid:
        raise HTTPException(400, "Order does not belong to this user")
    if row.get("status") == "paid":
        return {"success": True, "plan": row["plan"], "message": "Already upgraded"}
    u_before = await store.get_user_by_id(uid)
    old_plan = (u_before or {}).get("plan", "free")
    await store.mark_order_paid(row["order_id"], body.razorpay_payment_id or "", gateway="razorpay")
    await store.update_user_plan(uid, row["plan"])
    try:
        await store.apply_affiliate_commission_on_payment(uid, int(row.get("amount") or 0))
    except Exception:
        pass
    try:
        from analytics import track as track_analytics

        amt = int(row.get("amount") or 0)
        await track_analytics(
            "plan_upgraded",
            uid,
            from_plan=old_plan,
            to_plan=row["plan"],
            amount_inr=round(amt / 100.0, 2),
        )
    except Exception:
        pass
    return {"success": True, "plan": row["plan"], "message": "Upgraded successfully"}


@router.get("/billing/history")
async def billing_history(
    auth: dict = Depends(require_auth),
    limit: int = 50,
) -> dict[str, Any]:
    uid = _require_uid(auth)
    rows = await store.list_orders_for_user(uid, limit=limit)
    return {
        "payments": [
            {
                "order_id": r["order_id"],
                "plan": r["plan"],
                "amount": r["amount"],
                "currency": r["currency"],
                "status": r["status"],
                "created_at": r["created_at"],
                "completed_at": r.get("completed_at"),
            }
            for r in rows
        ]
    }


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request) -> dict[str, str]:
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")

    if not settings.razorpay_webhook_secret:
        log.warning("RAZORPAY_WEBHOOK_SECRET not set; rejecting webhook")
        raise HTTPException(503, "Webhook not configured")

    if not verify_webhook_body(body, sig, settings.razorpay_webhook_secret):
        raise HTTPException(400, "Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}") from e

    event = payload.get("event", "")
    try:
        if event == "payment.captured":
            await _handle_payment_captured(payload)
        elif event == "payment.failed":
            await _handle_payment_failed(payload)
        elif event == "subscription.cancelled":
            await _handle_subscription_cancelled(payload)
        else:
            log.debug("Unhandled Razorpay event: %s", event)
    except Exception:
        log.exception("Webhook handler error for event %s", event)

    return {"status": "ok"}


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict[str, str]:
    raw = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe webhook not configured")

    try:
        event = stripe.Webhook.construct_event(
            raw, sig, settings.stripe_webhook_secret
        )
    except Exception as e:
        raise HTTPException(400, f"Invalid Stripe webhook: {e}") from e

    etype = event["type"]
    obj = event["data"]["object"]
    try:
        if etype == "payment_intent.succeeded":
            await _stripe_payment_intent_succeeded(obj)
        elif etype == "payment_intent.payment_failed":
            await _stripe_payment_intent_failed(obj)
        elif etype == "customer.subscription.deleted":
            await _stripe_subscription_deleted(obj)
    except Exception:
        log.exception("Stripe webhook handler error for %s", etype)

    return {"status": "ok"}


async def _stripe_payment_intent_succeeded(obj: Any) -> None:
    pi = obj.get("id") if hasattr(obj, "get") else obj["id"]
    if not pi:
        return
    row = await store.get_order_by_stripe_payment_intent_id(pi)
    if not row or row.get("status") == "paid":
        return
    await store.mark_order_paid(row["order_id"], pi, gateway="stripe")
    await store.update_user_plan(row["user_id"], row["plan"])
    try:
        await store.apply_affiliate_commission_on_payment(
            row["user_id"], int(row.get("amount") or 0)
        )
    except Exception:
        pass


async def _stripe_payment_intent_failed(obj: Any) -> None:
    pi = obj.get("id") if hasattr(obj, "get") else obj["id"]
    if not pi:
        return
    row = await store.get_order_by_stripe_payment_intent_id(pi)
    if row:
        await store.mark_order_failed(row["order_id"])


async def _stripe_subscription_deleted(obj: Any) -> None:
    meta = (obj.get("metadata") or {}) if hasattr(obj, "get") else (obj["metadata"] or {})
    uid = meta.get("user_id")
    if uid:
        await store.update_user_plan(uid, "free")


async def _handle_payment_captured(payload: dict) -> None:
    ent = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )
    rzp_order_id = ent.get("order_id")
    pay_id = ent.get("id")
    if not rzp_order_id or not pay_id:
        return
    row = await store.get_order_by_razorpay_order_id(rzp_order_id)
    if not row:
        log.warning("Webhook: no local order for Razorpay order %s", rzp_order_id)
        return
    if row.get("status") == "paid":
        return
    await store.mark_order_paid(row["order_id"], pay_id, gateway="razorpay")
    await store.update_user_plan(row["user_id"], row["plan"])
    try:
        amt = int(ent.get("amount") or row.get("amount") or 0)
        await store.apply_affiliate_commission_on_payment(row["user_id"], amt)
    except Exception:
        pass


async def _handle_payment_failed(payload: dict) -> None:
    ent = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )
    rzp_order_id = ent.get("order_id")
    if not rzp_order_id:
        return
    row = await store.get_order_by_razorpay_order_id(rzp_order_id)
    if row:
        await store.mark_order_failed(row["order_id"])
        log.info("Payment failed for order %s user %s", rzp_order_id, row.get("user_id"))


async def _handle_subscription_cancelled(payload: dict) -> None:
    sub = (
        payload.get("payload", {})
        .get("subscription", {})
        .get("entity", {})
    )
    if not sub:
        return
    notes = sub.get("notes") or {}
    uid = notes.get("user_id")
    if uid:
        await store.update_user_plan(uid, "free")
        log.info("Subscription cancelled — user %s downgraded to free", uid)
    else:
        log.info("subscription.cancelled webhook without user_id in notes; skip downgrade")


def stripe_webhook_handler_exists() -> bool:
    """Test hook: Stripe webhook route is registered on the router."""
    return callable(stripe_webhook)
