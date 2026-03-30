"""
tools/browser.py — Playwright browser automation (Phase 2)

Install: pip install playwright && playwright install chromium

Supported actions:
  navigate      → go to URL, return title + status
  click         → click by CSS selector or visible text
  type_text     → type into an input field
  extract_text  → get text from a selector (or whole page)
  get_links     → extract all <a href> links
  screenshot    → save full-page PNG to workspace
  fill_form     → fill multiple fields + optional submit
  wait_for      → wait for a selector to appear
  scroll        → scroll up / down / to top / to bottom
  get_html      → get outerHTML of a selector
  close         → close and release the browser session

Sessions persist across steps using session_id (default: "default").
Always close the session in your last browser step.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any

_pw_available = True
try:
    from playwright.async_api import async_playwright, Page
except ImportError:
    _pw_available = False

from config import settings

SCREENSHOT_DIR = Path(settings.workspace_dir) / "screenshots"
_sessions: dict[str, dict] = {}


async def execute(action: str, params: dict[str, Any]) -> Any:
    if not _pw_available:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "navigate":     _navigate,
        "click":        _click,
        "type_text":    _type_text,
        "extract_text": _extract_text,
        "get_links":    _get_links,
        "screenshot":   _screenshot,
        "fill_form":    _fill_form,
        "wait_for":     _wait_for,
        "scroll":       _scroll,
        "get_html":     _get_html,
        "close":        _close,
    }
    fn = dispatch.get(action)
    if fn is None:
        raise ValueError(f"Unknown browser action: '{action}'. Available: {list(dispatch)}")
    return await fn(params)


# ─────────────────────────────────────────────────────────────────────────────
# Session management
# ─────────────────────────────────────────────────────────────────────────────

async def _get_page(params: dict) -> "Page":
    sid = params.get("session_id", "default")
    if sid not in _sessions:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await ctx.new_page()
        _sessions[sid] = {"pw": pw, "browser": browser, "ctx": ctx, "page": page}
    return _sessions[sid]["page"]


# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────

async def _navigate(p: dict) -> dict:
    page = await _get_page(p)
    resp = await page.goto(p["url"], wait_until=p.get("wait_until", "load"), timeout=30_000)
    return {"url": page.url, "title": await page.title(), "status": resp.status if resp else None}


async def _click(p: dict) -> dict:
    page = await _get_page(p)
    if "text" in p:
        await page.get_by_text(p["text"]).first.click(timeout=10_000)
        return {"clicked": f"text={p['text']}"}
    await page.click(p["selector"], timeout=10_000)
    return {"clicked": p["selector"]}


async def _type_text(p: dict) -> dict:
    page = await _get_page(p)
    if p.get("clear_first", True):
        await page.fill(p["selector"], "")
    await page.type(p["selector"], p["text"], delay=25)
    return {"typed": len(p["text"]), "selector": p["selector"]}


async def _extract_text(p: dict) -> Any:
    page = await _get_page(p)
    sel = p.get("selector", "body")
    if p.get("all"):
        els = await page.query_selector_all(sel)
        return [await el.inner_text() for el in els]
    el = await page.query_selector(sel)
    return "" if el is None else await el.inner_text()


async def _get_links(p: dict) -> list:
    page = await _get_page(p)
    links = await page.evaluate("""
        Array.from(document.querySelectorAll('a[href]'))
            .map(a => ({ href: a.href, text: a.innerText.trim().slice(0, 120) }))
            .filter(l => l.href.startsWith('http'))
            .slice(0, 60)
    """)
    return links


async def _screenshot(p: dict) -> dict:
    page = await _get_page(p)
    fname = p.get("filename", f"shot_{int(asyncio.get_event_loop().time())}.png")
    if not fname.endswith(".png"):
        fname += ".png"
    out = SCREENSHOT_DIR / fname
    await page.screenshot(path=str(out), full_page=p.get("full_page", True))
    return {"path": str(out), "bytes": out.stat().st_size, "url": page.url}


async def _fill_form(p: dict) -> dict:
    page = await _get_page(p)
    filled = []
    for field in p.get("fields", []):
        await page.fill(field["selector"], field["value"])
        filled.append(field["selector"])
    result: dict = {"filled": filled}
    if p.get("submit_selector"):
        await page.click(p["submit_selector"])
        result["submitted"] = p["submit_selector"]
    return result


async def _wait_for(p: dict) -> dict:
    page = await _get_page(p)
    await page.wait_for_selector(
        p["selector"], state=p.get("state", "visible"), timeout=p.get("timeout_ms", 15_000)
    )
    return {"found": p["selector"]}


async def _scroll(p: dict) -> dict:
    page = await _get_page(p)
    direction = p.get("direction", "down")
    amount = p.get("amount", 600)
    if direction == "bottom":
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    elif direction == "top":
        await page.evaluate("window.scrollTo(0, 0)")
    elif direction == "up":
        await page.evaluate(f"window.scrollBy(0, -{amount})")
    else:
        await page.evaluate(f"window.scrollBy(0, {amount})")
    return {"scrolled": direction}


async def _get_html(p: dict) -> str:
    page = await _get_page(p)
    el = await page.query_selector(p.get("selector", "body"))
    return "" if el is None else await el.inner_html()


async def _close(p: dict) -> dict:
    sid = p.get("session_id", "default")
    session = _sessions.pop(sid, None)
    if session:
        await session["browser"].close()
        await session["pw"].stop()
        return {"closed": sid}
    return {"closed": None, "reason": "session not found"}


async def close_all() -> None:
    for sid in list(_sessions):
        await _close({"session_id": sid})
