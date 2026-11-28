"""
Agent 5: Risk Review Agent

Receives outputs from agents 1–4 and independently challenges findings.
Can downgrade or block research.
Missing data = missing_information, not a negative signal.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.ai.schemas import (
    AgentName,
    AIResponse,
    CompanyResearchOutput,
    MarketContextOutput,
    NewsIntelligenceOutput,
    RiskFlag,
    RiskReviewOutput,
    TechnicalResearchOutput,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are an independent risk review analyst for an Indian equity swing-trading research platform.

You receive outputs from four prior research agents and must independently challenge their findings.

RULES:
1. Identify contradictions between sources — do not rubber-stamp prior agents.
2. Flag missing data as missing_information, NOT as a negative signal.
3. Identify: conflicting sources, stale data, missing data, downside news, regulatory risk, earnings proximity.
4. If you find a compelling reason to downgrade the research status, say so explicitly.
5. Never recommend buying or selling. Never set prices. Never advise on positions.
6. All outputs are informational research only — not trading directives.
7. Return valid JSON matching the required schema.
""".strip()

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk_type": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                },
                "required": ["risk_type", "description", "severity"],
            },
        },
        "contradictions_found": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "downgraded_from": {"type": ["string", "null"]},
        "overall_risk_level": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
    },
    "required": ["risk_flags", "contradictions_found", "missing_information", "overall_risk_level"],
}


def run_risk_review(
    symbol: str,
    provider,
    news_output: Optional[NewsIntelligenceOutput] = None,
    company_output: Optional[CompanyResearchOutput] = None,
    market_output: Optional[MarketContextOutput] = None,
    technical_output: Optional[TechnicalResearchOutput] = None,
    market: str = "IN",
) -> RiskReviewOutput:
    """
    Run the Risk Review agent across all prior agent outputs.

    Returns:
        RiskReviewOutput with risk flags, contradictions, missing info.
    """
    # Build a summary of prior agents' outputs for the prompt
    sections: List[str] = []

    if news_output and news_output.is_valid:
        sections.append(
            f"[News Intelligence]\n"
            f"  Materiality: {news_output.materiality}\n"
            f"  Sentiment: {news_output.sentiment}\n"
            f"  Is rumor: {news_output.is_rumor}\n"
            f"  Summary: {news_output.summary[:200]}\n"
            f"  Conflicting sources: {', '.join(news_output.conflicting_sources) or 'none'}\n"
            f"  Requires follow-up: {news_output.requires_follow_up}"
        )
    else:
        sections.append("[News Intelligence]\n  Status: UNAVAILABLE or INVALID")

    if company_output and company_output.is_valid:
        red_checks = [c for c in company_output.fundamental_checks if c.status == "RED"]
        sections.append(
            f"[Company Research]\n"
            f"  Data completeness: {company_output.data_completeness}\n"
            f"  Missing metrics: {', '.join(company_output.missing_metrics) or 'none'}\n"
            f"  Red flags: {', '.join(c.metric for c in red_checks) or 'none'}\n"
            f"  Bear points: {len(company_output.bear_points)}"
        )
    else:
        sections.append("[Company Research]\n  Status: UNAVAILABLE or INVALID")

    if market_output and market_output.is_valid:
        sections.append(
            f"[Market Context]\n"
            f"  Regime: {market_output.index_regime}\n"
            f"  Sector trend: {market_output.sector_trend}\n"
            f"  Staleness warning: {market_output.data_staleness_warning or 'none'}\n"
            f"  Macro flags: {', '.join(market_output.macro_flags) or 'none'}"
        )
    else:
        sections.append("[Market Context]\n  Status: UNAVAILABLE or INVALID")

    if technical_output and technical_output.is_valid:
        sections.append(
            f"[Technical Research]\n"
            f"  Setup: {technical_output.setup_pattern}\n"
            f"  Signal state: {technical_output.signal_state}\n"
            f"  Explanation: {technical_output.plain_english_explanation[:200]}"
        )
    else:
        sections.append("[Technical Research]\n  Status: UNAVAILABLE or INVALID")

    prompt = (
        f"Company: {symbol} | Market: {market}\n\n"
        f"Prior agent summaries to review:\n\n"
        + "\n\n".join(sections)
        + "\n\nIdentify risks, contradictions, and missing information. "
          "Return your risk review as JSON matching the required schema."
    )

    t_start = time.perf_counter()
    ai_resp: AIResponse = provider.generate(
        prompt=prompt,
        system=_SYSTEM_PROMPT,
        schema=_OUTPUT_SCHEMA,
        timeout=45.0,
        max_tokens=640,
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

    flags: List[RiskFlag] = []
    for item in parsed.get("risk_flags") or []:
        flags.append(RiskFlag(
            risk_type=str(item.get("risk_type", "UNKNOWN")),
            description=str(item.get("description", "")),
            severity=str(item.get("severity", "MEDIUM")),
        ))

    return RiskReviewOutput(
        agent_name=AgentName.RISK_REVIEW,
        symbol=symbol,
        market=market,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=True,
        risk_flags=flags,
        contradictions_found=parsed.get("contradictions_found") or [],
        missing_information=parsed.get("missing_information") or [],
        downgraded_from=parsed.get("downgraded_from"),
        overall_risk_level=parsed.get("overall_risk_level", "MEDIUM"),
    )


def _make_error_output(
    symbol: str,
    market: str,
    provider,
    ai_resp: Optional[AIResponse] = None,
    latency: float = 0.0,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> RiskReviewOutput:
    return RiskReviewOutput(
        agent_name=AgentName.RISK_REVIEW,
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
        overall_risk_level="MEDIUM",
    )
