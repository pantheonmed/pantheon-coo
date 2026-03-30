"""
security/user_auth.py
─────────────────────
Multi-user passwords (bcrypt), JWT sessions, API keys, registration helpers.
"""
from __future__ import annotations

import re
import secrets
import time
import uuid
from typing import Any, Optional

import bcrypt
import jwt as pyjwt

from config import (
    COUNTRY_TO_CURRENCY,
    LOCALE_BY_COUNTRY,
    TIMEZONE_BY_COUNTRY,
    settings,
)

import memory.store as store

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

JWT_BLOCKLIST: set[str] = set()
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def create_jwt(user_id: str, email: str, role: str) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET / jwt_secret is not configured")
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + settings.jwt_expiry_hours * 3600,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> Optional[dict[str, Any]]:
    if not settings.jwt_secret or not token:
        return None
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
        )
        jti = payload.get("jti")
        if jti and jti in JWT_BLOCKLIST:
            return None
        return dict(payload)
    except pyjwt.PyJWTError:
        return None


def revoke_jwt_jti(jti: str) -> None:
    if jti:
        JWT_BLOCKLIST.add(jti)


def validate_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email.strip()))


async def create_user(
    email: str,
    name: str,
    password: str,
    *,
    industry: str = "other",
    ref_code: Optional[str] = None,
    country_code: Optional[str] = None,
    timezone: Optional[str] = None,
) -> dict[str, Any]:
    """Register a user; new accounts use plan ``free`` (including AUTH_MODE=jwt)."""
    if not settings.allow_registration:
        raise ValueError("Registration is disabled")
    if not validate_email(email):
        raise ValueError("Invalid email address")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if await store.get_user_by_email(email):
        raise ValueError("Email already registered")
    uid = str(uuid.uuid4())
    ph = hash_password(password)
    key = generate_api_key()
    cc = (country_code or "IN").strip().upper()
    if len(cc) != 2:
        cc = "IN"
    tz_use = (timezone or "").strip() or TIMEZONE_BY_COUNTRY.get(cc, "Asia/Kolkata")
    currency = COUNTRY_TO_CURRENCY.get(cc, settings.default_currency)
    loc = LOCALE_BY_COUNTRY.get(cc, "en-IN")
    await store.insert_user(
        uid,
        email.strip().lower(),
        name.strip(),
        ph,
        role="user",
        plan="free",
        api_key=key,
        industry=industry or "other",
        currency=currency,
        country_code=cc,
        timezone=tz_use,
        locale=loc,
    )
    await store.attach_referral_from_code(ref_code, uid, email.strip().lower())
    return {
        "user_id": uid,
        "email": email.strip().lower(),
        "name": name.strip(),
        "api_key": key,
        "plan": "free",
        "industry": industry or "other",
        "country_code": cc,
        "currency": currency,
        "timezone": tz_use,
        "locale": loc,
    }


async def update_last_login(user_id: str) -> None:
    await store.update_last_login(user_id)


async def authenticate_user(email: str, password: str) -> Optional[dict[str, Any]]:
    u = await store.get_user_by_email(email)
    if not u or not u.get("is_active", 1):
        return None
    if not verify_password(password, u["password_hash"]):
        return None
    return u
