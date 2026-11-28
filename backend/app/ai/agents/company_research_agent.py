"""
Agent 2: Company Research Agent

Input: Verified NewsIntelligenceOutput + fundamentals from DB.
Output: CompanyResearchOutput with fundamental checks and bull/bear evidence.

NEVER fabricates financial figures. Returns NOT_AVAILABLE for missing metrics.
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
    EvidenceRecord,
    FundamentalCheck,
    NewsIntelligenceOutput,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a company research analyst for an Indian equity swing-trading research platform.

You receive:
1. A news intelligence summary about a company.
2. Verified fundamental data from the platform database (may be partial or absent).

Your task is to produce a structured fundamental research assessment.

RULES:
1. Use ONLY the fundamental data provided. Never invent or estimate financial metrics.
2. If a metric is missing, set its value to null and status to UNKNOWN.
3. Produce balanced bull and bear points based solely on the data supplied.
4. Never recommend buying or selling. Never set price targets. Never advise on position sizing.
5. All outputs are informational research only — not trading directives.
6. Return valid JSON that conforms exactly to the requested schema.
""".strip()

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": ["string", "null"]},
        "sector": {"type": ["string", "null"]},
        "industry": {"type": ["string", "null"]},
        "fundamental_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "value": {"type": ["string", "null"]},
                    "status": {"type": "string", "enum": ["GREEN", "AMBER", "RED", "UNKNOWN"]},
                    "note": {"type": "string"},
                },
                "required": ["metric", "status", "note"],
            },
        },
        "bull_points": {"type": "array", "items": {"type": "string"}},
        "bear_points": {"type": "array", "items": {"type": "string"}},
        "data_completeness": {"type": "string", "enum": ["COMPLETE", "PARTIAL", "NONE"]},
        "missing_metrics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fundamental_checks", "bull_points", "bear_points", "data_completeness", "missing_metrics"],
}


def _build_prompt(
    news_output: NewsIntelligenceOutput,
    fundamentals: Optional[Dict[str, Any]],
    instrument_meta: Optional[Dict[str, Any]],
) -> str:
    fund_str = "No fundamental data available in platform database."
    if fundamentals:
        # Only pass the actual DB-verified numbers
        fund_str = json.dumps({
            k: v for k, v in fundamentals.items()
            if k in (
                "revenue_yoy", "profit_yoy", "op_margin", "roce", "roe",
                "debt_equity", "interest_coverage", "pe", "sector_median_pe",
                "promoter_holding", "pledge_pct", "completeness", "as_of", "source",
            ) and v is not None
        }, indent=2)

    meta_str = ""
    if instrument_meta:
        meta_str = (
            f"Sector: {instrument_meta.get('sector', 'Unknown')}\n"
            f"Industry: {instrument_meta.get('industry', 'Unknown')}\n"
            f"Company name: {instrument_meta.get('name', news_output.symbol)}\n"
        )

    return (
        f"Company: {news_output.symbol}\n"
        f"{meta_str}\n"
        f"Recent news event:\n"
        f"  Category: {news_output.event_category}\n"
        f"  Sentiment: {news_output.sentiment}\n"
        f"  Materiality: {news_output.materiality}\n"
        f"  Summary: {news_output.summary}\n"
        f"  Key facts: {', '.join(news_output.key_facts[:5])}\n\n"
        f"Platform fundamental data (DB-verified, may be partial):\n{fund_str}\n\n"
        f"Return your company research assessment as JSON matching the required schema. "
        f"Use UNKNOWN for any metric not supplied above."
    )


def run_company_research(
    news_output: NewsIntelligenceOutput,
    provider,
    fundamentals: Optional[Dict[str, Any]] = None,
    instrument_meta: Optional[Dict[str, Any]] = None,
) -> CompanyResearchOutput:
    """
    Run the Company Research agent.

    Args:
        news_output: Output from the News Intelligence agent (must be valid).
        provider: An AIProvider instance.
        fundamentals: Dict of fundamental metrics from DB (FundamentalSnapshot).
        instrument_meta: Dict with name, sector, industry from Instrument model.

    Returns:
        CompanyResearchOutput.
    """
    symbol = news_output.symbol

    if not news_output.is_valid:
        return _make_error_output(symbol, provider, error_msg="Cannot run company research on invalid news output")

    prompt = _build_prompt(news_output, fundamentals, instrument_meta)
    t_start = time.perf_counter()
    ai_resp: AIResponse = provider.generate(
        prompt=prompt,
        system=_SYSTEM_PROMPT,
        schema=_OUTPUT_SCHEMA,
        timeout=45.0,
        max_tokens=768,
    )
    latency = time.perf_counter() - t_start

    if not ai_resp.success or not ai_resp.content:
        return _make_error_output(symbol, provider, ai_resp=ai_resp, latency=latency)

    try:
        parsed = json.loads(ai_resp.content)
    except (json.JSONDecodeError, ValueError) as exc:
        return _make_error_output(
            symbol, provider, ai_resp=ai_resp, latency=latency,
            error_code="INVALID_JSON", error_msg=str(exc),
        )

    # Build fundamental checks
    checks: List[FundamentalCheck] = []
    for item in parsed.get("fundamental_checks") or []:
        checks.append(FundamentalCheck(
            metric=str(item.get("metric", "unknown")),
            value=item.get("value"),
            status=str(item.get("status", "UNKNOWN")),
            note=str(item.get("note", "")),
        ))

    # Build evidence from fundamentals source
    evidence: List[EvidenceRecord] = []
    if fundamentals and fundamentals.get("source"):
        evidence.append(EvidenceRecord(
            source_type="FUNDAMENTAL",
            source_title=f"Fundamental Snapshot — {fundamentals.get('source', 'platform')}",
            pub_timestamp=None,
            extracted_passage=f"as_of: {fundamentals.get('as_of', 'unknown')}",
            verification_status=VerificationStatus.VERIFIED,
        ))

    return CompanyResearchOutput(
        agent_name=AgentName.COMPANY_RESEARCH,
        symbol=symbol,
        market=news_output.market,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=True,
        company_name=parsed.get("company_name") or instrument_meta.get("name") if instrument_meta else None,
        sector=parsed.get("sector") or (instrument_meta.get("sector") if instrument_meta else None),
        industry=parsed.get("industry") or (instrument_meta.get("industry") if instrument_meta else None),
        fundamental_checks=checks,
        bull_points=parsed.get("bull_points") or [],
        bear_points=parsed.get("bear_points") or [],
        evidence=evidence,
        data_completeness=parsed.get("data_completeness", "PARTIAL"),
        missing_metrics=parsed.get("missing_metrics") or [],
    )


def _make_error_output(
    symbol: str,
    provider,
    ai_resp: Optional[AIResponse] = None,
    latency: float = 0.0,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> CompanyResearchOutput:
    return CompanyResearchOutput(
        agent_name=AgentName.COMPANY_RESEARCH,
        symbol=symbol,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens if ai_resp else None,
        output_tokens=ai_resp.output_tokens if ai_resp else None,
        is_valid=False,
        error_code=error_code or (ai_resp.error_code if ai_resp else "UNKNOWN"),
        error_message=error_msg or (ai_resp.error_message if ai_resp else None),
        data_completeness="NONE",
    )
