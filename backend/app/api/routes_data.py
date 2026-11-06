import datetime
import threading
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.calendars import get_expected_trading_days
from app.engine.historical_ingestion import historical_ingestion_engine
from app.engine.universe import universe_manager
from app.models import DailyBar, IngestionCheckpoint, IngestionRun

router = APIRouter()


class IngestionTriggerRequest(BaseModel):
    market: str = "IN"  # IN, US, ALL
    target_sessions: int = 1250
    run_id: Optional[str] = None


@router.get("/data/coverage")
def get_data_coverage(market: Optional[str] = None, db: Session = Depends(get_db)):
    """Provides complete historical market data coverage and research readiness audit.
    Shows:
    - Total symbols and bars count
    - Earliest and latest historical dates
    - Percentage and count meeting 300, 750, and 1,250 sessions
    - Missing-bar counts (using exchange calendars)
    - Last successful ingestion timestamp
    - Provider provenance and split-adjustment status
    - Explicit survivorship bias and feed limitations notice
    """
    in_stocks = {s.symbol: s for s in universe_manager.load_universe("IN")}
    us_stocks = {s.symbol: s for s in universe_manager.load_universe("US")}

    # Query bars_daily grouped by symbol
    q = (
        db.query(
            DailyBar.symbol,
            func.count(DailyBar.date).label("bar_count"),
            func.min(DailyBar.date).label("min_date"),
            func.max(DailyBar.date).label("max_date"),
            func.max(DailyBar.source).label("source"),
            func.bool_or(DailyBar.is_split_adjusted).label("split_adj"),
            func.max(DailyBar.ingested_at).label("last_ingest"),
        )
        .group_by(DailyBar.symbol)
    )

    rows = q.all()
    symbol_stats = {r.symbol: r for r in rows}

    # All eligible symbols
    if market and market.upper() in ("IN", "NSE"):
        eligible_symbols = sorted(list(in_stocks.keys()))
    elif market and market.upper() == "US":
        eligible_symbols = sorted(list(us_stocks.keys()))
    else:
        eligible_symbols = sorted(list(set(list(in_stocks.keys()) + list(us_stocks.keys()))))

    symbols_list = []
    total_bars = 0
    meets_300 = 0
    meets_750 = 0
    meets_1250 = 0

    in_counts = {"total": 0, "meets_300": 0, "meets_750": 0, "meets_1250": 0}
    us_counts = {"total": 0, "meets_300": 0, "meets_750": 0, "meets_1250": 0}

    for sym in eligible_symbols:
        sym_mkt = "US" if sym in us_stocks else "IN"
        stat = symbol_stats.get(sym)

        if stat:
            bars_count = int(stat.bar_count)
            min_d = stat.min_date
            max_d = stat.max_date
            source = stat.source
            split_adj = bool(stat.split_adj)
            last_ingest = stat.last_ingest.isoformat() if stat.last_ingest else None
            total_bars += bars_count

            # Calculate missing sessions using actual exchange calendars
            if min_d and max_d:
                expected_days = get_expected_trading_days(sym_mkt, min_d, max_d)
                missing_count = max(0, len(expected_days) - bars_count)
            else:
                missing_count = 0

            # Research Readiness
            if bars_count >= 1250:
                readiness = "AVAILABLE"
                meets_1250 += 1
                meets_750 += 1
                meets_300 += 1
            elif bars_count >= 750:
                readiness = "PARTIAL_INTERIM"
                meets_750 += 1
                meets_300 += 1
            elif bars_count >= 300:
                readiness = "PARTIAL_MINIMUM"
                meets_300 += 1
            else:
                readiness = "INSUFFICIENT_DATA"
        else:
            bars_count = 0
            min_d, max_d = None, None
            source = "none"
            split_adj = False
            last_ingest = None
            missing_count = 0
            readiness = "INSUFFICIENT_DATA"

        if sym_mkt == "IN":
            in_counts["total"] += 1
            if bars_count >= 300:
                in_counts["meets_300"] += 1
            if bars_count >= 750:
                in_counts["meets_750"] += 1
            if bars_count >= 1250:
                in_counts["meets_1250"] += 1
        else:
            us_counts["total"] += 1
            if bars_count >= 300:
                us_counts["meets_300"] += 1
            if bars_count >= 750:
                us_counts["meets_750"] += 1
            if bars_count >= 1250:
                us_counts["meets_1250"] += 1

        symbols_list.append({
            "symbol": sym,
            "market": sym_mkt,
            "sessions": bars_count,
            "earliest_date": str(min_d) if min_d else None,
            "latest_date": str(max_d) if max_d else None,
            "missing_sessions": missing_count,
            "provider": source,
            "split_adjusted": split_adj,
            "last_ingested": last_ingest,
            "readiness": readiness,
        })

    n_total = len(eligible_symbols)
    pct_300 = round((meets_300 / n_total * 100.0), 1) if n_total > 0 else 0.0
    pct_750 = round((meets_750 / n_total * 100.0), 1) if n_total > 0 else 0.0
    pct_1250 = round((meets_1250 / n_total * 100.0), 1) if n_total > 0 else 0.0

    return {
        "summary": {
            "total_symbols": n_total,
            "total_bars": total_bars,
            "meets_300_sessions": meets_300,
            "meets_300_pct": pct_300,
            "meets_750_sessions": meets_750,
            "meets_750_pct": pct_750,
            "meets_1250_sessions": meets_1250,
            "meets_1250_pct": pct_1250,
            "in_market": in_counts,
            "us_market": us_counts,
        },
        "limitations": [
            "Survivorship Bias: Historical universe is reconstructed using current index constituents. Delisted or dropped historical constituents are not present.",
            "US Data Feed: Alpaca provider uses the IEX exchange feed (~2.5% of US consolidated volume). High-volume mega-caps provide reliable pricing; off-exchange odd lots may differ from CTA/UTP tape.",
            "Research Gate: Minimum 300 trading sessions strictly enforced. Any symbol under 300 sessions returns INSUFFICIENT_DATA and cannot be backtested.",
        ],
        "symbols": symbols_list,
    }


