import collections
import datetime
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.ai_research_assistant import ai_research_assistant
from app.engine.planner import TradePlan, planner, compute_factor_score_breakdown
from app.engine.fundamentals_engine import fundamentals_engine
from app.engine.value_radar import value_radar_engine
from app.models import Position, Scan, Signal, DecisionAudit, DecisionStageResult, Instrument, FundamentalSnapshot, NewsEvent
from app.providers.manager import provider_manager
from app.cache import shared_cache, cached_json_response
from app.telemetry import current_tag_ctx

logger = logging.getLogger(__name__)
router = APIRouter()


def _format_audit_stages(rows: list) -> tuple[list, Optional[dict]]:
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


def _audit_payload_for_signal(db: Session, signal: Signal, session_date: datetime.date) -> tuple[list, Optional[dict]]:
    """Return the persisted audit for this scan and a compact, display-safe first failure.

    This is presentation metadata only: it does not re-evaluate a trade or alter any
    decision. Keeping it alongside the list row makes BLOCKED actionable at a glance.
    """
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
    return _format_audit_stages(rows)


@router.get("/plan")
def get_trade_plan(
    request: Request,
    market: str = Query("IN", pattern="^(IN|US)$"),
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Returns today's or specified date's Trade Plan with ranked signals and checklist.
    Uses 60s shared memory cache, ETag/304 handling, and batch audit queries to prevent N+1.
    """
    target_date = datetime.date.fromisoformat(date) if date else datetime.date.today()
    cache_key = f"plan:{market}:{target_date.isoformat()}"

    def compute():
        current_tag_ctx.set("query:trade_plan")
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

        # Batch-fetch DecisionAudit and DecisionStageResult in 2 queries (eliminates N+1)
        symbols = list({s.symbol for s in signals})
        latest_audits = {}
        stage_results_by_audit = collections.defaultdict(list)

        # Batch-fetch Instruments for sector mapping (Phase 3.5 fix)
        inst_sector_map = {}
        if symbols:
            inst_rows = db.query(Instrument).filter(Instrument.symbol.in_(symbols), Instrument.market == market).all()
            for i in inst_rows:
                inst_sector_map[i.symbol] = i.sector if (i.sector and isinstance(i.sector, str)) else "General"

        # Compute sector averages across current signals to establish group trends
        sector_rs_buckets = collections.defaultdict(list)
        for s in signals:
            sec = inst_sector_map.get(s.symbol, "General")
            if s.rs_rank is not None:
                sector_rs_buckets[sec].append(s.rs_rank)

        sector_avg_rs_map = {
            sec: sum(vals) / len(vals) if vals else 0.5
            for sec, vals in sector_rs_buckets.items()
        }

        # Query recent verified news events for these symbols (top 2 per symbol)
        recent_news_events = collections.defaultdict(list)
        if symbols:
            cutoff_dt = datetime.datetime.combine(scan_row.session_date - datetime.timedelta(days=14), datetime.time.min)
            news_rows = (
                db.query(NewsEvent)
                .filter(
                    NewsEvent.symbol.in_(symbols),
                    NewsEvent.published_at >= cutoff_dt,
                )
                .order_by(NewsEvent.published_at.desc())
                .all()
            )
            for nr in news_rows:
                if len(recent_news_events[nr.symbol]) < 2:
                    recent_news_events[nr.symbol].append({
                        "id": nr.id,
                        "title": nr.title,
                        "source": nr.source or "Unknown",
                        "source_url": nr.url,
                        "published_at": nr.published_at.isoformat() if nr.published_at else None,
                        "severity": nr.severity or "CLEAR",
                        "materiality": nr.materiality,
                        "match_confidence": nr.match_confidence,
                    })

        if symbols:
            audits = (
                db.query(DecisionAudit)
                .filter(
                    DecisionAudit.symbol.in_(symbols),
                    DecisionAudit.market == market,
                    DecisionAudit.asof_date == scan_row.session_date,
                )
                .order_by(DecisionAudit.created_at.desc())
                .all()
            )
            for a in audits:
                if a.symbol not in latest_audits:
                    latest_audits[a.symbol] = a

            audit_ids = [a.id for a in latest_audits.values()]
            if audit_ids:
                stage_rows = db.query(DecisionStageResult).filter(DecisionStageResult.audit_id.in_(audit_ids)).all()
                for sr in stage_rows:
                    stage_results_by_audit[sr.audit_id].append(sr)

        for s in signals:
            reasons_raw = json.loads(s.reasons_json) if s.reasons_json else []
            clean_reasons = [r for r in reasons_raw if isinstance(r, str) and r.strip()]

            audit = latest_audits.get(s.symbol)
            if audit:
                stage_rows = stage_results_by_audit.get(audit.id, [])
                decision_stages, blocked_reason = _format_audit_stages(stage_rows)
            else:
                decision_stages, blocked_reason = [], None

            fund_dict = json.loads(s.fundamentals_json) if s.fundamentals_json else None
            news_cov_dict = json.loads(s.news_flags_json) if s.news_flags_json else {}

            sec_name = inst_sector_map.get(s.symbol, "General")
            sec_avg_rs = sector_avg_rs_map.get(sec_name, s.rs_rank or 0.5)
            sec_trend = "LEADING" if sec_avg_rs >= 0.65 else ("LAGGING" if sec_avg_rs <= 0.35 else "NEUTRAL")
            sym_catalysts = recent_news_events.get(s.symbol, [])

            factors = compute_factor_score_breakdown(
                symbol=s.symbol,
                setup=s.setup or "MONITORING",
                trigger=s.trigger or 0.0,
                stop=s.stop or 0.0,
                rs_rank=s.rs_rank or 0.5,
                sector_name=sec_name,
                sector_rs_rank=sec_avg_rs,
                sector_trend=sec_trend,
                news_cov=news_cov_dict,
                fund_dict=fund_dict,
                catalyst_count=len(sym_catalysts),
            )
            evidence = {
                "fundamental_snapshot_id": None,
                "fundamental_as_of": None,
                "fundamental_source": None,
                "catalysts": sym_catalysts,
                "sector_name": sec_name,
                "sector_rs_rank": round(sec_avg_rs, 2),
                "sector_trend": sec_trend,
            }

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
                "news_coverage": news_cov_dict,
                "valid_until": s.valid_until.isoformat() if s.valid_until else None,
                "decision_stages": decision_stages,
                "blocked_reason": blocked_reason,
                "fundamentals": fund_dict,
                "factors": factors.model_dump(),
                "evidence": evidence,
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

    if_none_match = request.headers.get("if-none-match")
    data, etag, is_stale, _ = shared_cache.get_or_compute(cache_key, compute, ttl_sec=60.0)
    return cached_json_response(data, etag=etag, if_none_match=if_none_match, max_age_sec=60, is_stale=is_stale)


@router.post("/scan/run")
def run_scan_now(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Triggers an on-demand screening scan. Invalidates plan/pulse/regime caches."""
    plan = planner.run_scan(market=market, db=db)
    shared_cache.invalidate_prefix(f"plan:{market}")
    shared_cache.invalidate_prefix(f"pulse:{market}")
    shared_cache.invalidate_prefix(f"regime:{market}")
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
    query = db.query(DecisionAudit).filter(DecisionAudit.market == market)
    if symbol:
        query = query.filter(DecisionAudit.symbol == symbol.strip().upper())

    audits = query.order_by(DecisionAudit.created_at.desc()).limit(limit).all()
    results = []

    audit_ids = [a.id for a in audits]
    stage_results_by_audit = collections.defaultdict(list)
    if audit_ids:
        stage_rows = db.query(DecisionStageResult).filter(DecisionStageResult.audit_id.in_(audit_ids)).all()
        for sr in stage_rows:
            stage_results_by_audit[sr.audit_id].append(sr)

    for a in audits:
        stage_rows = stage_results_by_audit.get(a.id, [])
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


@router.get("/opportunities/{symbol}/dossier")
def get_opportunity_dossier(
    symbol: str,
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Comprehensive Research Dossier endpoint for an opportunity candidate.
    Aggregates technical setup details, invalidation rules, fundamental traffic lights,
    verified news catalysts, sector relative momentum, and 4-factor scoring breakdown.
    Strictly informational — zero control over deterministic order execution.
    """
    sym = symbol.upper().strip()

    # 1. Instrument metadata
    inst = db.query(Instrument).filter(Instrument.symbol == sym, Instrument.market == market).first()
    sector = getattr(inst, "sector", "General") if inst else "General"
    tier = getattr(inst, "universe_tier", "Small") if inst else "Small"
    last_price = inst.last_price if inst and inst.last_price else 0.0

    # 2. Latest Signal (if any)
    sig = db.query(Signal).filter(Signal.symbol == sym, Signal.market == market).order_by(Signal.created_at.desc()).first()

    # 3. DecisionAudit and stages (if any)
    audit = db.query(DecisionAudit).filter(DecisionAudit.symbol == sym, DecisionAudit.market == market).order_by(DecisionAudit.created_at.desc()).first()
    stages, blocked_reason = [], None
    if audit:
        stage_rows = db.query(DecisionStageResult).filter(DecisionStageResult.audit_id == audit.id).all()
        stages, blocked_reason = _format_audit_stages(stage_rows)

    # 4. FundamentalSnapshot
    snap = db.query(FundamentalSnapshot).filter(FundamentalSnapshot.symbol == sym, FundamentalSnapshot.market == market).order_by(FundamentalSnapshot.as_of.desc()).first()
    fund_dict = None
    if snap and snap.lights_json:
        try:
            fund_dict = json.loads(snap.lights_json)
        except Exception:
            fund_dict = None
    if not fund_dict and snap:
        fund_dict = fundamentals_engine.evaluate_traffic_lights(sym, {
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
        }, market=market)

    # 5. News events
    cutoff = datetime.date.today() - datetime.timedelta(days=30)
    news_rows = (
        db.query(NewsEvent)
        .filter(
            NewsEvent.symbol == sym,
            NewsEvent.published_at >= datetime.datetime.combine(cutoff, datetime.time.min),
        )
        .order_by(NewsEvent.published_at.desc())
        .limit(10)
        .all()
    )
    catalysts = [
        {
            "id": nr.id,
            "title": nr.title,
            "source": nr.source or "Unknown",
            "source_url": nr.url,
            "published_at": nr.published_at.isoformat() if nr.published_at else None,
            "severity": nr.severity or "CLEAR",
            "materiality": nr.materiality,
            "match_confidence": nr.match_confidence,
        }
        for nr in news_rows
    ]

    rs_rank = sig.rs_rank if sig else 0.5
    setup_name = sig.setup if sig else "MONITORING"
    trigger = sig.trigger if sig else (last_price or 0.0)
    stop = sig.stop if sig else (last_price * 0.95 if last_price else 0.0)
    target1 = sig.target1 if sig else (last_price * 1.10 if last_price else 0.0)
    news_cov = json.loads(sig.news_flags_json) if sig and sig.news_flags_json else {"status": "CLEAR"}

    # Sector Trend & Group Relative Strength Computation (Phase 3.5 fix)
    sector_signals = (
        db.query(Signal)
        .join(Instrument, (Instrument.symbol == Signal.symbol) & (Instrument.market == Signal.market))
        .filter(Instrument.sector == sector, Signal.market == market)
        .all()
    )
    if sector_signals:
        sec_rs_scores = [s.rs_rank for s in sector_signals if s.rs_rank is not None]
        sec_avg_rs = sum(sec_rs_scores) / len(sec_rs_scores) if sec_rs_scores else rs_rank
    else:
        sec_avg_rs = rs_rank

    sec_trend = "LEADING" if sec_avg_rs >= 0.65 else ("LAGGING" if sec_avg_rs <= 0.35 else "NEUTRAL")

    factors = compute_factor_score_breakdown(
        symbol=sym,
        setup=setup_name,
        trigger=trigger,
        stop=stop,
        rs_rank=rs_rank,
        sector_name=sector,
        sector_rs_rank=sec_avg_rs,
        sector_trend=sec_trend,
        news_cov=news_cov,
        fund_dict=fund_dict,
        catalyst_count=len(catalysts),
    )

    currency = "₹" if market == "IN" else "$"
    invalidation_rules = [
        f"Hard Stop: Intraday break or close below {currency}{stop:.2f}" if stop > 0 else "Hard Stop: Set upon trigger confirmation",
        "Time Stop: 20 completed exchange sessions without reaching Target 1",
        "Earnings Blackout: Mandatory exit if unannounced earnings report is scheduled within 3 trading days",
    ]
    if blocked_reason:
        invalidation_rules.append(
            f"Active Invalidation Gate: {blocked_reason.get('check', 'Gate')} blocked setup ({blocked_reason.get('value')})"
        )

    # Dynamic AI Research Dossier Synthesis (Phase 3.4 & 3.5)
    ai_thesis = ai_research_assistant.analyze_candidate_thesis(
        symbol=sym,
        sector=sector,
        current_price=last_price or trigger,
        momentum_score=rs_rank,
        regime_status="BULLISH",
        catalysts=catalysts,
        fundamental_lights=fund_dict,
        setup_details={
            "pattern": setup_name,
            "trigger": trigger,
            "stop": stop,
            "risk_pct": round((trigger - stop) / trigger * 100.0, 1) if (trigger > 0 and stop > 0 and trigger > stop) else 5.0,
        },
        sector_trend=sec_trend,
    )

    return {
        "symbol": sym,
        "market": market,
        "sector": sector,
        "tier": tier,
        "last_price": last_price or trigger,
        "setup": {
            "pattern": setup_name,
            "trigger": round(trigger, 2),
            "stop": round(stop, 2),
            "target1": round(target1, 2),
            "risk_reward_ratio": round((target1 - trigger) / (trigger - stop), 2) if (trigger > stop and stop > 0 and target1 > trigger) else 0.0,
            "invalidation_rules": invalidation_rules,
        },
        "state": sig.state if sig else "MONITORING",
        "factors": factors.model_dump(),
        "evidence": {
            "fundamental_snapshot_id": snap.id if snap else None,
            "fundamental_as_of": snap.as_of.isoformat() if snap and snap.as_of else None,
            "fundamental_source": snap.source if snap else None,
            "catalysts": catalysts,
            "sector_name": sector,
            "sector_rs_rank": round(sec_avg_rs, 2),
            "sector_trend": sec_trend,
        },
        "decision_stages": stages,
        "blocked_reason": blocked_reason,
        "fundamentals": fund_dict,
        "ai_thesis": ai_thesis,
        "disclaimer": "AI Informational Research Dossier Only — Not a Trading Directive. Deterministic trading logic governs all orders.",
    }

