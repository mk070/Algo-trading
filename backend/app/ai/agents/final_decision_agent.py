"""
Agent 6: Final Research Decision Agent

Inputs: all 5 prior agent outputs.
Output: WATCH | MONITOR | REJECT | INSUFFICIENT_DATA.

HARD RULES:
- Must NOT simply average confidence scores.
- Must NOT create BUY/SELL/execution instructions. is_execution_instruction is always False.
- Must explain what evidence would change the assessment.
- Persists as ai_research_assessments record (via orchestrator).
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
    FinalResearchOutput,
    MarketContextOutput,
    NewsIntelligenceOutput,
    ResearchStatus,
    RiskReviewOutput,
    TechnicalResearchOutput,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the final research decision agent for an Indian equity swing-trading research platform.

You receive a full research dossier compiled by five prior agents and must synthesise it into a single research status.

RESEARCH STATUS DEFINITIONS:
- WATCH: Compelling evidence warrants close monitoring; no immediate action
- MONITOR: Noteworthy developments present; track for potential changes
- REJECT: Adverse evidence (regulatory, financial, or risk) outweighs positives; remove from focus
- INSUFFICIENT_DATA: Critical data missing to make a meaningful assessment

HARD RULES:
1. Never output BUY, SELL, or any execution instruction.
2. Never average or score individual agents; weigh the actual evidence.
3. Always explain what specific new evidence would change the assessment.
4. If any HIGH-severity risk flag is present, escalate requires_human_review = true.
5. INSUFFICIENT_DATA means you cannot assess — not that the company is bad.
6. All outputs are informational research only — not trading directives.
7. Return valid JSON matching the required schema.
""".strip()

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "final_status": {
            "type": "string",
            "enum": ["WATCH", "MONITOR", "REJECT", "INSUFFICIENT_DATA"],
        },
        "confidence_basis": {"type": "string"},
        "what_would_change_assessment": {"type": "array", "items": {"type": "string"}},
        "requires_human_review": {"type": "boolean"},
        "human_review_reason": {"type": ["string", "null"]},
    },
    "required": [
        "final_status", "confidence_basis",
        "what_would_change_assessment", "requires_human_review",
    ],
}


def run_final_decision(
    symbol: str,
    provider,
    news_output: Optional[NewsIntelligenceOutput] = None,
    company_output: Optional[CompanyResearchOutput] = None,
    market_output: Optional[MarketContextOutput] = None,
    technical_output: Optional[TechnicalResearchOutput] = None,
    risk_output: Optional[RiskReviewOutput] = None,
    market: str = "IN",
) -> FinalResearchOutput:
    """
    Run the Final Research Decision agent.

    Returns:
        FinalResearchOutput with final_status, confidence_basis, evidence.
    """
    # Build dossier summary
    sections: List[str] = []

    if news_output and news_output.is_valid:
        sections.append(
            f"[NEWS] Materiality={news_output.materiality} | Sentiment={news_output.sentiment} | "
            f"Category={news_output.event_category} | Rumor={news_output.is_rumor}\n"
            f"  Summary: {news_output.summary[:250]}"
        )
    else:
        sections.append("[NEWS] Unavailable")

    if company_output and company_output.is_valid:
        sections.append(
            f"[COMPANY] Completeness={company_output.data_completeness} | "
            f"Bull points={len(company_output.bull_points)} | Bear points={len(company_output.bear_points)}\n"
            f"  Missing: {', '.join(company_output.missing_metrics[:4]) or 'none'}\n"
            f"  Bull: {'; '.join(company_output.bull_points[:2])}\n"
            f"  Bear: {'; '.join(company_output.bear_points[:2])}"
        )
    else:
        sections.append("[COMPANY] Unavailable")

    if market_output and market_output.is_valid:
        sections.append(
            f"[MARKET] Regime={market_output.index_regime} | Sector={market_output.sector_trend} | "
            f"Stale={market_output.data_staleness_warning or 'No'}"
        )
    else:
        sections.append("[MARKET] Unavailable")

    if technical_output and technical_output.is_valid:
        sections.append(
            f"[TECHNICAL] Setup={technical_output.setup_pattern} | State={technical_output.signal_state}\n"
            f"  {technical_output.plain_english_explanation[:200]}"
        )
    else:
        sections.append("[TECHNICAL] Unavailable")

    if risk_output and risk_output.is_valid:
        high_risks = [f for f in risk_output.risk_flags if f.severity == "HIGH"]
        sections.append(
            f"[RISK] Overall={risk_output.overall_risk_level} | "
            f"High-severity flags={len(high_risks)} | "
            f"Contradictions={len(risk_output.contradictions_found)}\n"
            f"  Flags: {'; '.join(f'{f.risk_type}: {f.description[:60]}' for f in risk_output.risk_flags[:3])}\n"
            f"  Missing info: {', '.join(risk_output.missing_information[:3]) or 'none'}"
        )
    else:
        sections.append("[RISK] Unavailable")

    prompt = (
        f"Research dossier for: {symbol} (Market: {market})\n\n"
        + "\n\n".join(sections)
        + "\n\nSynthesise this dossier into a final research status. "
          "Weigh the actual evidence. Do not average confidence scores. "
          "Return your decision as JSON matching the required schema."
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

    # Map status safely
    status_raw = str(parsed.get("final_status", "INSUFFICIENT_DATA")).upper()
    try:
        final_status = ResearchStatus(status_raw)
    except ValueError:
        final_status = ResearchStatus.INSUFFICIENT_DATA

    # Build supporting evidence from prior agents
    supporting_evidence: List[EvidenceRecord] = []
    for src_output in [news_output, company_output]:
        if src_output and src_output.is_valid and hasattr(src_output, "evidence"):
            supporting_evidence.extend(src_output.evidence[:2])

    # Auto-escalate human review for high risk
    requires_human_review = bool(parsed.get("requires_human_review", False))
    if risk_output and risk_output.is_valid:
        high_risks = [f for f in risk_output.risk_flags if f.severity == "HIGH"]
        if high_risks:
            requires_human_review = True

    return FinalResearchOutput(
        agent_name=AgentName.FINAL_DECISION,
        symbol=symbol,
        market=market,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=True,
        final_status=final_status,
        confidence_basis=str(parsed.get("confidence_basis", ""))[:800],
        supporting_evidence=supporting_evidence,
        what_would_change_assessment=parsed.get("what_would_change_assessment") or [],
        requires_human_review=requires_human_review,
        human_review_reason=parsed.get("human_review_reason"),
        is_execution_instruction=False,  # always False — hard rule
    )


def _make_error_output(
    symbol: str,
    market: str,
    provider,
    ai_resp: Optional[AIResponse] = None,
    latency: float = 0.0,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> FinalResearchOutput:
    return FinalResearchOutput(
        agent_name=AgentName.FINAL_DECISION,
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
        final_status=ResearchStatus.INSUFFICIENT_DATA,
        confidence_basis="AI analysis unavailable",
        is_execution_instruction=False,
    )
