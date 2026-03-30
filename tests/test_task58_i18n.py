"""Task 58 — i18n translations and public language API."""
import uuid

import pytest

import memory.store as store
from i18n.translations import get_supported_languages, t
from main import app
from security.auth import require_auth


def test_t_welcome_hindi():
    s = t("welcome", "hi")
    assert "Pantheon" in s
    assert "स्वागत" in s or "COO" in s


def test_t_welcome_arabic():
    s = t("welcome", "ar")
    assert "Pantheon" in s or "COO" in s
    assert "مرحب" in s


def test_t_unknown_key_falls_back_german():
    s = t("totally_unknown_key_xyz", "de")
    assert s == "totally_unknown_key_xyz"


def test_get_i18n_languages_count(client):
    r = client.get("/i18n/languages")
    assert r.status_code == 200
    data = r.json()
    assert len(data["languages"]) == 12


def test_get_translations_fr(client):
    r = client.get("/i18n/translations/fr")
    assert r.status_code == 200
    j = r.json()
    assert j["lang"] == "fr"
    assert "translations" in j
    assert j["translations"]["execute_task"]


def test_rtl_languages_include_arabic():
    langs = get_supported_languages()
    ar = next(x for x in langs if x["code"] == "ar")
    assert ar["rtl"] is True


def test_supported_languages_have_flag():
    for row in get_supported_languages():
        assert "flag" in row
        assert row["flag"]


def test_parse_accept_language_prefers_first_match():
    from i18n.translations import parse_accept_language

    c = parse_accept_language("de-DE,en-US;q=0.9", {"de", "en"})
    assert c == "de"


def test_t_welcome_english():
    assert "Welcome" in t("welcome", "en")


def test_translations_vietnamese_welcome():
    s = t("welcome", "vi")
    assert "Pantheon" in s


def test_twelve_language_codes_in_translations():
    from i18n.translations import TRANSLATIONS

    assert len(TRANSLATIONS) == 12


def test_auth_me_language_patch_requires_auth(client):
    """Without JWT override, /auth/me/language should not succeed in open mode."""
    r = client.patch("/auth/me/language", json={"language": "ar"})
    assert r.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_patch_language_with_override(client):
    uid = str(uuid.uuid4())
    ph = "x" * 60
    await store.insert_user(
        uid,
        f"lang{uuid.uuid4().hex[:6]}@example.com",
        "Lang",
        ph,
        api_key="k" + uuid.uuid4().hex[:8],
    )

    async def _auth():
        return {
            "authenticated": True,
            "mode": "jwt",
            "user_id": uid,
            "email": "x@y.z",
            "role": "user",
            "plan": "free",
            "jti": None,
        }

    app.dependency_overrides[require_auth] = _auth
    try:
        r = client.patch("/auth/me/language", json={"language": "de"})
        assert r.status_code == 200
        assert r.json()["language"] == "de"
        u = await store.get_user_by_id(uid)
        assert u["language"] == "de"
    finally:
        app.dependency_overrides.pop(require_auth, None)
