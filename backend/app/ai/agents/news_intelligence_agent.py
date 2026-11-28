"""
Agent 1: News Intelligence Agent

Input: NewsEvent record + company metadata.
Output: NewsIntelligenceOutput (materiality, sentiment, category, key facts, evidence).

Materiality filter: ROUTINE_IMMATERIAL events are skipped unless force=True.
Input hash: sha256(symbol + headline + published_at + source_url) for deduplication.

Security: Only public market data and permitted filings are used in prompts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.ai.schemas import (
    AgentName,
    AIResponse,
    EvidenceRecord,
    EventCategory,
    MaterialityLevel,
    NewsIntelligenceOutput,
    SentimentLabel,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt (verbatim from benchmark SYSTEM_INSTRUCTION)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """
You are a financial news intelligence agent for an Indian equity swing-trading research platform.

Your task is to analyse a single corporate news event and return a structured JSON assessment.

RULES:
1. Only state facts that appear explicitly in the input headline and context. Never invent company names, prices, dates, or financial figures.
2. If information is unavailable, set the field to null or an empty list — do not fabricate.
3. Distinguish verified exchange filings (NSE/BSE) from media reports. Mark media-only items as UNVERIFIED.
4. Assess materiality strictly: use HIGH only for events that directly and immediately affect the stock's fundamental value or regulatory status.
5. This output is informational research only — not a trading directive.
6. Return valid JSON that conforms exactly to the requested schema.
""".strip()

# ---------------------------------------------------------------------------
# JSON schema for structured Gemini output
# ---------------------------------------------------------------------------
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "event_category": {
            "type": "string",
            "enum": ["EARNINGS", "REGULATORY", "MANAGEMENT", "ACQUISITION",
                     "LEGAL", "DIVIDEND", "RESTRUCTURING", "MACRO", "ANALYST", "OTHER"],
        },
        "sentiment": {
            "type": "string",
            "enum": ["POSITIVE", "NEGATIVE", "MIXED", "NEUTRAL"],
        },
        "materiality": {
            "type": "string",
            "enum": ["HIGH", "MEDIUM", "LOW", "ROUTINE_IMMATERIAL"],
        },
        "affected_companies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "summary": {"type": "string"},
        "key_facts": {
            "type": "array",
            "items": {"type": "string"},
        },
        "is_rumor": {"type": "boolean"},
        "requires_follow_up": {"type": "boolean"},
        "conflicting_sources": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["event_category", "sentiment", "materiality", "summary", "key_facts", "is_rumor"],
}


def _build_input_hash(symbol: str, headline: str, published_at: str, source_url: str) -> str:
    raw = f"{symbol}|{headline}|{published_at}|{source_url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_prompt(event_data: Dict[str, Any]) -> str:
    return (
        f"Analyse this corporate news event for Indian equity research:\n\n"
        f"Company symbol: {event_data.get('symbol', 'UNKNOWN')}\n"
        f"Headline: {event_data.get('title', '')}\n"
        f"Source: {event_data.get('source', 'unknown')}\n"
        f"Published: {event_data.get('published_at', 'unknown')}\n"
        f"Source URL: {event_data.get('url', 'N/A')}\n"
        f"Existing severity: {event_data.get('severity', 'UNKNOWN')}\n"
        f"Existing category: {event_data.get('category', 'UNKNOWN')}\n\n"
        f"Return your assessment as JSON matching the required schema."
    )


def run_news_intelligence(
    event_data: Dict[str, Any],
    provider,  # AIProvider instance
    *,
    force_routine: bool = False,
) -> NewsIntelligenceOutput:
    """
    Run the News Intelligence agent for a single news event.

    Args:
        event_data: Dict from NewsEvent model (id, symbol, title, source, published_at, url, severity, category).
        provider: An AIProvider instance (e.g. gemini_adapter).
        force_routine: If True, analyse even ROUTINE_IMMATERIAL events.

    Returns:
        NewsIntelligenceOutput (success or error state).
    """
    symbol = str(event_data.get("symbol", "UNKNOWN")).upper()
    event_id = int(event_data.get("id", 0))
    headline = str(event_data.get("title", ""))
    published_at = str(event_data.get("published_at", ""))
    source_url = str(event_data.get("url", ""))

    input_hash = _build_input_hash(symbol, headline, published_at, source_url)

    # --- Fast path: skip obviously routine events unless forced ---
    existing_category = str(event_data.get("category", "")).upper()
    if not force_routine and existing_category in ("ROUTINE", "BOARD_MEETING_GENERAL"):
        return _make_skipped_output(
            symbol=symbol,
            event_id=event_id,
            headline=headline,
            provider=provider,
            reason="ROUTINE_IMMATERIAL — skipped per materiality filter",
        )

    prompt = _build_prompt(event_data)
    t_start = time.perf_counter()
    ai_resp: AIResponse = provider.generate(
        prompt=prompt,
        system=_SYSTEM_PROMPT,
        schema=_OUTPUT_SCHEMA,
        timeout=45.0,
        max_tokens=512,
    )
    latency = time.perf_counter() - t_start

    if not ai_resp.success or not ai_resp.content:
        return _make_error_output(
            symbol=symbol,
            event_id=event_id,
            headline=headline,
            provider=provider,
            ai_resp=ai_resp,
            latency=latency,
        )

    # --- Parse JSON ---
    try:
        parsed = json.loads(ai_resp.content)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"[NewsAgent] JSON parse failed for event {event_id}: {exc}")
        return _make_error_output(
            symbol=symbol,
            event_id=event_id,
            headline=headline,
            provider=provider,
            ai_resp=ai_resp,
            latency=latency,
            error_code="INVALID_JSON",
            error_msg=str(exc),
        )

    # --- Build evidence record from the news source ---
    import datetime as dt
    evidence = []
    if source_url:
        try:
            pub_dt = dt.datetime.fromisoformat(published_at.replace("Z", "+00:00")) if published_at else None
        except ValueError:
            pub_dt = None
        evidence.append(EvidenceRecord(
            source_type="NEWS_EVENT",
            source_title=headline,
            source_url=source_url,
            pub_timestamp=pub_dt,
            extracted_passage=headline,
            verification_status=(
                VerificationStatus.VERIFIED
                if event_data.get("source", "").startswith("nse_")
                else VerificationStatus.UNVERIFIED
            ),
        ))

    # --- Map enum values safely ---
    def _safe_enum(cls, val, default):
        try:
            return cls(val.upper() if val else default)
        except (ValueError, AttributeError):
            return cls(default)

    return NewsIntelligenceOutput(
        agent_name=AgentName.NEWS_INTELLIGENCE,
        symbol=symbol,
        market=str(event_data.get("market", "IN")),
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=True,
        news_event_id=event_id,
        headline=headline,
        event_category=_safe_enum(EventCategory, parsed.get("event_category"), "OTHER"),
        sentiment=_safe_enum(SentimentLabel, parsed.get("sentiment"), "NEUTRAL"),
        materiality=_safe_enum(MaterialityLevel, parsed.get("materiality"), "LOW"),
        affected_companies=parsed.get("affected_companies") or [],
        summary=str(parsed.get("summary", ""))[:500],
        key_facts=parsed.get("key_facts") or [],
        evidence=evidence,
        requires_follow_up=bool(parsed.get("requires_follow_up", False)),
        is_rumor=bool(parsed.get("is_rumor", False)),
        conflicting_sources=parsed.get("conflicting_sources") or [],
    )


def _make_error_output(
    symbol: str,
    event_id: int,
    headline: str,
    provider,
    ai_resp: AIResponse,
    latency: float,
    error_code: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> NewsIntelligenceOutput:
    return NewsIntelligenceOutput(
        agent_name=AgentName.NEWS_INTELLIGENCE,
        symbol=symbol,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=round(latency, 3),
        input_tokens=ai_resp.input_tokens,
        output_tokens=ai_resp.output_tokens,
        is_valid=False,
        error_code=error_code or ai_resp.error_code,
        error_message=error_msg or ai_resp.error_message,
        news_event_id=event_id,
        headline=headline,
        event_category=EventCategory.OTHER,
        sentiment=SentimentLabel.NEUTRAL,
        materiality=MaterialityLevel.LOW,
        summary="[AI analysis unavailable]",
    )


def _make_skipped_output(
    symbol: str,
    event_id: int,
    headline: str,
    provider,
    reason: str,
) -> NewsIntelligenceOutput:
    return NewsIntelligenceOutput(
        agent_name=AgentName.NEWS_INTELLIGENCE,
        symbol=symbol,
        model_id=provider.model_id,
        provider=provider.provider_name,
        latency_sec=0.0,
        is_valid=True,
        error_code="SKIPPED",
        error_message=reason,
        news_event_id=event_id,
        headline=headline,
        event_category=EventCategory.OTHER,
        sentiment=SentimentLabel.NEUTRAL,
        materiality=MaterialityLevel.ROUTINE_IMMATERIAL,
        summary="[Skipped — routine immaterial event]",
    )
