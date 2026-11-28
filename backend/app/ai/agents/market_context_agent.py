"""
Agent 3: Market Context Agent

Reads NIFTY regime, sector data from existing DB.
Does NOT make new data requests or fetch external data.
Timestamps all data clearly and marks stale data.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.ai.schemas import (
    AgentName,
    AIResponse,
    MarketContextOutput,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a market context analyst for an Indian equity swing-trading research platform.

You receive deterministic market regime data already computed by the platform.
Your task is to produce a plain-language interpretation of the market context.

RULES:
1. Only use the data provided. Never invent index values, dates, or regime classifications.
2. If a field is missing or stale, say so explicitly.
3. Never recommend buying or selling.
4. All outputs are informational research only — not trading directives.
5. Return valid JSON matching the required schema.
""".strip()

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "index_regime": {"type": ["string", "null"]},
        "regime_detail": {"type": ["string", "null"]},
        "sector_trend": {"type": ["string", "null"]},
        "macro_flags": {"type": "array", "items": {"type": "string"}},
        "data_staleness_warning": {"type": ["string", "null"]},
    },
    "required": ["index_regime", "macro_flags"],
}

_STALE_THRESHOLD_HOURS = 48


def run_market_context(
    symbol: str,
    provider,
    regime_data: Optional[Dict[str, Any]] = None,
    sector: Optional[str] = None,
    market: str = "IN",
) -> MarketContextOutput:
    """
    Run the Market Context agent.

    Args:
        symbol: Stock symbol.
        provider: An AIProvider instance.
        regime_data: Dict from latest Scan record (regime, session_date, regime_detail_json).
        sector: Sector string from Instrument record.
        market: Market code.

    Returns:
        MarketContextOutput.
    """
    # Build context summary
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    staleness_warning: Optional[str] = None

    regime_str = "No regime data available"
    regime_detail_str = ""
    data_as_of: Optional[datetime.datetime] = None

    if regime_data:
        regime_str = regime_data.get("regime", "UNKNOWN")
        detail_raw = regime_data.get("regime_detail_json")
        if detail_raw:
            try:
                detail_dict = json.loads(detail_raw) if isinstance(detail_raw, str) else detail_raw
                regime_detail_str = json.dumps(detail_dict)
            except Exception:
                regime_detail_str = str(detail_raw)[:200]

        session_date = regime_data.get("session_date")
        if session_date:
            if isinstance(session_date, str):
                try:
                    session_date = datetime.date.fromisoformat(session_date)
                except ValueError:
                    pass
            if isinstance(session_date, datetime.date):
                data_as_of = datetime.datetime.combine(session_date, datetime.time(0, 0), tzinfo=datetime.timezone.utc)
                age_hours = (now_utc - data_as_of).total_seconds() / 3600
                if age_hours > _STALE_THRESHOLD_HOURS:
                    staleness_warning = (
                        f"Market regime data is {age_hours:.0f} hours old "
                        f"(session date: {session_date}). Treat with caution."
                    )

    prompt = (
        f"Company: {symbol} | Market: {market} | Sector: {sector or 'Unknown'}\n\n"
        f"Market regime data from platform (deterministic engine output):\n"
        f"  Regime: {regime_str}\n"
        f"  Detail: {regime_detail_str[:300] if regime_detail_str else 'N/A'}\n"
        f"  Data as of: {data_as_of.date() if data_as_of else 'unknown'}\n"
        f"  Staleness: {staleness_warning or 'Within expected window'}\n\n"
        f"Return your market context interpretation as JSON matching the required schema."
    )

    t_start = time.perf_counter()
    ai_resp: AIResponse = provider.generate(
        prompt=prompt,
        system=_SYSTEM_PROMPT,
        schema=_OUTPUT_SCHEMA,
        timeout=30.0,
        max_tokens=384,
    )
    latency = time.perf_counter() - t_start

    if not ai_resp.success or not ai_resp.content:
        return _make_error_output(symbol, market, provider, ai_resp, latency)

    try:
        parsed = json.loads(ai_resp.content)
    except (json.JSONDecodeError, ValueError) as exc:
        return _make_error_output(
            symbol, market, provider, ai_resp, latency,
            error_code="INVALID_JSON", error_msg=str(exc),
        )

    return MarketContextOutput(
        agent_name=AgentName.MARKET_CONTEXT,
        symbol=symbol,
        market=market,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=True,
        index_regime=parsed.get("index_regime") or regime_str,
        regime_detail=parsed.get("regime_detail"),
        sector_trend=parsed.get("sector_trend"),
        macro_flags=parsed.get("macro_flags") or [],
        data_as_of=data_as_of,
        data_staleness_warning=staleness_warning or parsed.get("data_staleness_warning"),
    )


def _make_error_output(
    symbol: str,
    market: str,
    provider,
    ai_resp: Optional[AIResponse] = None,
    latency: float = 0.0,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> MarketContextOutput:
    return MarketContextOutput(
        agent_name=AgentName.MARKET_CONTEXT,
        symbol=symbol,
        market=market,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens if ai_resp else None,
        output_tokens=ai_resp.output_tokens if ai_resp else None,
        is_valid=False,
        error_code=error_code or (ai_resp.error_code if ai_resp else "UNKNOWN"),
        error_message=error_msg or (ai_resp.error_message if ai_resp else None),
        macro_flags=[],
    )