@router.post("/data/ingest")
def trigger_historical_ingestion(req: IngestionTriggerRequest, db: Session = Depends(get_db)):
    """Triggers or resumes background incremental historical ingestion."""
    run = historical_ingestion_engine.get_or_create_run(
        db, market=req.market, target_sessions=req.target_sessions, run_id=req.run_id
    )

    # Launch in background thread to return response immediately
    def _run_bg():
        historical_ingestion_engine.run_pipeline(
            market=req.market, target_sessions=req.target_sessions, run_id=run.id
        )

    t = threading.Thread(target=_run_bg, daemon=True, name=f"ingest_{run.id}")
    t.start()

    return {
        "run_id": run.id,
        "market": run.market,
        "status": run.status,
        "total_symbols": run.total_symbols,
        "target_sessions": run.target_sessions,
        "message": f"Historical ingestion run {run.id} started in background.",
    }


@router.get("/data/ingest/status")
def get_ingestion_status(run_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Returns the live status, completed checkpoints, and progress of historical ingestion."""
    if run_id:
        run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    else:
        run = db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).first()

    if not run:
        return {"active": False, "message": "No ingestion runs found."}

    checkpoints = db.query(IngestionCheckpoint).filter(IngestionCheckpoint.run_id == run.id).all()
    completed = sum(1 for c in checkpoints if c.status in ("COMPLETED", "PARTIAL"))
    failed = sum(1 for c in checkpoints if c.status == "FAILED")
    in_progress = sum(1 for c in checkpoints if c.status == "IN_PROGRESS")
    pending = sum(1 for c in checkpoints if c.status == "PENDING")

    total = len(checkpoints)
    pct = round((completed / total * 100.0), 1) if total > 0 else 0.0

    return {
        "run_id": run.id,
        "market": run.market,
        "target_sessions": run.target_sessions,
        "status": run.status,
        "total_symbols": total,
        "completed": completed,
        "failed": failed,
        "in_progress": in_progress,
        "pending": pending,
        "progress_pct": pct,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }

