"""
tools/market_data.py — Yahoo Finance chart + quoteSummary (no API key).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from security.sandbox import validate_market_symbol, validate_market_symbols_batch

CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
SUMMARY = "https://query1.finance.yahoo.com/v10/finance/quoteSummary"

_PERIOD_MAP = {
    "1d": ("1d", "5m"),
    "1w": ("5d", "1h"),
    "1m": ("1mo", "1d"),
    "3m": ("3mo", "1d"),
    "1y": ("1y", "1wk"),
}

# Curated NSE symbols for lightweight screener (Yahoo .NS)
_SCREENER_UNIVERSE = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "ITC.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "AXISBANK.NS",
    "ASIANPAINT.NS",
    "MARUTI.NS",
    "TITAN.NS",
]


async def _get_json(url: str, params: Optional[dict] = None) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PantheonCOO/2.0; +https://pantheon.example)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _chart_result(data: dict) -> Optional[dict]:
    try:
        return data["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return None


async def _get_quote(symbol: str) -> dict[str, Any]:
    validate_market_symbol(symbol)
    url = f"{CHART}/{symbol}"
    data = await _get_json(url, {"interval": "1d", "range": "5d"})
    res = _chart_result(data)
    if not res:
        return {"symbol": symbol, "error": "no data"}
    meta = res.get("meta") or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    vol = meta.get("regularMarketVolume")
    change = None
    change_pct = None
    if price is not None and prev:
        change = round(float(price) - float(prev), 4)
        change_pct = round(100.0 * (float(price) - float(prev)) / float(prev), 4)
    return {
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "volume": vol,
    }


async def _get_history(symbol: str, period: str) -> dict[str, Any]:
    validate_market_symbol(symbol)
    p = (period or "1m").lower()
    if p not in _PERIOD_MAP:
        raise ValueError(f"period must be one of: {list(_PERIOD_MAP)}")
    rge, interval = _PERIOD_MAP[p]
    url = f"{CHART}/{symbol}"
    data = await _get_json(url, {"interval": interval, "range": rge})
    res = _chart_result(data)
    if not res:
        return {"symbol": symbol, "period": p, "bars": []}
    ts = res.get("timestamp") or []
    quotes = (res.get("indicators") or {}).get("quote") or [{}]
    q0 = quotes[0] if quotes else {}
    opens = q0.get("open") or []
    highs = q0.get("high") or []
    lows = q0.get("low") or []
    closes = q0.get("close") or []
    vols = q0.get("volume") or []
    bars = []
    for i, t in enumerate(ts):
        def _at(arr, idx):
            if not arr or idx >= len(arr):
                return None
            return arr[idx]

        bars.append(
            {
                "date": t,
                "open": _at(opens, i),
                "high": _at(highs, i),
                "low": _at(lows, i),
                "close": _at(closes, i),
                "volume": _at(vols, i),
            }
        )
    return {"symbol": symbol, "period": p, "bars": bars}


async def _get_news(symbol_or_query: str, limit: int = 10) -> dict[str, Any]:
    from security.sandbox import validate_market_news_query

    q = validate_market_news_query(symbol_or_query)
    sym = q.upper().strip()
    try:
        sym = validate_market_symbol(sym)
    except Exception:
        sym = "^NSEI"
    modules = "news"
    url = f"{SUMMARY}/{sym}"
    data = await _get_json(url, {"modules": modules})
    try:
        result = data["quoteSummary"]["result"][0]
        news = result.get("news") or []
    except (KeyError, IndexError, TypeError):
        news = []
    out = []
    for item in news[: max(1, min(limit, 50))]:
        out.append(
            {
                "headline": (item.get("title") or "")[:500],
                "source": item.get("publisher") or "",
                "url": item.get("link") or "",
                "sentiment": "n/a",
            }
        )
    return {"query": symbol_or_query, "items": out}


async def _quote_summary_mini(symbol: str) -> dict[str, Any]:
    validate_market_symbol(symbol)
    url = f"{SUMMARY}/{symbol}"
    data = await _get_json(
        url,
        {"modules": "defaultKeyStatistics,summaryDetail,financialData,price"},
    )
    try:
        r0 = data["quoteSummary"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return {}
    dk = r0.get("defaultKeyStatistics") or {}
    fd = r0.get("financialData") or {}
    sd = r0.get("summaryDetail") or {}
    pe = None
    if dk.get("trailingPE") and dk["trailingPE"].get("raw") is not None:
        pe = dk["trailingPE"]["raw"]
    elif sd.get("trailingPE") and sd["trailingPE"].get("raw") is not None:
        pe = sd["trailingPE"]["raw"]
    mcap = None
    if fd.get("totalCash") is not None:
        pass
    if dk.get("marketCap") and dk["marketCap"].get("raw") is not None:
        mcap = dk["marketCap"]["raw"]
    elif fd.get("totalRevenue") is not None:
        if fd.get("marketCap") and isinstance(fd["marketCap"], dict):
            mcap = fd["marketCap"].get("raw")
    return {"pe": pe, "market_cap": mcap, "symbol": symbol}


async def _get_screener(filters: dict[str, Any]) -> dict[str, Any]:
    pe_lt = filters.get("pe_lt")
    mcap_gt = filters.get("market_cap_gt")
    syms = validate_market_symbols_batch(list(_SCREENER_UNIVERSE[:10]))

    async def one(sym: str):
        try:
            return await _quote_summary_mini(sym)
        except Exception:
            return {"symbol": sym, "pe": None, "market_cap": None}

    rows = await asyncio.gather(*[one(s) for s in syms])
    matched = []
    for row in rows:
        pe = row.get("pe")
        mcap = row.get("market_cap")
        ok = True
        if pe_lt is not None and pe is not None:
            ok = ok and float(pe) < float(pe_lt)
        if mcap_gt is not None and mcap is not None:
            ok = ok and float(mcap) >= float(mcap_gt)
        elif mcap_gt is not None and mcap is None:
            ok = False
        if ok and row.get("symbol"):
            matched.append(
                {
                    "symbol": row["symbol"],
                    "pe": pe,
                    "market_cap": mcap,
                }
            )
    return {"filters": filters, "matches": matched}


async def _get_indices() -> dict[str, Any]:
    indices = {
        "NIFTY50": "^NSEI",
        "SENSEX": "^BSESN",
        "BANKNIFTY": "^NSEBANK",
    }
    out = {}
    for name, sym in indices.items():
        try:
            q = await _get_quote(sym)
            out[name] = {
                "symbol": sym,
                "price": q.get("price"),
                "change_pct": q.get("change_pct"),
            }
        except Exception as e:
            out[name] = {"symbol": sym, "error": str(e)}
    return out


async def execute(action: str, params: dict[str, Any]) -> Any:
    a = (action or "").strip().lower()
    if a == "get_quote":
        return await _get_quote(str(params.get("symbol", "")).strip())
    if a == "get_history":
        return await _get_history(
            str(params.get("symbol", "")).strip(),
            str(params.get("period", "1m")).strip(),
        )
    if a == "get_news":
        return await _get_news(
            str(params.get("query", "")).strip(),
            int(params.get("limit") or 10),
        )
    if a == "get_screener":
        f = params.get("filters") or {}
        if not isinstance(f, dict):
            raise ValueError("get_screener requires filters dict")
        return await _get_screener(f)
    if a == "get_indices":
        return await _get_indices()
    raise ValueError(f"Unknown market_data action: {action}")
