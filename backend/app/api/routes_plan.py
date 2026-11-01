import datetime
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.planner import TradePlan, planner
from app.models import Position, Scan, Signal
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/plan")
def get_trade_plan(
    market: str = Query("IN", pattern="^(IN|US)$"),
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Returns today's or specified date's Trade Plan with ranked signals and checklist."""
    target_date = datetime.date.fromisoformat(date) if date else datetime.date.today()

    # Look for existing scan in DB
    scan_row = (
        db.query(Scan)
        .filter(Scan.market == market, Scan.session_date == target_date)
        .order_by(Scan.run_at.desc())
        .first()
    )

    if not scan_row:
        # Run scan on demand
        plan = planner.run_scan(market=market, target_date=target_date, db=db)
        return plan.model_dump()

    # Retrieve signals for this scan
    signals = db.query(Signal).filter(Signal.scan_id == scan_row.id).all()
    sig_dicts = []
    shadow_dicts = []
    for s in signals:
        item = {
            "id": s.id,
            "symbol": s.symbol,
            "market": s.market,
            "setup": s.setup,
            "trigger": s.trigger,
            "entry_zone_high": s.entry_zone_high,
            "stop": s.stop,
            "target1": s.target1,
            "qty": s.qty,
            "risk_amount": s.risk_amount,
            "cost_estimate": s.cost_estimate,
            "cost_in_r": s.cost_in_r,
            "rs_rank": s.rs_rank,
            "score": s.score,
            "atr": s.atr,
            "gap95": s.gap95,
            "state": s.state,
            "reasons": json.loads(s.reasons_json) if s.reasons_json else [],
            "news_coverage": json.loads(s.news_flags_json) if s.news_flags_json else {},
            "valid_until": s.valid_until.isoformat() if s.valid_until else None,
        }
        if s.setup == "PULLBACK":
            shadow_dicts.append(item)
        else:
            sig_dicts.append(item)

    return {
        "market": market,
        "session_date": scan_row.session_date.isoformat(),
        "regime": json.loads(scan_row.regime_detail_json) if scan_row.regime_detail_json else {},
        "signals": sig_dicts,
        "shadow_signals": shadow_dicts,
        "universe_size": scan_row.universe_size,
        "passed_filters": scan_row.passed_filters,
        "data_warnings": json.loads(scan_row.data_warnings_json) if scan_row.data_warnings_json else [],
        "generated_at": scan_row.run_at.isoformat(),
    }


@router.post("/scan/run")
def run_scan_now(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Triggers an on-demand screening scan."""
    plan = planner.run_scan(market=market, db=db)
    return plan.model_dump()


@router.get("/signals/{signal_id}")
def get_signal_detail(signal_id: int, db: Session = Depends(get_db)):
    """Returns complete details of a specific signal."""
    sig = db.query(Signal).filter(Signal.id == signal_id).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")

    return {
        "id": sig.id,
        "scan_id": sig.scan_id,
        "symbol": sig.symbol,
        "market": sig.market,
        "setup": sig.setup,
        "trigger": sig.trigger,
        "entry_zone_high": sig.entry_zone_high,
        "stop": sig.stop,
        "target1": sig.target1,
        "qty": sig.qty,
        "risk_amount": sig.risk_amount,
        "cost_estimate": sig.cost_estimate,
        "cost_in_r": sig.cost_in_r,
        "rs_rank": sig.rs_rank,
        "score": sig.score,
        "atr": sig.atr,
        "gap95": sig.gap95,
        "reasons": json.loads(sig.reasons_json) if sig.reasons_json else [],
        "news_coverage": json.loads(sig.news_flags_json) if sig.news_flags_json else {},
        "state": sig.state,
        "valid_until": sig.valid_until.isoformat() if sig.valid_until else None,
        "created_at": sig.created_at.isoformat(),
    }


@router.get("/watchlist")
def get_watchlist(market: str = Query("IN", pattern="^(IN|US)$"), db: Session = Depends(get_db)):
    """Watchlist: active signals + open positions with live prices, distance to trigger/stop."""
    signals = (
        db.query(Signal)
        .filter(Signal.market == market, Signal.state.in_(["WATCHLIST", "APPROACHING", "TRIGGERED_PROVISIONAL"]))
        .all()
    )
    positions = (
        db.query(Position)
        .filter(Position.market == market, Position.status == "OPEN")
        .all()
    )

    symbols = list(set([s.symbol for s in signals] + [p.symbol for p in positions]))
    quotes = provider_manager.get_quotes(symbols, market=market)

    watchlist_items = []
    for s in signals:
        q = quotes.get(s.symbol)
        last_price = q.last_price if q else s.trigger
        dist_trigger_pct = ((s.trigger - last_price) / s.trigger * 100.0) if s.trigger > 0 else 0.0
        dist_stop_pct = ((last_price - s.stop) / last_price * 100.0) if last_price > 0 else 0.0

        watchlist_items.append(
            {
                "id": s.id,
                "symbol": s.symbol,
                "setup": s.setup,
                "state": s.state,
                "trigger": s.trigger,
                "stop": s.stop,
                "target1": s.target1,
                "last_price": round(last_price, 2),
                "distance_to_trigger_pct": round(dist_trigger_pct, 2),
                "distance_to_stop_pct": round(dist_stop_pct, 2),
                "is_stale": q.is_stale if q else True,
                "source": q.source if q else "None",
                "as_of": q.timestamp.isoformat() if q else None,
            }
        )

    return watchlist_items


@router.get("/decision-audits")
def get_decision_audits(
    symbol: Optional[str] = None,
    market: str = Query("IN", pattern="^(IN|US)$"),
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Returns persistent trade decision audits with 7-stage pipeline checks and pass/block reasons."""
    from app.models import DecisionAudit, DecisionStageResult

    query = db.query(DecisionAudit).filter(DecisionAudit.market == market)
    if symbol:
        query = query.filter(DecisionAudit.symbol == symbol.strip().upper())

    audits = query.order_by(DecisionAudit.created_at.desc()).limit(limit).all()
    results = []

    for a in audits:
        stage_rows = (
            db.query(DecisionStageResult)
            .filter(DecisionStageResult.audit_id == a.id)
            .all()
        )
        stages = [
            {
                "stage_name": sr.stage_name,
                "status": sr.status,
                "checks": json.loads(sr.checks_json) if sr.checks_json else [],
                "rejection_reasons": json.loads(sr.rejection_reasons_json) if sr.rejection_reasons_json else [],
            }
            for sr in stage_rows
        ]

        results.append(
            {
                "id": a.id,
                "symbol": a.symbol,
                "market": a.market,
                "asof_date": a.asof_date.isoformat(),
                "mode": a.mode,
                "final_decision": a.final_decision,
                "setup": a.setup,
                "trigger": a.trigger,
                "stop": a.stop,
                "target1": a.target1,
                "qty": a.qty,
                "risk_amount": a.risk_amount,
                "cost_in_r": a.cost_in_r,
                "config_hash": a.config_hash,
                "code_version": a.code_version,
                "data_source": a.data_source,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "stages": stages,
            }
        )

    return results

