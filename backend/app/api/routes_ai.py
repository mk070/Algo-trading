"""
AI Research Agent API Routes

Endpoints (all protected via existing `verify_token` auth dependency in main.py):

  GET  /api/ai/status                     — provider eligibility + quota status + agent flags
  GET  /api/ai/news/{event_id}            — get cached AI analysis of a news event
  POST /api/ai/news/{event_id}/analyze    — trigger analysis (quota-gated)
  GET  /api/ai/research/{symbol}          — get latest AI assessment for symbol
  POST /api/ai/research/{symbol}/analyze  — trigger full 6-agent research (quota-gated)
  GET  /api/ai/research/{symbol}/full     — full 6-agent research (cached)
  GET  /api/ai/research/{symbol}/history  — prior assessments with timestamps

Feature flags default OFF — no agent runs unless explicitly enabled in .env:
  AI_AGENTS_ENABLED=true
  AI_GEMINI_ENABLED=true
  AI_NEWS_AGENT_ENABLED=true (etc.)

NVIDIA hosted API is for offline evaluation ONLY — not used in live routes.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.ai.quota_guard import quota_guard

logger = logging.getLogger(__name__)
router = APIRouter()

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-&]{1,20}$")


def _validate_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    if not _SYMBOL_RE.match(clean):
        raise HTTPException(status_code=422, detail="Invalid stock symbol format")
    return clean


# ---------------------------------------------------------------------------
# Status endpoint (never blocked by feature flags — always available)
# ---------------------------------------------------------------------------

@router.get("/ai/status", tags=["AI Research"])
def get_ai_status(db: Session = Depends(get_db)):
    """
    Returns AI provider eligibility, feature flag state, and current quota usage.
    Always available regardless of feature flags (does not expose credentials).
    """
    status = quota_guard.get_status(db=db)
    return {
        "ai_agents_enabled": status.enabled,
        "gemini_enabled": status.gemini_enabled,
        "nvidia_policy": "OFFLINE_DEV_EVALUATION_ONLY",
        "zero_cost_only": status.zero_cost_only,
        "agent_flags": status.agent_flags,
        "quota": {
            "daily_limit": status.daily_limit,
            "per_minute_limit": status.per_minute_limit,
            "used_today": status.used_today,
            "successful_today": status.successful_today,
            "failed_today": status.failed_today,
            "used_this_minute": status.used_this_minute,
            "remaining_today": status.remaining_today,
            "quota_exhausted": status.quota_exhausted,
            "exhausted_at": status.exhausted_at.isoformat() if status.exhausted_at else None,
        },
        "provider_status": status.provider_status,
        "blocked_free_tier_models": ["gemini-4-hydrogen", "gemini-3.8-flash"],
        "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
    }


# ---------------------------------------------------------------------------
# News event analysis
# ---------------------------------------------------------------------------

@router.get("/ai/news/{event_id}", tags=["AI Research"])
def get_news_ai_analysis(
    event_id: int = ApiPath(..., gt=0),
    db: Session = Depends(get_db),
):
    """Get cached AI analysis for a news event (does not consume quota)."""
    try:
        from app.ai.models import AiAgentExecution
        row = (
            db.query(AiAgentExecution)
            .filter(
                AiAgentExecution.agent_name == "news_intelligence",
                AiAgentExecution.input_record_ids.contains(f"[{event_id}]"),
                AiAgentExecution.is_valid.is_(True),
            )
            .order_by(AiAgentExecution.generated_at.desc())
            .first()
        )
        if not row:
            return {"status": "NOT_ANALYZED", "event_id": event_id, "message": "No AI analysis found for this event."}

        output = json.loads(row.output_json) if row.output_json else {}
        return {
            "status": "OK",
            "event_id": event_id,
            "agent_name": row.agent_name,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            "model_id": row.model_id,
            "latency_sec": row.latency_sec,
            "analysis": output,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
        }
    except Exception as exc:
        logger.error(f"[routes_ai] get_news_ai_analysis error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error retrieving AI analysis")


@router.post("/ai/news/{event_id}/analyze", tags=["AI Research"])
def trigger_news_analysis(
    event_id: int = ApiPath(..., gt=0),
    db: Session = Depends(get_db),
):
    """Trigger AI analysis for a news event (flag-gated & quota-gated)."""
    status = quota_guard.get_status(db=db)
    if not status.enabled:
        return _disabled_response("AI agents are disabled (AI_AGENTS_ENABLED=false)")
    if not status.gemini_enabled:
        return _disabled_response("Gemini is disabled (AI_GEMINI_ENABLED=false)")
    if not quota_guard.is_agent_enabled("news_intelligence"):
        return _disabled_response("News Intelligence agent is disabled (AI_NEWS_AGENT_ENABLED=false)")
    if status.quota_exhausted:
        return _quota_exhausted_response(status)

    from app.models import NewsEvent
    event = db.query(NewsEvent).filter(NewsEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"News event {event_id} not found")

    try:
        from app.ai.orchestrator import run_news_intelligence
        result = run_news_intelligence(news_event_id=event_id, db=db)
        if result is None:
            return _disabled_response("Request blocked by quota guard or feature flag")
        return {
            "status": "OK" if result.is_valid else "ANALYSIS_ERROR",
            "event_id": event_id,
            "agent_name": result.agent_name,
            "is_valid": result.is_valid,
            "materiality": result.materiality,
            "sentiment": result.sentiment,
            "summary": result.summary,
            "latency_sec": result.latency_sec,
            "error_code": result.error_code,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
        }
    except Exception as exc:
        logger.error(f"[routes_ai] trigger_news_analysis error: {exc}")
        raise HTTPException(status_code=500, detail="Analysis failed")


# ---------------------------------------------------------------------------
# Symbol research
# ---------------------------------------------------------------------------

@router.get("/ai/research/{symbol}", tags=["AI Research"])
def get_research_assessment(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Get the latest AI research assessment for a symbol (does not consume quota)."""
    clean_symbol = _validate_symbol(symbol)
    try:
        from app.ai.models import AiResearchAssessment
        row = (
            db.query(AiResearchAssessment)
            .filter(
                AiResearchAssessment.symbol == clean_symbol,
                AiResearchAssessment.superseded_by.is_(None),
            )
            .order_by(AiResearchAssessment.generated_at.desc())
            .first()
        )
        if not row:
            return {"status": "NOT_ANALYZED", "symbol": clean_symbol, "message": "No AI research assessment found."}

        evidence = json.loads(row.evidence_json) if row.evidence_json else []
        risks = json.loads(row.risks_json) if row.risks_json else []
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "final_status": row.final_status,
            "summary": row.summary,
            "evidence": evidence,
            "what_would_change": risks,
            "requires_human_review": row.requires_human_review,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
        }
    except Exception as exc:
        logger.error(f"[routes_ai] get_research_assessment error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/ai/research/{symbol}/analyze", tags=["AI Research"])
