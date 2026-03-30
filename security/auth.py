"""
security/auth.py
─────────────────
API Authentication for Pantheon COO OS.

Two modes (configured via .env):

  AUTH_MODE=none      → open (default for local dev — no key required)
  AUTH_MODE=apikey    → static API key in X-COO-API-Key header
  AUTH_MODE=jwt       → JWT bearer tokens + per-user API keys (multi-user)

API key generation:
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"

Usage in requests:
  curl -H "Authorization: Bearer <jwt>" http://localhost:8002/execute ...
  curl -H "X-COO-API-Key: <user-or-legacy-key>" http://localhost:8002/execute ...

Public endpoints (no auth required regardless of mode):
  GET  /health
  GET  /        (dashboard HTML)
  POST /auth/register
  POST /auth/login
  GET  /webhook/whatsapp  (Meta verification GET)
  POST /webhook/whatsapp  (validated by WhatsApp signature)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

# ─────────────────────────────────────────────────────────────────────────────
# Config — AUTH_MODE / COO_API_KEY read via helpers so tests can monkeypatch os.environ
# without reloading this module (see tests/test_auth.py).
# ─────────────────────────────────────────────────────────────────────────────

JWT_ALGORITHM  = "HS256"


def _auth_mode() -> str:
    return os.getenv("AUTH_MODE", "none").lower()


def _legacy_api_key() -> str:
    return os.getenv("COO_API_KEY", "")

# Endpoints that skip auth entirely
PUBLIC_PATHS = {
    "/",
    "/health",
    "/static",
    "/webhook/whatsapp",
    "/webhook/telegram",
    "/webhook/razorpay",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/register",
    "/auth/login",
    "/billing/plans",
    "/config/branding",
    "/webhook/zapier",
    "/onboarding/samples",
    "/tutorials",
    "/sitemap.xml",
    "/robots.txt",
    "/docs-page",
    "/marketplace",
    "/ready",
}


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency — use as: Depends(require_auth)
# ─────────────────────────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-COO-API-Key", auto_error=False)
_bearer         = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
    bearer:  Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> dict:
    """
    FastAPI dependency. Validates the request based on AUTH_MODE.
    Returns identity dict on success.
    Raises HTTP 401/403 on failure.
    """
    path = request.url.path
    if _is_public(path):
        return {"authenticated": False, "mode": "public", "plan": "free"}

    mode = _auth_mode()
    if mode == "none":
        return {
            "authenticated": True,
            "mode": "none",
            "user_id": None,
            "email": "",
            "role": "user",
            "jti": None,
            "plan": "free",
        }

    if mode == "apikey":
        return _check_api_key(api_key)

    if mode == "jwt":
        return await _auth_jwt_mode(bearer, api_key)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unknown AUTH_MODE: '{mode}'. Set to: none | apikey | jwt",
    )


async def require_admin(auth: dict = Depends(require_auth)):
    if auth.get("mode") == "none":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if auth.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )
    return auth


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/affiliate/link"):
        return True
    if path.startswith("/i18n/"):
        return True
    if path.startswith("/shared/"):
        return True
    return any(path.startswith(p) for p in ("/static/", "/webhook/"))


async def _auth_jwt_mode(
    bearer: Optional[HTTPAuthorizationCredentials],
    api_key: Optional[str],
) -> dict:
    from config import settings
    import memory.store as store
    from security import user_auth

    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_MODE=jwt but JWT_SECRET / jwt_secret is not set in .env",
        )

    if bearer and bearer.credentials:
        payload = user_auth.verify_jwt(bearer.credentials)
        if payload:
            uid = payload.get("sub")
            if uid:
                u = await store.get_user_by_id(uid)
                if u and u.get("is_active", 1):
                    return {
                        "authenticated": True,
                        "mode": "jwt",
                        "user_id": uid,
                        "email": u.get("email", ""),
                        "role": u.get("role", "user"),
                        "jti": payload.get("jti"),
                        "plan": u.get("plan", "free"),
                    }

    legacy = _legacy_api_key()
    if api_key and legacy and hmac.compare_digest(
        api_key.encode(), legacy.encode()
    ):
        return {
            "authenticated": True,
            "mode": "apikey",
            "legacy": True,
            "user_id": None,
            "email": "",
            "role": "user",
            "jti": None,
            "plan": "free",
        }

    if api_key:
        u = await store.get_user_by_api_key(api_key)
        if u and u.get("is_active", 1):
            return {
                "authenticated": True,
                "mode": "jwt",
                "user_id": u["user_id"],
                "email": u.get("email", ""),
                "role": u.get("role", "user"),
                "jti": None,
                "plan": u.get("plan", "free"),
            }

    if not bearer or not bearer.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token or X-COO-API-Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or revoked token",
    )


def _check_api_key(provided: Optional[str]) -> dict:
    key = _legacy_api_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_MODE=apikey but COO_API_KEY is not set in .env",
        )
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-COO-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not hmac.compare_digest(
        provided.encode(), key.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return {
        "authenticated": True,
        "mode": "apikey",
        "legacy": True,
        "user_id": None,
        "email": "",
        "role": "user",
        "jti": None,
        "plan": "free",
    }


# ─────────────────────────────────────────────────────────────────────────────
# JWT utilities (for issuing tokens)
# ─────────────────────────────────────────────────────────────────────────────

def create_token(subject: str, expires_in_hours: int = 24) -> str:
    """Create a signed JWT. Requires jwt_secret in config."""
    from config import settings
    try:
        import jwt as pyjwt
    except ImportError:
        raise RuntimeError("PyJWT not installed. Run: pip install PyJWT")
    if not settings.jwt_secret:
        raise RuntimeError("jwt_secret / JWT_SECRET not configured")
    payload = {
        "sub": subject,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_hours * 3600,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp signature verification (HMAC-SHA256)
# ─────────────────────────────────────────────────────────────────────────────

def verify_whatsapp_signature(body: bytes, signature_header: str) -> bool:
    """
    Validate X-Hub-Signature-256 on inbound WhatsApp webhooks.
    Returns True if valid, False otherwise.
    """
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if not app_secret:
        return True  # not configured — skip (warn in prod)
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)
