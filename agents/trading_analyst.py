"""
agents/trading_analyst.py — SEBI-style educational market analysis (no trade calls).
"""
from __future__ import annotations

import json

from config import settings
from models import TradingAnalysisOutput
from agents.base import BaseAgent


class TradingAnalystAgent(BaseAgent):
    name = "trading_analyst"
    model = settings.claude_model_fast
    max_tokens = 1024
    use_fast_model = True
    system_prompt = """
You are a market analysis assistant.

MANDATORY DISCLAIMER — add to every response (also set the "disclaimer" field to this exact text):
"This is educational analysis only, NOT investment advice.
Consult a SEBI-registered advisor before investing."

Analyze: RSI, moving averages, volume, news sentiment where data allows.
Never give exact buy/sell calls.
Never promise returns.

Return JSON only:
{
  "symbol": str,
  "trend": "bullish|bearish|neutral",
  "summary": str (2-3 sentences),
  "key_levels": {"support": number, "resistance": number},
  "risk_factors": list[str],
  "disclaimer": str
}
"""

    async def analyze(self, symbol: str, data: dict) -> dict:
        payload = json.dumps(data, default=str)[:14000]
        msg = f"Symbol: {symbol}\nMarket data (JSON):\n{payload}\nProduce the JSON analysis object."
        out = await self._call_claude_async(msg, TradingAnalysisOutput)
        return out.model_dump()
