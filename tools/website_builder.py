"""
tools/website_builder.py — Landing pages, portfolio, product pages, SEO tweaks.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from typing import Any

from config import settings


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "site").strip().lower())[:80].strip("-")
    return s or "site"


def _ws_dir() -> Path:
    return Path(settings.workspace_dir).resolve()


async def _write_html(subdir: str, filename: str, html: str) -> dict[str, Any]:
    base = _ws_dir() / "websites" / subdir
    base.mkdir(parents=True, exist_ok=True)
    path = base / filename
    path.write_text(html, encoding="utf-8")
    return {
        "html_path": str(path),
        "file_size_bytes": path.stat().st_size,
    }


async def _create_landing_page(p: dict[str, Any]) -> dict[str, Any]:
    from agents.website_generator import WebsiteGeneratorAgent

    name = str(p.get("business_name") or "Business").strip()
    tagline = str(p.get("tagline") or "")
    desc = str(p.get("description") or "")
    features = p.get("features") or []
    email = str(p.get("contact_email") or "")
    scheme = str(p.get("color_scheme") or "modern")
    feat_lines = "\n".join(f"- {x}" for x in features) if isinstance(features, list) else str(features)
    instruction = f"""Create a single-page landing site for:
Business: {name}
Tagline: {tagline}
Description: {desc}
Features:
{feat_lines}
Contact email: {email}
Color scheme theme: {scheme}
Include hero, features section, contact/footer."""
    agent = WebsiteGeneratorAgent()
    html = await agent.generate_html(instruction)
    slug = _slug(name)
    return await _write_html(slug, "index.html", html)


async def _create_portfolio(p: dict[str, Any]) -> dict[str, Any]:
    from agents.website_generator import WebsiteGeneratorAgent

    name = str(p.get("name") or "Portfolio").strip()
    profession = str(p.get("profession") or "")
    projects = p.get("projects") or []
    skills = p.get("skills") or []
    instruction = f"""Portfolio site for {name}, profession: {profession}.
Projects (JSON-ish): {projects}
Skills: {skills}
Sections: about, projects grid, skills, contact."""
    agent = WebsiteGeneratorAgent()
    html = await agent.generate_html(instruction)
    slug = _slug(name)
    return await _write_html(slug, "index.html", html)


async def _create_product_page(p: dict[str, Any]) -> dict[str, Any]:
    from agents.website_generator import WebsiteGeneratorAgent

    pname = str(p.get("product_name") or "Product").strip()
    instruction = f"""Product landing page for: {pname}
Description: {p.get("description", "")}
Price: {p.get("price", "")}
Features: {p.get("features", [])}
CTA: {p.get("cta_text", "Buy now")}"""
    agent = WebsiteGeneratorAgent()
    html = await agent.generate_html(instruction)
    slug = _slug(pname)
    return await _write_html(slug, "index.html", html)


async def _add_section(p: dict[str, Any]) -> dict[str, Any]:
    page_path = str(p.get("page_path") or "").strip()
    section_type = str(p.get("section_type") or "custom")
    content = p.get("content") or {}
    path = Path(page_path).resolve()
    ws = _ws_dir()
    if not str(path).startswith(str(ws)):
        raise ValueError("page_path must be under workspace_dir")
    html = path.read_text(encoding="utf-8")
    blob = html_lib.escape(json.dumps(content, ensure_ascii=False)[:8000])
    frag = f'<section data-type="{html_lib.escape(section_type)}"><pre>{blob}</pre></section>\n'
    if "</body>" in html:
        html = html.replace("</body>", frag + "</body>", 1)
    else:
        html += frag
    path.write_text(html, encoding="utf-8")
    return {"html_path": str(path), "file_size_bytes": path.stat().st_size}


async def _optimize_seo(p: dict[str, Any]) -> dict[str, Any]:
    page_path = str(p.get("page_path") or "").strip()
    keywords = p.get("keywords") or []
    meta_desc = str(p.get("meta_description") or "").strip()
    path = Path(page_path).resolve()
    ws = _ws_dir()
    if not str(path).startswith(str(ws)):
        raise ValueError("page_path must be under workspace_dir")
    html = path.read_text(encoding="utf-8")
    kw = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
    inject = f'<meta name="description" content="{meta_desc.replace(chr(34), "&quot;")}" />\n'
    inject += f'<meta name="keywords" content="{kw.replace(chr(34), "&quot;")}" />\n'
    if "</head>" in html:
        html = html.replace("</head>", inject + "</head>", 1)
    else:
        html = inject + html
    path.write_text(html, encoding="utf-8")
    return {
        "html_path": str(path),
        "file_size_bytes": path.stat().st_size,
    }


async def execute(action: str, params: dict[str, Any]) -> Any:
    a = (action or "").strip().lower()
    if a == "create_landing_page":
        return await _create_landing_page(params)
    if a == "create_portfolio":
        return await _create_portfolio(params)
    if a == "create_product_page":
        return await _create_product_page(params)
    if a == "add_section":
        return await _add_section(params)
    if a == "optimize_seo":
        return await _optimize_seo(params)
    raise ValueError(f"Unknown website_builder action: {action}")
