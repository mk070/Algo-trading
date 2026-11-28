"""
Agent 4: Technical Research Agent

Reads existing deterministic signals from DB (VCP status, EMA relationships, RSI, breakout).
NEVER calculates new signals via LLM.
NEVER invents support/resistance prices.
Only explains the existing deterministic output in plain English.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.ai.schemas import (
    AgentName,
    AIResponse,
    TechnicalResearchOutput,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a technical analysis communicator for an Indian equity swing-trading research platform.

You receive deterministic signal data computed by the platform's rules-based engine.
Your sole task is to explain this data in plain English for the platform user.

RULES:
1. Only explain the data provided. Never compute new indicators or invent price levels.
2. Never state a support or resistance price that is not explicitly in the input.
3. Never recommend buying or selling. Never set targets. Never advise on stops.
4. Use plain language that a non-technical investor can understand.
5. If signal data is absent, say the system has not generated a signal for this stock.
6. All outputs are informational research only — not trading directives.
7. Return valid JSON matching the required schema.
""".strip()

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "setup_pattern": {"type": ["string", "null"]},
        "plain_english_explanation": {"type": "string"},
        "key_levels_explained": {"type": "array", "items": {"type": "string"}},
        "signal_state": {"type": ["string", "null"]},
    },
    "required": ["plain_english_explanation", "key_levels_explained"],
}


def run_technical_research(
    symbol: str,
    provider,
    signal_data: Optional[Dict[str, Any]] = None,
    market: str = "IN",
) -> TechnicalResearchOutput:
    """
    Run the Technical Research agent.

    Args:
        symbol: Stock symbol.
        provider: An AIProvider instance.
        signal_data: Dict from Signal/Scan record (setup, trigger, stop, target1, state, score, atr, reasons_json).
        market: Market code.

    Returns:
        TechnicalResearchOutput.
    """
    if signal_data:
        reasons_raw = signal_data.get("reasons_json") or "[]"
        try:
            reasons = json.loads(reasons_raw) if isinstance(reasons_raw, str) else reasons_raw
        except Exception:
            reasons = []

        signal_summary = (
            f"Setup: {signal_data.get('setup', 'UNKNOWN')}\n"
            f"State: {signal_data.get('state', 'UNKNOWN')}\n"
            f"Trigger price: {signal_data.get('trigger', 'N/A')}\n"
            f"Stop price: {signal_data.get('stop', 'N/A')}\n"
            f"Target 1: {signal_data.get('target1', 'N/A')}\n"
            f"ATR: {signal_data.get('atr', 'N/A')}\n"
            f"RS rank: {signal_data.get('rs_rank', 'N/A')}\n"
            f"Score: {signal_data.get('score', 'N/A')}\n"
            f"Reasons: {', '.join(str(r) for r in reasons[:5])}\n"
            f"Valid until: {signal_data.get('valid_until', 'N/A')}"
        )
    else:
        signal_summary = "No active signal from the platform's rules-based engine for this stock."

    prompt = (
        f"Company: {symbol} | Market: {market}\n\n"
        f"Platform signal data (from deterministic rules-based engine — not for modification):\n"
        f"{signal_summary}\n\n"
        f"Provide a plain-English explanation of this signal data for the platform user. "
        f"Return your explanation as JSON matching the required schema."
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

    return TechnicalResearchOutput(
        agent_name=AgentName.TECHNICAL_RESEARCH,
        symbol=symbol,
        market=market,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=True,
        setup_pattern=parsed.get("setup_pattern") or (signal_data.get("setup") if signal_data else None),
        plain_english_explanation=parsed.get("plain_english_explanation", ""),
        key_levels_explained=parsed.get("key_levels_explained") or [],
        signal_state=parsed.get("signal_state") or (signal_data.get("state") if signal_data else None),
        source_is_deterministic_engine=True,
    )


def _make_error_output(
    symbol: str,
    market: str,
    provider,
    ai_resp: Optional[AIResponse] = None,
    latency: float = 0.0,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> TechnicalResearchOutput:
    return TechnicalResearchOutput(
        agent_name=AgentName.TECHNICAL_RESEARCH,
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
        plain_english_explanation="[Technical research unavailable]",
        source_is_deterministic_engine=True,
    )
