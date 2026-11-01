import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.costs import CostModel
from app.models import Fill, Journal, Position
from app.providers.manager import provider_manager

router = APIRouter()


class CreatePositionRequest(BaseModel):
    symbol: str
    market: str = "IN"
    entry_price: float
    qty: int
    initial_stop: float
    target1: float
    entry_date: Optional[str] = None
    signal_id: Optional[int] = None
    mode: str = "LIVE"  # LIVE or PAPER
    notes: Optional[str] = None


class UpdatePositionRequest(BaseModel):
    active_stop: Optional[float] = None
    target1: Optional[float] = None
    notes: Optional[str] = None


class ClosePositionRequest(BaseModel):
    exit_price: float
    exit_date: Optional[str] = None
    exit_reason: str
    qty: Optional[int] = None
    note: Optional[str] = None


@router.get("/positions")
def list_positions(
    status: str = "OPEN",
    market: Optional[str] = None,
    mode: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lists tracked swing positions with current quotes and unrealized P&L."""
    query = db.query(Position)
    if status:
        query = query.filter(Position.status == status)
    if market:
        query = query.filter(Position.market == market)
    if mode:
        query = query.filter(Position.mode == mode)

    positions = query.order_by(Position.entry_date.desc()).all()
    symbols = [p.symbol for p in positions]
    quotes = provider_manager.get_quotes(symbols, market="IN")

    result = []
    for p in positions:
        q = quotes.get(p.symbol)
        curr_price = q.last_price if q else p.entry_price
        unrealized_pnl = (curr_price - p.entry_price) * p.qty
        unrealized_pct = ((curr_price - p.entry_price) / p.entry_price * 100.0) if p.entry_price > 0 else 0.0

        r0 = p.entry_price - p.initial_stop
        unrealized_r = (curr_price - p.entry_price) / r0 if r0 > 0 else 0.0
        days_held = (datetime.date.today() - p.entry_date).days

        result.append(
            {
                "id": p.id,
                "symbol": p.symbol,
                "market": p.market,
                "source": p.source,
                "mode": p.mode,
                "entry_date": p.entry_date.isoformat(),
                "entry_price": p.entry_price,
                "qty": p.qty,
                "initial_stop": p.initial_stop,
                "active_stop": p.active_stop,
                "target1": p.target1,
                "status": p.status,
                "current_price": round(curr_price, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pct": round(unrealized_pct, 2),
                "unrealized_r": round(unrealized_r, 2),
                "days_held": days_held,
                "notes": p.notes,
                "as_of": q.timestamp.isoformat() if q else None,
            }
        )

    return result


@router.post("/positions")
def create_position(req: CreatePositionRequest, db: Session = Depends(get_db)):
    """Owner logs: 'I took this trade'."""
    entry_d = datetime.date.fromisoformat(req.entry_date) if req.entry_date else datetime.date.today()

    pos = Position(
        symbol=req.symbol.upper(),
        market=req.market.upper(),
        source="MANUAL",
        tracked_as_swing=True,
        signal_id=req.signal_id,
        mode=req.mode.upper(),
        entry_date=entry_d,
        entry_price=req.entry_price,
        qty=req.qty,
        initial_stop=req.initial_stop,
        active_stop=req.initial_stop,
        target1=req.target1,
        status="OPEN",
        notes=req.notes,
    )
    db.add(pos)
    db.flush()

    fill = Fill(
        position_id=pos.id,
        side="BUY",
        date=entry_d,
        price=req.entry_price,
        qty=req.qty,
        fees_total=0.0,
    )
    db.add(fill)
    db.commit()

    return {"status": "CREATED", "position_id": pos.id}


@router.patch("/positions/{position_id}")
def update_position(
    position_id: int, req: UpdatePositionRequest, db: Session = Depends(get_db)
):
    """Edits active stop loss or notes."""
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    if req.active_stop is not None:
        pos.active_stop = req.active_stop
    if req.target1 is not None:
        pos.target1 = req.target1
    if req.notes is not None:
        pos.notes = req.notes

    db.commit()
    return {"status": "UPDATED", "position_id": pos.id}


@router.post("/positions/{position_id}/close")
def close_position(
    position_id: int, req: ClosePositionRequest, db: Session = Depends(get_db)
):
    """Owner records exit -> closes position and creates Trade Journal row."""
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    exit_d = datetime.date.fromisoformat(req.exit_date) if req.exit_date else datetime.date.today()
    exit_qty = req.qty or pos.qty

    # Calculate P&L and R-multiple
    cost_model = CostModel(pos.market)
    r_initial = pos.entry_price - pos.initial_stop
    pnl_per_share = req.exit_price - pos.entry_price
    gross_pnl = pnl_per_share * exit_qty

    cost_breakdown = cost_model.calculate_round_trip(
        pos.entry_price, exit_qty, (r_initial * exit_qty) if r_initial > 0 else 100.0
    )
    net_pnl = gross_pnl - cost_breakdown.total_cost
    pnl_pct = (pnl_per_share / pos.entry_price * 100.0) if pos.entry_price > 0 else 0.0
    r_multiple = (net_pnl / (r_initial * exit_qty)) if r_initial > 0 else 0.0
    holding_days = max(1, (exit_d - pos.entry_date).days)

    # Save Fill
    fill = Fill(
        position_id=pos.id,
        side="SELL",
        date=exit_d,
        price=req.exit_price,
        qty=exit_qty,
        fees_total=cost_breakdown.total_cost,
    )
    db.add(fill)

    # Save Journal
    journal_entry = Journal(
        position_id=pos.id,
        symbol=pos.symbol,
        market=pos.market,
        entry_date=pos.entry_date,
        entry_price=pos.entry_price,
        exit_date=exit_d,
        exit_price=req.exit_price,
        qty=exit_qty,
        exit_reason=req.exit_reason,
        pnl_amount=round(net_pnl, 2),
        pnl_pct=round(pnl_pct, 2),
        r_multiple=round(r_multiple, 2),
        holding_days=holding_days,
        fees_total=round(cost_breakdown.total_cost, 2),
        note=req.note,
    )
    db.add(journal_entry)

    pos.status = "CLOSED"
    db.commit()

    return {
        "status": "CLOSED",
        "journal_id": journal_entry.id,
        "pnl_amount": round(net_pnl, 2),
        "r_multiple": round(r_multiple, 2),
    }


@router.get("/journal")
def get_journal(limit: int = 100, db: Session = Depends(get_db)):
    """Returns trade journal history."""
    entries = (
        db.query(Journal)
        .order_by(Journal.exit_date.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": j.id,
            "position_id": j.position_id,
            "symbol": j.symbol,
            "market": j.market,
            "entry_date": j.entry_date.isoformat() if j.entry_date else None,
            "entry_price": j.entry_price,
            "exit_date": j.exit_date.isoformat(),
            "exit_price": j.exit_price,
            "qty": j.qty,
            "exit_reason": j.exit_reason,
            "pnl_amount": j.pnl_amount,
            "pnl_pct": j.pnl_pct,
            "r_multiple": j.r_multiple,
            "holding_days": j.holding_days,
            "fees_total": j.fees_total,
            "note": j.note,
        }
        for j in entries
    ]


@router.get("/stats")
def get_performance_stats(db: Session = Depends(get_db)):
    """Returns overall performance analytics from journal entries."""
    entries = db.query(Journal).order_by(Journal.exit_date.asc()).all()

    total_trades = len(entries)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_realized_pnl": 0.0,
            "avg_r_multiple": 0.0,
            "equity_curve": [],
        }

    wins = [j for j in entries if j.pnl_amount > 0]
    losses = [j for j in entries if j.pnl_amount <= 0]
    win_rate = (len(wins) / total_trades) * 100.0

    gross_profit = sum(w.pnl_amount for w in wins)
    gross_loss = abs(sum(l.pnl_amount for l in losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    total_pnl = sum(j.pnl_amount for j in entries)
    avg_r = sum(j.r_multiple for j in entries) / total_trades

    equity = 17500.0
    equity_curve = [{"date": entries[0].exit_date.isoformat(), "equity": equity}]
    for j in entries:
        equity += j.pnl_amount
        equity_curve.append({"date": j.exit_date.isoformat(), "equity": round(equity, 2)})

    return {
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "total_realized_pnl": round(total_pnl, 2),
        "avg_r_multiple": round(avg_r, 2),
        "equity_curve": equity_curve,
    }