def trigger_full_research(
    symbol: str,
    news_event_id: Optional[int] = Query(default=None, gt=0, description="Seed the analysis from a specific news event"),
    market: str = Query(default="IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Trigger full 6-agent research for a symbol (flag-gated & quota-gated)."""
    clean_symbol = _validate_symbol(symbol)
    status = quota_guard.get_status(db=db)
    if not status.enabled:
        return _disabled_response("AI agents are disabled (AI_AGENTS_ENABLED=false)")
    if not status.gemini_enabled:
        return _disabled_response("Gemini is disabled (AI_GEMINI_ENABLED=false)")
    if not any(status.agent_flags.values()):
        return _disabled_response("All individual AI agent flags are disabled")
    if status.quota_exhausted:
        return _quota_exhausted_response(status)

    try:
        from app.ai.orchestrator import run_full_research
        result = run_full_research(
            symbol=clean_symbol,
            db=db,
            news_event_id=news_event_id,
            market=market,
        )
        final = result.get("final_decision")
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "assessment_id": result.get("assessment_id"),
            "final_status": final.get("final_status") if final else None,
            "summary": final.get("confidence_basis") if final else None,
            "requires_human_review": final.get("requires_human_review") if final else None,
            "agents_run": [
                k for k, v in result.items()
                if v is not None and k not in ("symbol", "market", "assessment_id")
            ],
            "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
        }
    except Exception as exc:
        logger.error(f"[routes_ai] trigger_full_research error for {clean_symbol}: {exc}")
        raise HTTPException(status_code=500, detail="Research failed")


@router.get("/ai/research/{symbol}/full", tags=["AI Research"])
def get_full_research_detail(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Return cached per-agent outputs for a symbol (does not consume quota)."""
    clean_symbol = _validate_symbol(symbol)
    try:
        from app.ai.models import AiAgentExecution
        rows = (
            db.query(AiAgentExecution)
            .filter(
                AiAgentExecution.symbol == clean_symbol,
                AiAgentExecution.is_valid.is_(True),
            )
            .order_by(AiAgentExecution.generated_at.desc())
            .limit(18)
            .all()
        )
        if not rows:
            return {"status": "NOT_ANALYZED", "symbol": clean_symbol}

        by_agent: Dict[str, Any] = {}
        for row in rows:
            if row.agent_name not in by_agent:
                by_agent[row.agent_name] = {
                    "agent_name": row.agent_name,
                    "generated_at": row.generated_at.isoformat() if row.generated_at else None,
                    "model_id": row.model_id,
                    "latency_sec": row.latency_sec,
                    "output": json.loads(row.output_json) if row.output_json else {},
                }
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "agents": by_agent,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
        }
    except Exception as exc:
        logger.error(f"[routes_ai] get_full_research_detail error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ai/research/{symbol}/history", tags=["AI Research"])
def get_research_history(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return prior research assessments for a symbol with timestamps."""
    clean_symbol = _validate_symbol(symbol)
    try:
        from app.ai.models import AiResearchAssessment
        rows = (
            db.query(AiResearchAssessment)
            .filter(AiResearchAssessment.symbol == clean_symbol)
            .order_by(AiResearchAssessment.generated_at.desc())
            .limit(limit)
            .all()
        )
        history = [
            {
                "id": row.id,
                "final_status": row.final_status,
                "summary": row.summary,
                "requires_human_review": row.requires_human_review,
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
                "superseded_by": row.superseded_by,
            }
            for row in rows
        ]
        return {
            "status": "OK",
            "symbol": clean_symbol,
            "count": len(history),
            "history": history,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
        }
    except Exception as exc:
        logger.error(f"[routes_ai] get_research_history error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _disabled_response(reason: str) -> Dict[str, Any]:
    return {
        "status": "DISABLED",
        "reason": reason,
        "how_to_enable": (
            "Set AI_AGENTS_ENABLED=true, AI_GEMINI_ENABLED=true, and desired "
            "AI_*_AGENT_ENABLED=true flags in .env (verify free-tier terms first)."
        ),
        "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
    }


def _quota_exhausted_response(status) -> Dict[str, Any]:
    return {
        "status": "QUOTA_EXHAUSTED",
        "used_today": status.used_today,
        "daily_limit": status.daily_limit,
        "exhausted_at": status.exhausted_at.isoformat() if status.exhausted_at else None,
        "message": "Daily AI request quota exhausted. No paid fallback. Resets at midnight UTC.",
        "disclaimer": "AI Informational Research Only — Not a Trading Directive.",
    }
