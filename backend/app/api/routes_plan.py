import datetime
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.planner import TradePlan, planner
from app.engine.value_radar import value_radar_engine
from app.models import Position, Scan, Signal
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def _audit_payload_for_signal(db: Session, signal: Signal, session_date: datetime.date) -> tuple[list, Optional[dict]]:
    """Return the persisted audit for this scan and a compact, display-safe first failure.

    This is presentation metadata only: it does not re-evaluate a trade or alter any
    decision.  Keeping it alongside the list row makes BLOCKED actionable at a glance.
    """
    from app.models import DecisionAudit, DecisionStageResult

    audit = (
        db.query(DecisionAudit)
        .filter(
            DecisionAudit.symbol == signal.symbol,
            DecisionAudit.market == signal.market,
            DecisionAudit.asof_date == session_date,
        )
        .order_by(DecisionAudit.created_at.desc())
        .first()
    )
    if not audit:
        return [], None
    rows = db.query(DecisionStageResult).filter(DecisionStageResult.audit_id == audit.id).all()
    stages = [
        {
            "stage_name": row.stage_name,
            "status": row.status,
            "checks": json.loads(row.checks_json) if row.checks_json else [],
            "rejection_reasons": json.loads(row.rejection_reasons_json) if row.rejection_reasons_json else [],
        }
        for row in rows
    ]
    for stage in stages:
        if stage["status"] != "BLOCK":
            continue
        failed = next((check for check in stage["checks"] if not check.get("passed", False)), None)
        if failed:
            return stages, {
                "stage": stage["stage_name"],
                "check": failed.get("name", "Check"),
                "value": str(failed.get("value", "Unknown")),
                "threshold": str(failed.get("threshold", "Configured threshold")),
                "note": str(failed.get("note", "This check must pass before a setup can proceed.")),
            }
        reason = next((reason for reason in stage["rejection_reasons"] if reason), None)
        if reason:
            return stages, {"stage": stage["stage_name"], "check": "Gate", "value": reason, "threshold": "Pass required", "note": "This gate blocked the setup."}
    return stages, None


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
    candidate_dicts = []

    ACTIONABLE_STATES = {"VALID_SETUP", "APPROACHING", "TRIGGERED_PROVISIONAL", "TRIGGERED_CONFIRMED"}

    for s in signals:
        reasons_raw = json.loads(s.reasons_json) if s.reasons_json else []
        clean_reasons = [r for r in reasons_raw if isinstance(r, str) and r.strip()]
        decision_stages, blocked_reason = _audit_payload_for_signal(db, s, scan_row.session_date)
        item = {
            "id": s.id,
            "symbol": s.symbol,
            "market": s.market,
            "setup": s.setup,
            "trigger": s.trigger if s.trigger and s.trigger > 0 else 0.0,
            "entry_zone_high": s.entry_zone_high if s.entry_zone_high and s.entry_zone_high > 0 else 0.0,
            "stop": s.stop if s.stop and s.stop > 0 else 0.0,
            "target1": s.target1 if s.target1 and s.target1 > 0 else 0.0,
            "qty": s.qty if s.qty and s.qty > 0 else 0,
            "risk_amount": s.risk_amount or 0.0,
            "cost_estimate": s.cost_estimate or 0.0,
            "cost_in_r": s.cost_in_r or 0.0,
            "rs_rank": s.rs_rank,
            "score": s.score,
            "atr": s.atr,
            "gap95": s.gap95,
            "state": s.state,
            "reasons": clean_reasons,
            "news_coverage": json.loads(s.news_flags_json) if s.news_flags_json else {},
            "valid_until": s.valid_until.isoformat() if s.valid_until else None,
            "decision_stages": decision_stages,
            "blocked_reason": blocked_reason,
            "fundamentals": json.loads(s.fundamentals_json) if s.fundamentals_json else None,
        }

        # ONLY actionable, verified setups belong in Trade Plan signals!
        # Everything else (NO_SETUP, BLOCKED, MONITORING) belongs in candidate_opportunities
        if s.state in ACTIONABLE_STATES and s.setup in ("VCP", "BREAKOUT", "PULLBACK") and s.trigger and s.trigger > 0:
            if s.setup == "PULLBACK":
                shadow_dicts.append(item)
            else:
                sig_dicts.append(item)
        else:
            candidate_dicts.append(item)

    regime_detail = json.loads(scan_row.regime_detail_json) if scan_row.regime_detail_json else {}
    regime_allows_entries = regime_detail.get("allows_entries", True)

    all_opps = sig_dicts + shadow_dicts + candidate_dicts
    scanned_count = scan_row.passed_filters
    trend_pass_count = sum(
        1 for s in all_opps
        if any(stage.get("stage_name") == "Setup Validator" and any("Trend Template" in r or "SMA" in r for r in stage.get("rejection_reasons", [])) is False for stage in s.get("decision_stages", []))
    )
    trend_count = min(scanned_count, trend_pass_count)
    setup_count = min(trend_count, sum(1 for s in all_opps if s.get("setup") not in ("MONITORING", None, "")))
    fund_count = min(setup_count, sum(1 for s in all_opps if (s.get("fundamentals") or {}).get("red_count", 0) == 0 and s.get("setup") not in ("MONITORING", None, "")))
    news_count = min(fund_count, sum(1 for s in all_opps if (s.get("news_coverage") or {}).get("status") == "CLEAR" and s.get("setup") not in ("MONITORING", None, "")))
    risk_count = min(news_count, sum(1 for s in all_opps if any(st.get("stage_name") == "Risk Validator" and st.get("status") == "PASS" for st in s.get("decision_stages", [])) and regime_allows_entries))
    pass_count = min(risk_count, len(sig_dicts))

    funnel = [
        {"key": "ALL", "label": "Scanned", "count": scanned_count, "denominator": scan_row.universe_size, "tooltip": "Eligible instruments passing price floor, liquidity ADV, volatility cap and affordability filters"},
        {"key": "TREND", "label": "Trend OK", "count": trend_count, "denominator": scanned_count or 1, "tooltip": "Passing Minervini Stage 2 Trend Template rules (SMA50/150/200, 52w high/low, RS Rank >= 0.70)"},
        {"key": "SETUPS", "label": "Valid Setups" if regime_allows_entries else "Patterns (blocked by regime)", "count": setup_count, "denominator": trend_count or 1, "tooltip": "Consolidation structure formed: tight VCP contraction or EMA pullback"},
        {"key": "FUNDAMENTALS", "label": "Fundamentals OK", "count": fund_count, "denominator": setup_count or 1, "tooltip": "Fundamental health check has 0 RED traffic lights (mode: warn)"},
        {"key": "NEWS", "label": "News Clear", "count": news_count, "denominator": fund_count or 1, "tooltip": "No high-risk corporate disclosures, earnings blackout, or adverse news events"},
        {"key": "RISK", "label": "Risk OK", "count": risk_count, "denominator": news_count or 1, "tooltip": "Passes portfolio heat, sector limits, cost drag gate <= 0.25R, and regime allow_entries"},
        {"key": "PASS", "label": "PASS", "count": pass_count, "denominator": risk_count or 1, "tooltip": "Approved actionable order ready for execution upon 15m intraday trigger confirmation"},
    ]

    return {
        "market": market,
        "session_date": scan_row.session_date.isoformat(),
        "regime": regime_detail,
        "signals": sig_dicts,
        "shadow_signals": shadow_dicts,
        "candidate_opportunities": candidate_dicts,
        "pre_breakout_watchlist": [item for item in candidate_dicts if item["state"] == "PRE_BREAKOUT_WATCHLIST"],
        "funnel": funnel,
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


@router.get("/value-radar")
def get_value_radar(
    market: str = Query("IN", pattern="^(IN|US)$"),
    format: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return research ideas only; candidates still use the regular pipeline and risk validator.
    Includes transparent 'Why Zero' exclusion metrics.
    """
    res = value_radar_engine.evaluate_universe(market=market, db=db)
    if format == "list":
        return res["ideas"]
    # Return full object with ideas, summary and explanation
    return res

