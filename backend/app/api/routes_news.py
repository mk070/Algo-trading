import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.newsfilter import news_engine
from app.engine.universe import universe_manager
from app.models import CompanyRelationship, NewsCoverageGap, NewsEvent, NewsSourceState
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class RelationshipCreateRequest(BaseModel):
    watched_symbol: str
    related_entity: str
    relationship_type: str  # SUBSIDIARY, PARENT, KEY_CUSTOMER, SUPPLIER, COMPETITOR
    evidence_url: Optional[str] = None
    evidence_note: Optional[str] = None
    confidence: float = 1.0


@router.get("/news")
def get_news_events(
    symbol: Optional[str] = None,
    days: int = 14,
    severity: Optional[str] = None,
    materiality: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Returns classified corporate events (RED, AMBER, GREEN) with original URLs, timestamps,
    syndication clusters, price moves, and deterministic summaries.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    query = db.query(NewsEvent).filter(NewsEvent.published_at >= cutoff)

    if symbol:
        query = query.filter(NewsEvent.symbol == symbol.strip().upper())
    if severity:
        query = query.filter(NewsEvent.severity == severity.strip().upper())
    if materiality:
        query = query.filter(NewsEvent.materiality == materiality.strip().upper())

    events = query.order_by(NewsEvent.published_at.desc()).limit(100).all()

    if not events:
        # If no events exist yet, automatically poll live financial media news for core stocks
        try:
            mkt = "US" if symbol and any(c.isascii() and c in ("AAPL", "TSLA", "MSFT", "NVDA") for c in [symbol]) else "IN"
            top_stocks = [symbol] if symbol else (["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"] if mkt == "IN" else ["AAPL", "TSLA", "NVDA", "MSFT"])
            news_engine.poll_financial_news(top_stocks, market=mkt, db=db)
            events = query.order_by(NewsEvent.published_at.desc()).limit(100).all()
        except Exception as e:
            logger.warning(f"Initial live news fetch warning: {e}")

    unique_syms = list(set(e.symbol for e in events))
    quotes = {}
    if unique_syms:
        try:
            from app.providers.manager import provider_manager
            quotes = provider_manager.get_quotes(unique_syms, market="IN")
        except Exception as qe:
            logger.debug(f"Could not load live quotes for news: {qe}")

    results = []
    for e in events:
        q = quotes.get(e.symbol)
        day_pct = round(q.pct_change, 2) if (q and q.pct_change is not None) else e.price_change_day_pct
        live_price = round(q.last_price, 2) if q else None

        results.append(
            {
                "id": e.id,
                "symbol": e.symbol,
                "source": e.source,
                "title": e.title,
                "url": e.url,
                "published_at": e.published_at.isoformat(),
                "ingested_at": e.ingested_at.isoformat(),
                "severity": e.severity,
                "category": e.category,
                "ai_summary": e.ai_summary,
                "match_confidence": e.match_confidence or "EXACT_NAME",
                "is_unverified": e.is_unverified or False,
                "syndication_cluster_id": e.syndication_cluster_id,
                "materiality": e.materiality or "LOW",
                "summary": e.summary or e.title,
                "live_price": live_price,
                "price_change_day_pct": day_pct,
                "price_atr_multiple": e.price_atr_multiple,
                "analyst_action": json.loads(e.analyst_action_json) if e.analyst_action_json else None,
            }
        )

    return results


@router.get("/news/coverage")
def get_news_coverage(
    symbols: str = Query(..., description="Comma-separated symbols"),
    market: str = "IN",
    db: Session = Depends(get_db),
):
    """Returns CLEAR, REVIEW, BLOCKED, or UNKNOWN coverage status per symbol."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    coverage_map = {}

    for s in sym_list:
        cov = news_engine.check_symbol_coverage(s, market=market, db=db)
        coverage_map[s] = cov.model_dump()

    return coverage_map


@router.get("/news/sources/health")
def get_sources_health(db: Session = Depends(get_db)):
    """Returns real-time health metrics, latency classes, and last poll state for all free news sources."""
    return news_engine.get_source_health(db=db)


@router.get("/news/macro")
def get_macro_calendar(market: Optional[str] = None):
    """Returns central bank meeting schedules and current caution flags."""
    cal = settings.get_macro_calendar()
    in_flags = news_engine.check_macro_calendar("IN")
    us_flags = news_engine.check_macro_calendar("US")

    return {
        "calendar": cal,
        "active_caution_flags": {
            "IN": in_flags,
            "US": us_flags,
        },
    }


@router.get("/news/relationships")
def get_company_relationships(symbol: Optional[str] = None, db: Session = Depends(get_db)):
    """Returns mapped company relationships (subsidiaries, parents, key suppliers)."""
    query = db.query(CompanyRelationship).filter(CompanyRelationship.status == "ACTIVE")
    if symbol:
        query = query.filter(CompanyRelationship.watched_symbol == symbol.strip().upper())
    rows = query.all()
    return [
        {
            "id": r.id,
            "watched_symbol": r.watched_symbol,
            "related_entity": r.related_entity,
            "relationship_type": r.relationship_type,
            "evidence_url": r.evidence_url,
            "evidence_note": r.evidence_note,
            "last_reviewed": r.last_reviewed.isoformat(),
            "confidence": r.confidence,
        }
        for r in rows
    ]


@router.post("/news/relationships")
def add_company_relationship(req: RelationshipCreateRequest, db: Session = Depends(get_db)):
    """Adds or updates a company relationship record."""
    record = CompanyRelationship(
        watched_symbol=req.watched_symbol.strip().upper(),
        related_entity=req.related_entity.strip(),
        relationship_type=req.relationship_type.strip().upper(),
        evidence_url=req.evidence_url,
        evidence_note=req.evidence_note,
        last_reviewed=datetime.date.today(),
        confidence=req.confidence,
        status="ACTIVE",
    )
    db.add(record)
    db.commit()
    return {"status": "SUCCESS", "id": record.id}


@router.get("/news/coverage-gaps")
def get_coverage_gaps(db: Session = Depends(get_db)):
    """Returns all recorded offline coverage gaps."""
    rows = db.query(NewsCoverageGap).order_by(NewsCoverageGap.gap_start.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "gap_start": r.gap_start.isoformat(),
            "gap_end": r.gap_end.isoformat() if r.gap_end else None,
            "duration_sec": r.duration_sec,
            "status": r.status,
            "notes": r.notes,
        }
        for r in rows
    ]


@router.get("/earnings/analysis")
def get_earnings_analysis(
    symbol: str = Query(..., description="Stock symbol, e.g. TCS or AAPL"),
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Returns structured YoY/QoQ earnings comparison, deterministic AMBER checks,
    and verified official source links. Missing consensus defaults to UNKNOWN.
    """
    from app.engine.earnings_analyst import earnings_analyst
    filings = earnings_analyst.get_filing_history(symbol, market=market, db=db)
    if not filings:
        return {"symbol": symbol, "status": "NO_FILINGS_FOUND"}

    latest = filings[0]
    prior_qoq = filings[1] if len(filings) > 1 else None
    prior_yoy = filings[2] if len(filings) > 2 else (filings[1] if len(filings) > 1 else None)

    res = earnings_analyst.analyze_results(latest, prior_qoq=prior_qoq, prior_yoy=prior_yoy, db=db)
    return res.model_dump()


@router.post("/news/refresh")
def refresh_live_news(
    market: str = Query("IN", pattern="^(IN|US)$"),
    symbols: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Fetches real-time financial news from Yahoo Finance, Reuters, Moneycontrol, Mint,
    and business press syndication for universe or specified stocks.
    """
    market = market.upper() if isinstance(market, str) else "IN"
    if symbols and isinstance(symbols, str):
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        # Load top universe stocks for this market
        u_stocks = universe_manager.load_universe(market)
        sym_list = [s.symbol for s in u_stocks][:15]
        if not sym_list:
            sym_list = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"] if market == "IN" else ["AAPL", "TSLA", "NVDA", "MSFT"]

    count = news_engine.poll_financial_news(sym_list, market=market, db=db)
    return {
        "status": "SUCCESS",
        "market": market,
        "symbols_polled": sym_list,
        "items_ingested": count,
    }

