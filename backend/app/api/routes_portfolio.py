import datetime
import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import BrokerSnapshot, ImportedReport, Position, ReportTrade
from app.providers.kite_provider import parse_zerodha_console_csv
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class TrackSwingRequest(BaseModel):
    initial_stop: float
    target1: float
    notes: Optional[str] = None


@router.get("/portfolio/kite/login-url")
def get_kite_login_url():
    """Returns the login URL for the 'Connect Zerodha' button."""
    url = provider_manager.kite.get_login_url()
    return {"login_url": url}


@router.get("/portfolio/kite/callback")
def handle_kite_callback(request_token: str, db: Session = Depends(get_db)):
    """Receives request_token, exchanges it for the daily access token."""
    try:
        session_data = provider_manager.kite.exchange_request_token(request_token)
        return {
            "status": "SUCCESS",
            "message": "Zerodha Kite Personal session established successfully.",
            "user_id": session_data.get("user_id"),
        }
    except Exception as e:
        logger.error(f"Kite callback error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/portfolio/status")
def get_portfolio_status():
    """Returns connection state, token expiry, last sync time."""
    return provider_manager.kite.status()


@router.post("/portfolio/sync")
def sync_portfolio_now(db: Session = Depends(get_db)):
    """Executes an immediate read-only sync of holdings, positions, and funds from Kite Personal."""
    holdings = provider_manager.kite.holdings()
    positions = provider_manager.kite.positions()
    funds = provider_manager.kite.funds()

    # Save broker snapshot to DB
    now = datetime.datetime.utcnow()
    snap = BrokerSnapshot(
        broker="ZERODHA_KITE",
        kind="FULL_SYNC",
        ts=now,
        payload_json=json.dumps({"holdings": holdings, "positions": positions, "funds": funds}),
    )
    db.add(snap)
    db.commit()

    return {
        "status": "SYNCED",
        "timestamp": now.isoformat(),
        "holdings_count": len(holdings),
        "positions_count": len(positions),
        "available_cash": funds.get("available_cash", 0.0),
    }


@router.get("/portfolio/holdings")
def get_holdings():
    """Returns synced holdings from Kite Personal."""
    return provider_manager.kite.holdings()


@router.get("/portfolio/valuation")
def get_portfolio_valuation():
    """Calculates live portfolio valuation comparing Broker-Reported vs Angel One Calculated P&L."""
    holdings = provider_manager.kite.holdings()
    symbols = [h["tradingsymbol"] for h in holdings]
    quotes = provider_manager.get_quotes(symbols, market="IN")

    now = datetime.datetime.utcnow()
    total_invested = 0.0
    total_broker_val = 0.0
    total_calc_val = 0.0
    items = []

    for h in holdings:
        sym = h["tradingsymbol"]
        qty = int(h["quantity"])
        avg_price = float(h["average_price"])
        invested = qty * avg_price
        total_invested += invested

        # Broker-reported
        broker_last_price = float(h.get("last_price", avg_price))
        broker_pnl = float(h.get("pnl", 0.0))
        broker_val = invested + broker_pnl
        total_broker_val += broker_val

        # Our Angel One calculated valuation
        q = quotes.get(sym)
        angel_ltp = q.last_price if q else broker_last_price
        calc_val = qty * angel_ltp
        total_calc_val += calc_val
        calc_pnl = calc_val - invested
        calc_pnl_pct = (calc_pnl / invested * 100.0) if invested > 0 else 0.0

        items.append(
            {
                "symbol": sym,
                "quantity": qty,
                "average_price": round(avg_price, 2),
                "broker_reported": {
                    "last_price": round(broker_last_price, 2),
                    "pnl": round(broker_pnl, 2),
                    "source": "Zerodha (Snapshot)",
                    "timestamp": now.isoformat(),
                },
                "calculated": {
                    "last_price": round(angel_ltp, 2),
                    "pnl": round(calc_pnl, 2),
                    "pnl_pct": round(calc_pnl_pct, 2),
                    "source": q.source if q else "AngelOne (Fallback)",
                    "is_realtime": q.is_realtime if q else False,
                    "is_stale": q.is_stale if q else True,
                    "timestamp": q.timestamp.isoformat() if q else now.isoformat(),
                },
            }
        )

    return {
        "summary": {
            "total_invested": round(total_invested, 2),
            "broker_reported_value": round(total_broker_val, 2),
            "calculated_live_value": round(total_calc_val, 2),
            "calculated_live_pnl": round(total_calc_val - total_invested, 2),
            "as_of": now.isoformat(),
        },
        "holdings": items,
    }


@router.post("/portfolio/track/{symbol}")
def track_holding_as_swing(
    symbol: str,
    req: TrackSwingRequest,
    db: Session = Depends(get_db),
):
    """Enables swing trading tracking for an existing broker holding."""
    clean_sym = symbol.strip().upper()
    holdings = provider_manager.kite.holdings()
    matched = next((h for h in holdings if h["tradingsymbol"] == clean_sym), None)
    if not matched:
        raise HTTPException(status_code=404, detail="Holding not found in Zerodha portfolio")

    qty = int(matched["quantity"])
    avg_price = float(matched["average_price"])

    pos = Position(
        symbol=clean_sym,
        market="IN",
        source="KITE",
        tracked_as_swing=True,
        mode="LIVE",
        entry_date=datetime.date.today(),
        entry_price=avg_price,
        qty=qty,
        initial_stop=req.initial_stop,
        active_stop=req.initial_stop,
        target1=req.target1,
        status="OPEN",
        notes=req.notes,
    )
    db.add(pos)
    db.commit()
    return {"status": "TRACKING_ENABLED", "position_id": pos.id}


@router.post("/portfolio/import")
async def import_zerodha_console_csv(
    kind: str = Query("TRADEBOOK", pattern="^(TRADEBOOK|PNL|CHARGES)$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Uploads Zerodha Console CSV report with duplicate file detection."""
    content = (await file.read()).decode("utf-8", errors="ignore")
    parsed = parse_zerodha_console_csv(content, kind=kind)
    file_hash = parsed["file_hash"]

    # Deduplicate check
    existing = db.query(ImportedReport).filter(ImportedReport.file_hash == file_hash).first()
    if existing:
        return {
            "status": "ALREADY_IMPORTED",
            "message": "This file has already been imported previously.",
            "imported_at": existing.imported_at.isoformat(),
            "row_count": existing.row_count,
        }

    rep = ImportedReport(
        kind=kind,
        file_hash=file_hash,
        row_count=parsed["row_count"],
    )
    db.add(rep)
    db.flush()

    for t in parsed["trades"]:
        try:
            trade_d = datetime.date.fromisoformat(t["trade_date"])
        except Exception:
            trade_d = datetime.date.today()

        rt = ReportTrade(
            report_id=rep.id,
            symbol=t["symbol"],
            side=t["side"],
            qty=t["qty"],
            price=t["price"],
            trade_date=trade_d,
            charges_json=json.dumps(t.get("raw", {})),
        )
        db.add(rt)

    db.commit()

    return {
        "status": "IMPORTED",
        "file_hash": file_hash,
        "rows_processed": parsed["row_count"],
        "valid_trades_saved": parsed["valid_trades_count"],
    }
