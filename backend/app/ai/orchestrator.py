"""
AI Research Orchestrator

Coordinates the six research agents in staged sequence:
  1. News Intelligence
  2. Company Research (only if materiality >= MEDIUM)
  3. Market Context
  4. Technical Research
  5. Risk Review
  6. Final Decision

Quota & Flag Gates:
  - Checks individual agent feature flags + global AI_AGENTS_ENABLED.
  - Checks cache BEFORE consuming quota (duplicate suppression).
  - Reserves quota atomically in DB via `quota_guard.check_and_consume(..., db=db)`.
  - Records success/failure outcomes in `ai_provider_usage`.
  - Persists results to `ai_agent_executions` and `ai_research_assessments`.

NVIDIA hosted API: NOT used for live production requests.
Only gemini_adapter is permitted for live requests.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.ai.gemini_adapter import gemini_adapter
from app.ai.quota_guard import quota_guard
from app.ai.schemas import (
    CompanyResearchOutput,
    FinalResearchOutput,
    MarketContextOutput,
    MaterialityLevel,
    NewsIntelligenceOutput,
    RiskReviewOutput,
    TechnicalResearchOutput,
)

logger = logging.getLogger(__name__)

# Materiality threshold for escalation to company research
_ESCALATION_THRESHOLD = {MaterialityLevel.HIGH, MaterialityLevel.MEDIUM}

# How long a cached result is considered fresh (avoid re-running for same input)
_CACHE_TTL_HOURS = 6


def _record_agent_outcome(result: Any, db: Session) -> None:
    """Record provider outcome if a provider call was actually attempted."""
    if getattr(result, "error_code", None) == "SKIPPED":
        return
    quota_guard.record_outcome(
        success=bool(getattr(result, "is_valid", False)),
        input_tokens=getattr(result, "input_tokens", None),
        output_tokens=getattr(result, "output_tokens", None),
        error_code=getattr(result, "error_code", None),
        db=db,
        provider=getattr(result, "provider", gemini_adapter.provider_name),
        model_id=getattr(result, "model_id", gemini_adapter.model_id),
    )


def run_news_intelligence(
    news_event_id: int,
    db: Session,
) -> Optional[NewsIntelligenceOutput]:
    """
    Run the News Intelligence agent for a single event (flag-gated, cached, quota-gated).

    Returns:
        NewsIntelligenceOutput or None if disabled / blocked by quota / not found.
    """
    if not quota_guard.is_agent_enabled("news_intelligence"):
        logger.info(f"[Orchestrator] news_intelligence disabled by feature flags")
        return None

    from app.models import NewsEvent
    event: Optional[NewsEvent] = db.query(NewsEvent).filter(NewsEvent.id == news_event_id).first()
    if not event:
        logger.warning(f"[Orchestrator] NewsEvent {news_event_id} not found")
        return None

    event_data = {
        "id": event.id,
        "symbol": event.symbol,
        "title": event.title,
        "source": event.source,
        "published_at": event.published_at.isoformat() if event.published_at else "",
        "url": event.url or "",
        "severity": event.severity,
        "category": event.category,
        "market": "IN",
    }

    input_hash = _make_news_hash(event.symbol, event.title, str(event.published_at), event.url or "")

    # Check cache BEFORE consuming quota
    cached = _load_cached_execution(db, "news_intelligence", event.symbol, input_hash)
    if cached:
        logger.debug(f"[Orchestrator] Cache hit for news_intelligence event {news_event_id}")
        try:
            return NewsIntelligenceOutput(**cached)
        except Exception:
            pass  # Cache miss on schema mismatch — re-run

    if not quota_guard.check_and_consume(
        "news_intelligence",
        db=db,
        provider=gemini_adapter.provider_name,
        model_id=gemini_adapter.model_id,
    ):
        logger.info(f"[Orchestrator] News Intelligence blocked by quota guard for event {news_event_id}")
        return None

    from app.ai.agents.news_intelligence_agent import run_news_intelligence as _run
    result = _run(event_data=event_data, provider=gemini_adapter)
    _record_agent_outcome(result, db)

    _persist_execution(
        db=db,
        agent_name="news_intelligence",
        symbol=event.symbol,
        market="IN",
        input_hash=input_hash,
        input_record_ids=[news_event_id],
        result=result,
    )

    return result


def run_company_research(
    symbol: str,
    news_event_id: int,
    db: Session,
    market: str = "IN",
) -> Optional[CompanyResearchOutput]:
    """
    Run the Company Research agent (flag-gated, cached, quota-gated, chained from News Intelligence).
    Only runs if news materiality >= MEDIUM.
    """
    if not quota_guard.is_agent_enabled("company_research"):
        return None

    news_output = run_news_intelligence(news_event_id, db)
    if news_output is None or not news_output.is_valid:
        return None

    if news_output.materiality not in _ESCALATION_THRESHOLD:
        logger.info(
            f"[Orchestrator] Skipping company research for {symbol} — "
            f"materiality {news_output.materiality} below threshold"
        )
        return None

    input_hash = _make_symbol_hash(symbol, str(news_event_id))
    cached = _load_cached_execution(db, "company_research", symbol, input_hash)
    if cached:
        try:
            return CompanyResearchOutput(**cached)
        except Exception:
            pass

    if not quota_guard.check_and_consume(
        "company_research",
        db=db,
        provider=gemini_adapter.provider_name,
        model_id=gemini_adapter.model_id,
    ):
        logger.info(f"[Orchestrator] Company Research blocked by quota guard for {symbol}")
        return None

    fundamentals, instrument_meta = _load_symbol_data(db, symbol, market)

    from app.ai.agents.company_research_agent import run_company_research as _run
    result = _run(
        news_output=news_output,
        provider=gemini_adapter,
        fundamentals=fundamentals,
        instrument_meta=instrument_meta,
    )
    _record_agent_outcome(result, db)

    _persist_execution(
        db=db,
        agent_name="company_research",
        symbol=symbol,
        market=market,
        input_hash=input_hash,
        input_record_ids=[news_event_id],
        result=result,
    )
    return result


def run_full_research(
    symbol: str,
    db: Session,
    news_event_id: Optional[int] = None,
    market: str = "IN",
) -> Dict[str, Any]:
    """
    Run all six agents in sequence (flag-gated, cached, and quota-gated at each step).

    Returns:
        Dict with outputs from all six agents + a final research assessment.
    """
    results: Dict[str, Any] = {
        "symbol": symbol,
        "market": market,
        "news_intelligence": None,
        "company_research": None,
        "market_context": None,
        "technical_research": None,
        "risk_review": None,
        "final_decision": None,
        "assessment_id": None,
    }

    # --- Agent 1: News Intelligence ---
    news_output: Optional[NewsIntelligenceOutput] = None
    if news_event_id:
        news_output = run_news_intelligence(news_event_id, db)
        results["news_intelligence"] = news_output.model_dump() if news_output else None

    # --- Agent 2: Company Research (gated by materiality + flag) ---
    company_output: Optional[CompanyResearchOutput] = None
    if (
        news_output
        and news_output.is_valid
        and news_output.materiality in _ESCALATION_THRESHOLD
        and quota_guard.is_agent_enabled("company_research")
    ):
        cr_hash = _make_symbol_hash(symbol, str(news_event_id))
        cached_cr = _load_cached_execution(db, "company_research", symbol, cr_hash)
        if cached_cr:
            try:
                company_output = CompanyResearchOutput(**cached_cr)
            except Exception:
                company_output = None

        if company_output is None and quota_guard.check_and_consume(
            "company_research",
            db=db,
            provider=gemini_adapter.provider_name,
            model_id=gemini_adapter.model_id,
        ):
            fundamentals, instrument_meta = _load_symbol_data(db, symbol, market)
            from app.ai.agents.company_research_agent import run_company_research as _run_cr
            company_output = _run_cr(
                news_output=news_output,
                provider=gemini_adapter,
                fundamentals=fundamentals,
                instrument_meta=instrument_meta,
            )
            _record_agent_outcome(company_output, db)
            _persist_execution(
                db, "company_research", symbol, market,
                cr_hash, [news_event_id] if news_event_id else [], company_output,
            )
        results["company_research"] = company_output.model_dump() if company_output else None

    # --- Agent 3: Market Context ---
    market_output: Optional[MarketContextOutput] = None
    if quota_guard.is_agent_enabled("market_context"):
        mc_hash = _make_symbol_hash(symbol, "market_context")
        cached_mc = _load_cached_execution(db, "market_context", symbol, mc_hash)
        if cached_mc:
            try:
                market_output = MarketContextOutput(**cached_mc)
            except Exception:
                market_output = None

        if market_output is None and quota_guard.check_and_consume(
            "market_context",
            db=db,
            provider=gemini_adapter.provider_name,
            model_id=gemini_adapter.model_id,
        ):
            regime_data = _load_latest_regime(db, market)
            _, instrument_meta = _load_symbol_data(db, symbol, market)
            from app.ai.agents.market_context_agent import run_market_context
            market_output = run_market_context(
                symbol=symbol,
                provider=gemini_adapter,
                regime_data=regime_data,
                sector=instrument_meta.get("sector") if instrument_meta else None,
                market=market,
            )
            _record_agent_outcome(market_output, db)
            _persist_execution(db, "market_context", symbol, market, mc_hash, [], market_output)
        results["market_context"] = market_output.model_dump() if market_output else None

    # --- Agent 4: Technical Research ---
    technical_output: Optional[TechnicalResearchOutput] = None
    if quota_guard.is_agent_enabled("technical_research"):
        tr_hash = _make_symbol_hash(symbol, "technical")
        cached_tr = _load_cached_execution(db, "technical_research", symbol, tr_hash)
        if cached_tr:
            try:
                technical_output = TechnicalResearchOutput(**cached_tr)
            except Exception:
                technical_output = None

        if technical_output is None and quota_guard.check_and_consume(
            "technical_research",
            db=db,
            provider=gemini_adapter.provider_name,
            model_id=gemini_adapter.model_id,
        ):
            signal_data = _load_latest_signal(db, symbol)
            from app.ai.agents.technical_research_agent import run_technical_research
            technical_output = run_technical_research(
                symbol=symbol,
                provider=gemini_adapter,
                signal_data=signal_data,
                market=market,
            )
            _record_agent_outcome(technical_output, db)
            _persist_execution(db, "technical_research", symbol, market, tr_hash, [], technical_output)
        results["technical_research"] = technical_output.model_dump() if technical_output else None

    # --- Agent 5: Risk Review ---
    risk_output: Optional[RiskReviewOutput] = None
    if quota_guard.is_agent_enabled("risk_review"):
        rr_hash = _make_symbol_hash(symbol, f"risk|{news_event_id or 'none'}")
        cached_rr = _load_cached_execution(db, "risk_review", symbol, rr_hash)
        if cached_rr:
            try:
                risk_output = RiskReviewOutput(**cached_rr)
            except Exception:
                risk_output = None

        if risk_output is None and quota_guard.check_and_consume(
            "risk_review",
            db=db,
            provider=gemini_adapter.provider_name,
            model_id=gemini_adapter.model_id,
        ):
            from app.ai.agents.risk_review_agent import run_risk_review
            risk_output = run_risk_review(
                symbol=symbol,
                provider=gemini_adapter,
                news_output=news_output,
                company_output=company_output,
                market_output=market_output,
                technical_output=technical_output,
                market=market,
            )
            _record_agent_outcome(risk_output, db)
            _persist_execution(db, "risk_review", symbol, market, rr_hash, [], risk_output)
        results["risk_review"] = risk_output.model_dump() if risk_output else None

    # --- Agent 6: Final Decision ---
    final_output: Optional[FinalResearchOutput] = None
    if quota_guard.is_agent_enabled("final_decision"):
        fd_hash = _make_symbol_hash(symbol, f"final|{news_event_id or 'none'}")
        cached_fd = _load_cached_execution(db, "final_decision", symbol, fd_hash)
        if cached_fd:
            try:
                final_output = FinalResearchOutput(**cached_fd)
            except Exception:
                final_output = None

        if final_output is None and quota_guard.check_and_consume(
            "final_decision",
            db=db,
            provider=gemini_adapter.provider_name,
            model_id=gemini_adapter.model_id,
        ):
            from app.ai.agents.final_decision_agent import run_final_decision
            final_output = run_final_decision(
                symbol=symbol,
                provider=gemini_adapter,
                news_output=news_output,
                company_output=company_output,
                market_output=market_output,
                technical_output=technical_output,
                risk_output=risk_output,
                market=market,
            )
            _record_agent_outcome(final_output, db)
            exec_id = _persist_execution(db, "final_decision", symbol, market, fd_hash, [], final_output)
            if final_output and final_output.is_valid:
                assessment_id = _persist_assessment(
                    db, symbol, market, final_output, agent_execution_id=exec_id
                )
                results["assessment_id"] = assessment_id
        results["final_decision"] = final_output.model_dump() if final_output else None

    return results


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_symbol_data(
    db: Session,
    symbol: str,
    market: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Load fundamentals and instrument metadata from DB."""
    fundamentals: Optional[Dict[str, Any]] = None
    instrument_meta: Optional[Dict[str, Any]] = None

    try:
        from app.models import FundamentalSnapshot, Instrument
        snap = (
            db.query(FundamentalSnapshot)
            .filter(FundamentalSnapshot.symbol == symbol)
            .order_by(FundamentalSnapshot.as_of.desc())
            .first()
        )
        if snap:
            fundamentals = {
                "revenue_yoy": snap.revenue_yoy,
                "profit_yoy": snap.profit_yoy,
                "op_margin": snap.op_margin,
                "roce": snap.roce,
                "roe": snap.roe,
                "debt_equity": snap.debt_equity,
                "interest_coverage": snap.interest_coverage,
                "pe": snap.pe,
                "sector_median_pe": snap.sector_median_pe,
                "promoter_holding": snap.promoter_holding,
                "pledge_pct": snap.pledge_pct,
                "completeness": snap.completeness,
                "as_of": str(snap.as_of) if snap.as_of else None,
                "source": snap.source,
            }

        instr = (
            db.query(Instrument)
            .filter(Instrument.symbol == symbol, Instrument.market == market)
            .first()
        )
        if instr:
            instrument_meta = {
                "name": instr.name,
                "sector": instr.sector,
                "industry": instr.industry,
            }
    except Exception as exc:
        logger.warning(f"[Orchestrator] Could not load symbol data for {symbol}: {exc}")

    return fundamentals, instrument_meta


