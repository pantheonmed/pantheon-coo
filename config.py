"""
config.py — Central settings for Pantheon COO OS v2
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings

try:
    from playwright.async_api import async_playwright  # noqa: F401

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class Settings(BaseSettings):
    app_name: str = "Pantheon COO OS"
    app_version: str = "2.0.0"
    debug: bool = False

    # AI — Primary (Claude)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5"
    claude_model_fast: str = "claude-haiku-4-5-20251001"

    # AI — Fallback (OpenAI) — Phase 4
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_model_fast: str = "gpt-4o-mini"
    openai_whisper_model: str = "whisper-1"

    # Voice (Whisper + TTS; requires OPENAI_API_KEY)
    voice_enabled: bool = False
    enable_fallback: bool = True          # fall back to OpenAI if Claude fails
    max_model_retries: int = 2

    # Database
    db_path: str = "pantheon_v2.db"

    # Orchestrator loop controls
    max_loop_iterations: int = 5
    agent_timeout_seconds: int = 90
    min_eval_score: float = 0.75

    # Performance monitoring — Phase 4
    monitor_interval_seconds: int = 300   # check every 5 min
    alert_score_threshold: float = 0.60   # alert if avg score drops below
    alert_failure_rate: float = 0.40      # alert if >40% tasks fail
    prompt_optimize_after: int = 10       # optimize prompts after N tasks per type

    # Server ports (override via PORT / FRONTEND_PORT in .env)
    port: int = 8002
    host: str = "0.0.0.0"
    frontend_port: int = 3002
    frontend_host: str = "0.0.0.0"

    # Security
    allowed_commands: list[str] = [
        "ls", "pwd", "echo", "cat", "head", "tail", "wc", "grep", "find", "tree",
        "mkdir", "touch", "cp", "mv", "python3", "pip3", "npm", "node",
        "git", "curl", "wget", "ping", "df", "du", "free", "ps",
    ]
    workspace_dir: str = str(Path("/tmp/pantheon_v2"))

    # WhatsApp
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    # Email
    email_backend: str = "smtp"
    email_from: str = "coo@pantheon.ai"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""

    # API auth: none | apikey | jwt (read by security/auth.py via os.environ after load)
    auth_mode: str = "none"

    # Multi-user auth (AUTH_MODE=jwt)
    jwt_secret: str = ""  # REQUIRED in production; set JWT_SECRET in .env
    jwt_expiry_hours: int = 168  # 7 days
    allow_registration: bool = True
    admin_email: str = ""
    admin_telegram_chat_id: str = ""
    # Standalone /admin HTML UI (separate from JWT admin role)
    admin_password: str = ""

    # Razorpay (India billing)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Stripe (global billing)
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # i18n
    default_language: str = "en"
    supported_languages: list[str] = [
        "en",
        "hi",
        "ar",
        "de",
        "fr",
        "ja",
        "pt",
        "id",
        "vi",
        "tl",
        "yo",
        "ta",
    ]

    # Multi-currency
    default_currency: str = "INR"
    supported_currencies: list[str] = [
        "INR",
        "USD",
        "GBP",
        "EUR",
        "AED",
        "JPY",
        "BRL",
        "IDR",
        "SGD",
        "NGN",
    ]

    # Amazon Selling Partner API
    amazon_access_key: str = ""
    amazon_secret_key: str = ""
    amazon_role_arn: str = ""
    amazon_marketplace_id: str = "A21TJRUUN4KGV"

    # Meesho supplier API
    meesho_api_key: str = ""
    meesho_supplier_id: str = ""

    # WhatsApp commerce (catalog / orders)
    whatsapp_catalog_id: str = ""
    whatsapp_business_account_id: str = ""

    # Google Sheets (service account JSON path or inline JSON string)
    google_service_account_json: str = ""
    google_sheets_scope: str = "https://www.googleapis.com/auth/spreadsheets"

    # Telegram Bot
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Twilio (voice / SMS)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Database tool — comma-separated hostnames allowed for postgresql:// and mysql://
    database_whitelist: str = ""

    # Production DB pool (optional). When set with postgresql, DBPool.backend is postgresql.
    # Store layer still uses SQLite via acquire() unless POSTGRES_STORE_ENABLED=true.
    database_url: str = ""
    postgres_store_enabled: bool = False

    # Deployer (CLI + GitHub API)
    github_token: str = ""
    github_username: str = ""
    railway_token: str = ""
    vercel_token: str = ""

    # Video generation (D-ID / Synthesia optional)
    did_api_key: str = ""
    synthesia_api_key: str = ""
    video_generation_enabled: bool = False

    # Notion
    notion_api_key: str = ""

    # Zoho CRM (India .in API)
    zoho_access_token: str = ""
    zoho_refresh_token: str = ""
    zoho_client_id: str = ""
    zoho_client_secret: str = ""

    # Google Calendar (same service account JSON as Sheets)
    google_calendar_scope: str = "https://www.googleapis.com/auth/calendar"

    # Redis (optional cache + distributed rate limits)
    redis_url: str = ""
    redis_enabled: bool = False
    cache_ttl_seconds: int = 300

    # OpenTelemetry
    otel_enabled: bool = False
    otel_endpoint: str = ""
    otel_service_name: str = "pantheon-coo"

    # White-label / rebranding
    white_label_enabled: bool = False
    white_label_name: str = "Pantheon COO"
    white_label_logo_url: str = ""
    white_label_primary_color: str = "#7c6ff7"
    white_label_support_email: str = "hello@pantheon.ai"
    white_label_domain: str = ""

    # Affiliate program
    default_affiliate_commission: float = 20.0

    # Tally Prime integration
    tally_host: str = "localhost"
    tally_port: int = 9000
    tally_company: str = ""

    # Zapier inbound webhook + tools
    zapier_webhook_secret: str = ""

    # HubSpot CRM (API key / private app token)
    hubspot_api_key: str = ""

    # WordPress REST (application password)
    wordpress_site_url: str = ""
    wordpress_username: str = ""
    wordpress_app_password: str = ""

    # Shopify Admin API
    shopify_store_domain: str = ""
    shopify_access_token: str = ""

    # LinkedIn automation (Playwright; use responsibly)
    linkedin_email: str = ""
    linkedin_password: str = ""

    # Instagram / Twitter
    instagram_username: str = ""
    instagram_password: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""

    # Enterprise SAML (stub endpoints until full IdP wiring)
    saml_enabled: bool = False
    saml_idp_metadata_url: str = ""
    saml_sp_entity_id: str = ""

    # Task queue workers (Task 90)
    worker_count: int = 2
    max_queue_depth: int = 100
    distributed_task_queue: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
# Keep os.environ in sync so security/auth.py and tests using getenv see .env value.
os.environ["AUTH_MODE"] = (settings.auth_mode or "none").lower()

# Paid plan catalog — amounts in paise (INR × 100) for Razorpay Order API
PLAN_PRICING = {
    "starter": {"amount": 299900, "currency": "INR", "label": "₹2,999/month"},
    "pro": {"amount": 999900, "currency": "INR", "label": "₹9,999/month"},
    # Dashboard “PRO” tier at ₹999/mo (Razorpay INR)
    "pro_monthly": {"amount": 99900, "currency": "INR", "label": "₹999/month"},
    "enterprise": {"amount": 4999900, "currency": "INR", "label": "₹49,999/month"},
    "team_5": {"amount": 999900, "currency": "INR", "label": "₹9,999/month"},
    "team_25": {"amount": 2499900, "currency": "INR", "label": "₹24,999/month"},
}

# Task limits per plan (for dashboard / docs; -1 = unlimited)
PLAN_LIMITS = {
    "free": {"tasks_per_month": 20},
    "starter": {"tasks_per_month": 100},
    "pro": {"tasks_per_month": -1},
    "pro_monthly": {"tasks_per_month": -1},
    "enterprise": {"tasks_per_month": -1},
    "team_5": {"tasks_per_month": -1},
    "team_25": {"tasks_per_month": -1},
}

# Regional pricing: amounts in smallest currency unit (paise / cents / fils, etc.)
GLOBAL_PRICING: dict[str, dict[str, dict[str, Any]]] = {
    "INR": {
        "starter": {"amount": 299900, "label": "₹2,999/mo"},
        "pro": {"amount": 999900, "label": "₹9,999/mo"},
        "pro_monthly": {"amount": 99900, "label": "₹999/mo"},
        "enterprise": {"amount": 4999900, "label": "₹49,999/mo"},
        "team_5": {"amount": 999900, "label": "₹9,999/mo — 5 seats"},
        "team_25": {"amount": 2499900, "label": "₹24,999/mo — 25 seats"},
    },
    "USD": {
        "starter": {"amount": 3900, "label": "$39/mo"},
        "pro": {"amount": 9900, "label": "$99/mo"},
        "pro_monthly": {"amount": 1200, "label": "$12/mo"},
        "enterprise": {"amount": 49900, "label": "$499/mo"},
    },
    "GBP": {
        "starter": {"amount": 3200, "label": "£32/mo"},
        "pro": {"amount": 7900, "label": "£79/mo"},
        "pro_monthly": {"amount": 1000, "label": "£10/mo"},
        "enterprise": {"amount": 39900, "label": "£399/mo"},
    },
    "EUR": {
        "starter": {"amount": 3700, "label": "€37/mo"},
        "pro": {"amount": 9200, "label": "€92/mo"},
        "pro_monthly": {"amount": 1100, "label": "€11/mo"},
        "enterprise": {"amount": 45900, "label": "€459/mo"},
    },
    "AED": {
        "starter": {"amount": 14900, "label": "AED 149/mo"},
        "pro": {"amount": 36900, "label": "AED 369/mo"},
        "pro_monthly": {"amount": 4500, "label": "AED 45/mo"},
        "enterprise": {"amount": 184900, "label": "AED 1,849/mo"},
    },
}

TIMEZONE_BY_COUNTRY: dict[str, str] = {
    "IN": "Asia/Kolkata",
    "US": "America/New_York",
    "GB": "Europe/London",
    "AE": "Asia/Dubai",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "JP": "Asia/Tokyo",
    "BR": "America/Sao_Paulo",
    "ID": "Asia/Jakarta",
    "SG": "Asia/Singapore",
    "NG": "Africa/Lagos",
    "PH": "Asia/Manila",
    "VN": "Asia/Ho_Chi_Minh",
}

COUNTRY_TO_CURRENCY: dict[str, str] = {
    "IN": "INR",
    "US": "USD",
    "GB": "GBP",
    "AE": "AED",
    "DE": "EUR",
    "FR": "EUR",
    "JP": "JPY",
    "BR": "BRL",
    "ID": "IDR",
    "SG": "SGD",
    "NG": "NGN",
    "PH": "USD",
    "VN": "USD",
}

LOCALE_BY_COUNTRY: dict[str, str] = {
    "IN": "en-IN",
    "US": "en-US",
    "GB": "en-GB",
    "AE": "ar-AE",
    "DE": "de-DE",
    "FR": "fr-FR",
    "JP": "ja-JP",
    "BR": "pt-BR",
    "ID": "id-ID",
    "SG": "en-SG",
    "NG": "en-NG",
    "PH": "en-PH",
    "VN": "vi-VN",
}
