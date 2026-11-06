import io
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.universe import universe_manager
from app.engine.corporate_actions import verify_corporate_action_adjustments_sample
from app.providers.manager import provider_manager
from app.providers.angelone_provider import AngelOneProvider

router = APIRouter(prefix="/universe", tags=["Universe"])


@router.get("/coverage")
def get_universe_coverage(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Returns the full-universe coverage census and pipeline:
    Listed -> has data -> enough history -> liquid -> passes filters -> scanned.
    """
    coverage = universe_manager.evaluate_coverage(market=market, db=db)
    return coverage


@router.get("/coverage/export-csv")
def export_universe_coverage_csv(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Download full universe coverage as a CSV file with downloadable reasons."""
    coverage = universe_manager.evaluate_coverage(market=market, db=db)
    csv_str = universe_manager.generate_coverage_csv(coverage)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=universe_coverage_{market.lower()}.csv"},
    )


@router.post("/refresh-master")
def refresh_scrip_master(
    market: str = Query("IN", pattern="^(IN|US)$"),
):
    """Triggers download of the latest official Angel One scrip master and refreshes local cache."""
    if market.upper() != "IN":
        return {"status": "SKIPPED", "detail": "Master refresh only applicable to IN (Angel One)"}
    ao = AngelOneProvider()
    ok = ao.refresh_instruments()
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to download Angel One scrip master")
    return {"status": "SUCCESS", "detail": "Instrument master refreshed and cached locally"}


@router.get("/audit-splits")
def audit_split_adjustments(
    sample_symbols: Optional[str] = Query(None, description="Comma-separated symbols to audit"),
    db: Session = Depends(get_db),
):
    """Audits sample instruments for corporate action adjustment integrity, flagging unadjusted series."""
    syms = [s.strip().upper() for s in sample_symbols.split(",")] if sample_symbols else ["TATASTEEL", "RELIANCE", "NESTLEIND", "BAJAJFINSV", "EICHERMOT", "BEL", "BPCL"]
    from datetime import date, timedelta
    start = date(2020, 1, 1)
    end = date.today()
    bars_dict = provider_manager.get_daily_bars(syms, start, end, market="IN", db=db)
    audit_res = verify_corporate_action_adjustments_sample(bars_dict, sample_symbols=syms)
    return audit_res