def _load_latest_regime(db: Session, market: str) -> Optional[Dict[str, Any]]:
    """Load the most recent Scan regime for the market."""
    try:
        from app.models import Scan
        scan = (
            db.query(Scan)
            .filter(Scan.market == market)
            .order_by(Scan.run_at.desc())
            .first()
        )
        if scan:
            return {
                "regime": scan.regime,
                "session_date": str(scan.session_date),
                "regime_detail_json": scan.regime_detail_json,
            }
    except Exception as exc:
        logger.warning(f"[Orchestrator] Could not load regime for market {market}: {exc}")
    return None


def _load_latest_signal(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """Load the most recent Signal record for the symbol."""
    try:
        from app.models import Signal
        sig = (
            db.query(Signal)
            .filter(Signal.symbol == symbol)
            .order_by(Signal.created_at.desc())
            .first()
        )
        if sig:
            return {
                "setup": sig.setup,
                "trigger": sig.trigger,
                "stop": sig.stop,
                "target1": sig.target1,
                "atr": sig.atr,
                "rs_rank": sig.rs_rank,
                "score": sig.score,
                "state": sig.state,
                "valid_until": str(sig.valid_until) if sig.valid_until else None,
                "reasons_json": sig.reasons_json,
            }
    except Exception as exc:
        logger.warning(f"[Orchestrator] Could not load signal for {symbol}: {exc}")
    return None


def _make_news_hash(symbol: str, headline: str, published_at: str, url: str) -> str:
    raw = f"{symbol}|{headline}|{published_at}|{url}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _make_symbol_hash(symbol: str, suffix: str) -> str:
    raw = f"{symbol}|{suffix}|{datetime.date.today().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _load_cached_execution(
    db: Session,
    agent_name: str,
    symbol: str,
    input_hash: str,
) -> Optional[Dict[str, Any]]:
    """Return cached output_json if a fresh valid execution exists."""
    try:
        from app.ai.models import AiAgentExecution
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=_CACHE_TTL_HOURS)
        row = (
            db.query(AiAgentExecution)
            .filter(
                AiAgentExecution.agent_name == agent_name,
                AiAgentExecution.symbol == symbol,
                AiAgentExecution.input_hash == input_hash,
                AiAgentExecution.is_valid.is_(True),
                AiAgentExecution.generated_at >= cutoff,
            )
            .order_by(AiAgentExecution.generated_at.desc())
            .first()
        )
        if row and row.output_json:
            return json.loads(row.output_json)
    except Exception as exc:
        logger.debug(f"[Orchestrator] Cache lookup failed: {exc}")
    return None


def _persist_execution(
    db: Session,
    agent_name: str,
    symbol: str,
    market: str,
    input_hash: str,
    input_record_ids: List[int],
    result: Any,
) -> Optional[int]:
    """Persist an agent execution to ai_agent_executions."""
    try:
        from app.ai.models import AiAgentExecution
        output_json = result.model_dump_json() if hasattr(result, "model_dump_json") else json.dumps({})
        row = AiAgentExecution(
            agent_name=agent_name,
            symbol=symbol,
            market=market,
            input_hash=input_hash,
            provider=getattr(result, "provider", "unknown"),
            model_id=getattr(result, "model_id", "unknown"),
            prompt_version="1.0",
            input_record_ids=json.dumps(input_record_ids),
            output_json=output_json,
            validation_status="VALID" if getattr(result, "is_valid", False) else "INVALID",
            generated_at=datetime.datetime.now(datetime.timezone.utc),
            latency_sec=getattr(result, "latency_sec", 0.0),
            input_tokens=getattr(result, "input_tokens", None),
            output_tokens=getattr(result, "output_tokens", None),
            error_code=getattr(result, "error_code", None),
            is_valid=getattr(result, "is_valid", False),
        )
        db.add(row)
        db.flush()
        return row.id
    except Exception as exc:
        logger.warning(f"[Orchestrator] Could not persist execution for {agent_name}/{symbol}: {exc}")
        return None


def _persist_assessment(
    db: Session,
    symbol: str,
    market: str,
    final_output: FinalResearchOutput,
    agent_execution_id: Optional[int] = None,
) -> Optional[int]:
    """Persist the final research assessment to ai_research_assessments."""
    try:
        from app.ai.models import AiResearchAssessment

        try:
            prior = (
                db.query(AiResearchAssessment)
                .filter(
                    AiResearchAssessment.symbol == symbol,
                    AiResearchAssessment.market == market,
                    AiResearchAssessment.superseded_by.is_(None),
                )
                .all()
            )
        except Exception:
            prior = []

        row = AiResearchAssessment(
            symbol=symbol,
            market=market,
            final_status=final_output.final_status.value,
            summary=final_output.confidence_basis[:1000] if final_output.confidence_basis else "",
            evidence_json=json.dumps([e.model_dump(mode="json") for e in final_output.supporting_evidence]),
            risks_json=json.dumps(final_output.what_would_change_assessment),
            confidence=None,
            requires_human_review=final_output.requires_human_review,
            generated_at=datetime.datetime.now(datetime.timezone.utc),
            agent_execution_id=agent_execution_id,
        )
        db.add(row)
        db.flush()

        for p in prior:
            p.superseded_by = row.id

        return row.id
    except Exception as exc:
        logger.warning(f"[Orchestrator] Could not persist assessment for {symbol}: {exc}")
        return None
