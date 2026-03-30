"""
tools/__init__.py
─────────────────
Central tool registry. The Execution Agent calls run_tool() exclusively.
Add new tools here as phases expand — no changes needed in the agent.
"""
from models import ToolName
from tools import (
    filesystem,
    terminal,
    browser,
    http,
    email,
    google_sheets,
    market_data,
    website_builder,
    content_creator,
    finance,
    code_builder,
    phone,
    database,
    pdf_generator,
    image_analyzer,
    researcher,
    security_scanner,
    compliance,
    deployer,
    video_generator,
    notion,
    zoho_crm,
    google_calendar,
    tally,
    amazon_seller,
    meesho,
    whatsapp_commerce,
    zapier,
    hubspot,
    wordpress,
    shopify,
    linkedin,
    instagram,
    twitter,
    gem_portal,
)

REGISTRY: dict = {
    ToolName.FILESYSTEM: filesystem,
    ToolName.TERMINAL:   terminal,
    ToolName.BROWSER:    browser,    # Phase 2 ✓
    ToolName.HTTP:       http,       # Phase 2 ✓
    ToolName.EMAIL:      email,      # Phase 3 ✓
    ToolName.GOOGLE_SHEETS: google_sheets,
    ToolName.MARKET_DATA: market_data,
    ToolName.WEBSITE_BUILDER: website_builder,
    ToolName.CONTENT_CREATOR: content_creator,
    ToolName.FINANCE: finance,
    ToolName.CODE_BUILDER: code_builder,
    ToolName.PHONE: phone,
    ToolName.DATABASE: database,
    ToolName.PDF_GENERATOR: pdf_generator,
    ToolName.IMAGE_ANALYZER: image_analyzer,
    ToolName.RESEARCHER: researcher,
    ToolName.SECURITY_SCANNER: security_scanner,
    ToolName.COMPLIANCE: compliance,
    ToolName.DEPLOYER: deployer,
    ToolName.VIDEO_GENERATOR: video_generator,
    ToolName.NOTION: notion,
    ToolName.ZOHO_CRM: zoho_crm,
    ToolName.GOOGLE_CALENDAR: google_calendar,
    ToolName.TALLY: tally,
    ToolName.AMAZON_SELLER: amazon_seller,
    ToolName.MEESHO: meesho,
    ToolName.WHATSAPP_COMMERCE: whatsapp_commerce,
    ToolName.ZAPIER: zapier,
    ToolName.HUBSPOT: hubspot,
    ToolName.WORDPRESS: wordpress,
    ToolName.SHOPIFY: shopify,
    ToolName.LINKEDIN: linkedin,
    ToolName.INSTAGRAM: instagram,
    ToolName.TWITTER: twitter,
    ToolName.GEM_PORTAL: gem_portal,
}


async def run_tool(tool: ToolName, action: str, params: dict):
    # Custom tools (Phase 3 — dynamically built)
    if tool == ToolName.CUSTOM:
        custom_name: str = params.pop("_tool_name", "")
        if not custom_name:
            raise ValueError("Custom tool step must include '_tool_name' in params")
        from tools.registry import run_custom_tool
        return await run_custom_tool(custom_name, action, params)

    module = REGISTRY.get(tool)
    if module is None:
        raise NotImplementedError(
            f"Tool '{tool}' is not yet available. "
            f"Active built-in tools: {[t.value for t in REGISTRY]}"
        )
    return await module.execute(action, params)
