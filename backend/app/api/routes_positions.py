import datetime
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.db import get_db
from app.engine.calendars import get_completed_sessions_held_count
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
    exit_reason: str = "MANUAL"
    qty: Optional[int] = None
    note: Optional[str] = None
    action_type: Optional[str] = None  # "PARTIAL_TARGET" | "MANUAL_REDUCTION" | "FULL_EXIT" | None
    idempotency_key: Optional[str] = None


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
        initial_qty=req.qty,
        highest_price_since_entry=req.entry_price,
        target_partial_completed=False,
        target_partial_qty=0,
        total_reduced_qty=0,
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
        fill_reason="ENTRY",
    )
    db.add(fill)
    db.commit()

    return {"status": "CREATED", "position_id": pos.id}


@router.patch("/positions/{position_id}")
def update_position(
    position_id: int, req: UpdatePositionRequest, db: Session = Depends(get_db)
):
    """Edits active stop loss or notes."""
    pos = db.query(Position).filter(Position.id == position_id).with_for_update().first()
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
    """Owner records exit -> supports atomic partial tranche reductions or full exits with Journal accounting."""
    pos = db.query(Position).filter(Position.id == position_id).with_for_update().first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    # Idempotency protection: prevent duplicate processing on retries
    if req.idempotency_key:
        existing_fill = db.query(Fill).filter(Fill.idempotency_key == req.idempotency_key).first()
        if existing_fill:
            existing_j = (
                db.query(Journal)
                .filter(Journal.position_id == pos.id)
                .order_by(Journal.id.desc())
                .first()
            )
            return {
                "status": "IDEMPOTENT_DUPLICATE",
                "position_id": pos.id,
                "remaining_qty": pos.qty,
                "journal_id": getattr(existing_j, "id", None),
                "action_type": existing_fill.fill_reason,
                "message": f"Fill with idempotency key '{req.idempotency_key}' already processed.",
            }

    if pos.status != "OPEN":
        raise HTTPException(status_code=400, detail=f"Cannot exit position in status '{pos.status}'")

    if req.exit_price <= 0:
        raise HTTPException(status_code=400, detail="Exit price must be positive")

    exit_qty = req.qty if req.qty is not None else pos.qty
    if exit_qty <= 0:
        raise HTTPException(status_code=400, detail="Exit quantity must be positive")

    if exit_qty > pos.qty:
        raise HTTPException(
            status_code=400,
            detail=f"Exit quantity {exit_qty} exceeds remaining position quantity {pos.qty}",
        )

    # Resolve action explicitly or validate unambiguous reduction
    if req.action_type is not None:
        if req.action_type not in ("PARTIAL_TARGET", "MANUAL_REDUCTION", "FULL_EXIT"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action_type '{req.action_type}'. Must be PARTIAL_TARGET, MANUAL_REDUCTION, or FULL_EXIT.",
            )
        if req.action_type == "FULL_EXIT" and exit_qty < pos.qty:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot request FULL_EXIT with partial quantity ({exit_qty} < {pos.qty}).",
            )
        if req.action_type in ("PARTIAL_TARGET", "MANUAL_REDUCTION") and exit_qty == pos.qty:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot request partial action '{req.action_type}' when exiting full remaining quantity {pos.qty}.",
            )
        resolved_action = req.action_type
    else:
        # Backward compatibility with existing frontend calls: deduce without guessing
        if exit_qty == pos.qty:
            resolved_action = "FULL_EXIT"
        else:
            if req.exit_reason in ("Target 1 Reached (2R)", "TARGET_1", "PARTIAL_PROFIT"):
                resolved_action = "PARTIAL_TARGET"
            elif req.exit_reason in ("Manual Discretionary Exit", "MANUAL_REDUCTION", "TRIM"):
                resolved_action = "MANUAL_REDUCTION"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ambiguous exit request: partial quantity {exit_qty} specified for exit reason '{req.exit_reason}' without explicit action_type.",
                )

    exit_d = datetime.date.fromisoformat(req.exit_date) if req.exit_date else datetime.date.today()

    # Calculate tranche-specific P&L and R-multiple
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

    # Holding sessions count
    exit_dt_approx = datetime.datetime.combine(exit_d, datetime.time(16, 0), tzinfo=datetime.timezone.utc)
    holding_sessions = get_completed_sessions_held_count(pos.market, pos.entry_date, exit_dt_approx)

    # Atomic database transaction
    try:
        pos.qty -= exit_qty
        pos.total_reduced_qty = (pos.total_reduced_qty or 0) + exit_qty

        if resolved_action == "PARTIAL_TARGET":
            pos.target_partial_completed = True
            pos.target_partial_qty = (pos.target_partial_qty or 0) + exit_qty

        is_fully_closed = (pos.qty == 0)
        if is_fully_closed:
            pos.status = "CLOSED"

        # 1. Save Fill
        fill = Fill(
            position_id=pos.id,
            side="SELL",
            date=exit_d,
            price=req.exit_price,
            qty=exit_qty,
            fees_total=cost_breakdown.total_cost,
            fill_reason=resolved_action,
            idempotency_key=req.idempotency_key,
        )
        db.add(fill)

        # 2. Save Journal Row for this tranche
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
            holding_days=holding_sessions,
            fees_total=round(cost_breakdown.total_cost, 2),
            note=req.note,
        )
        db.add(journal_entry)

        db.commit()
    except IntegrityError as ie:
        db.rollback()
        if req.idempotency_key:
            existing_fill = db.query(Fill).filter(Fill.idempotency_key == req.idempotency_key).first()
            if existing_fill:
                existing_j = (
                    db.query(Journal)
                    .filter(Journal.position_id == pos.id)
                    .order_by(Journal.id.desc())
                    .first()
                )
                return {
                    "status": "IDEMPOTENT_DUPLICATE",
                    "position_id": pos.id,
                    "remaining_qty": pos.qty,
                    "journal_id": getattr(existing_j, "id", None),
                    "action_type": existing_fill.fill_reason,
                    "message": f"Fill with idempotency key '{req.idempotency_key}' already processed.",
                }
        logger.error(f"Integrity error during position exit transaction: {ie}")
        raise HTTPException(status_code=400, detail=f"Database integrity constraint violated: {ie}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error during position exit transaction: {e}")
        raise HTTPException(status_code=500, detail=f"Database transaction failed during position exit: {e}")

    return {
        "status": "CLOSED" if is_fully_closed else "PARTIALLY_CLOSED",
        "position_id": pos.id,
        "remaining_qty": pos.qty,
        "journal_id": journal_entry.id,
        "pnl_amount": round(net_pnl, 2),
        "r_multiple": round(r_multiple, 2),
        "action_type": resolved_action,
        "target_partial_completed": pos.target_partial_completed,
        "total_reduced_qty": pos.total_reduced_qty,
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

