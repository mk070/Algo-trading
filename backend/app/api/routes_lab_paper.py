"""Strategy Lab — Paper Evaluation API Routes.

Endpoints:
  POST /api/lab/study/{study_id}/evaluate  — trigger evaluation (requires LAB_PAPER_ENABLED)
  GET  /api/lab/study/{study_id}/paper     — paper study details with staleness info
  GET  /api/lab/study/{study_id}/eval-status — evaluation audit log
  POST /api/lab/jobs/nightly               — nightly batch for all active studies
  GET  /api/lab/study/{study_id}/tomorrow  — tomorrow's planned orders
  GET  /api/lab/trade/paper/{trade_id}/chart — candle bars + trade markers for a paper trade
  GET  /api/lab/trade/backtest/{trade_id}/chart — candle bars + markers for a backtest trade
"""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lab", tags=["Strategy Lab — Paper"])


def _require_lab_paper():
    if not settings.lab_paper_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Lab paper evaluation is currently disabled. "
                "Set LAB_PAPER_ENABLED=true in the deployment environment to activate."
            ),
        )


# ─── Trigger evaluation ───────────────────────────────────────────────────────

@router.post("/study/{study_id}/evaluate")
def trigger_evaluate(study_id: str, db: Session = Depends(get_db)):
    """Trigger a synchronous paper evaluation for a specific study.

    Requires LAB_PAPER_ENABLED=true. Runs evaluate_study() + persist_evaluation_result().
    Returns evaluation_id on success.
    """
    _require_lab_paper()
    from app.lab.models_lab import LabStudy
    study = db.query(LabStudy).filter(LabStudy.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")
    if study.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=400, detail=f"Study status is {study.status}; cannot evaluate")

    try:
        from app.lab.evaluator import evaluate_study
        from app.lab.persist import persist_evaluation_result
        result = evaluate_study(study_id=study_id, db=db)
        if result.get("status") == "ERROR":
            raise HTTPException(status_code=500, detail=result.get("reason", "Evaluation error"))
        if result.get("status") == "SKIPPED":
            return {"status": "SKIPPED", "reason": result.get("reason")}
        evaluation_id = persist_evaluation_result(study_id=study_id, result=result, db=db)
        db.commit()
        return {
            "status": "OK",
            "evaluation_id": evaluation_id,
            "study_id": study_id,
            "data_through_date": result.get("data_through_date"),
            "closed_trades": len(result.get("closed_trades", [])),
            "open_positions": len(result.get("open_positions", [])),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[lab_paper] Evaluation failed for study {study_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Study paper detail ───────────────────────────────────────────────────────

@router.get("/study/{study_id}/paper")
def get_study_paper(study_id: str, db: Session = Depends(get_db)):
    """Return paper study details including daily equity, open holdings, closed trades, staleness."""
    from app.lab.models_lab import (
        LabStudy, LabStudyStrategy, LabPaperHolding, LabPaperTrade,
        LabPaperDaily, LabTomorrowOrder, LabEvaluation,
    )

    study = db.query(LabStudy).filter(LabStudy.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    strategies = db.query(LabStudyStrategy).filter(LabStudyStrategy.study_id == study_id).all()
    holdings = db.query(LabPaperHolding).filter(LabPaperHolding.study_id == study_id).all()
    daily = (
        db.query(LabPaperDaily)
        .filter(LabPaperDaily.study_id == study_id)
        .order_by(LabPaperDaily.session_date.asc())
        .all()
    )
    recent_trades = (
        db.query(LabPaperTrade)
        .filter(LabPaperTrade.study_id == study_id, LabPaperTrade.trade_key.isnot(None))
        .order_by(LabPaperTrade.exec_date.desc())
        .limit(50)
        .all()
    )
    tomorrow_orders = (
        db.query(LabTomorrowOrder)
        .filter(LabTomorrowOrder.study_id == study_id, LabTomorrowOrder.status == "PENDING")
        .all()
    )
    last_eval = (
        db.query(LabEvaluation)
        .filter(LabEvaluation.study_id == study_id, LabEvaluation.status == "DONE")
        .order_by(LabEvaluation.completed_at.desc())
        .first()
    )

    # Compute staleness
    from app.engine.research_loader import get_paper_data_staleness
    last_data_date = last_eval.data_through_date if last_eval else None
    stale_sessions = get_paper_data_staleness(last_data_date)

    return {
        "study": {
            "id": study.id,
            "name": study.name,
            "status": study.status,
            "start_date": str(study.start_date),
            "capital": study.capital,
            "risk_pct": study.risk_pct,
            "max_positions": study.max_positions,
            "kill_switch_triggered": study.kill_switch_triggered,
            "kill_switch_threshold_pct": study.kill_switch_threshold_pct,
            "is_test": getattr(study, "is_test", False),
        },
        "strategies": [
            {
                "strategy_id": ss.strategy_id,
                "holding_days": ss.holding_days,
                "config_hash": ss.config_hash,
            }
            for ss in strategies
        ],
        "holdings": [
            {
                "symbol": h.symbol,
                "strategy_id": h.strategy_id,
                "qty": h.qty,
                "entry_date": str(h.entry_date),
                "entry_price": h.entry_price,
                "stop_price": h.stop_price,
                "avg_cost": h.avg_cost,
                "unrealized_pnl": h.unrealized_pnl,
            }
            for h in holdings
        ],
        "daily": [
            {
                "strategy_id": r.strategy_id,
                "date": str(r.session_date),
                "total_equity": r.total_equity,
                "drawdown_pct": r.drawdown_pct,
                "cumulative_return_pct": r.cumulative_return_pct,
                "open_positions": r.open_positions,
                "trades_today": r.trades_today,
                "realized_pnl": r.realized_pnl,
                "unrealized_pnl": r.unrealized_pnl,
            }
            for r in daily
        ],
        "recent_trades": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "strategy_id": t.strategy_id,
                "side": t.side,
                "qty": t.qty,
                "exec_date": str(t.exec_date),
                "fill_price": t.fill_price,
                "net_pnl": t.net_pnl,
                "gross_pnl": t.gross_pnl,
                "r_multiple": t.r_multiple,
                "exit_reason": t.exit_reason,
                "reason_text": t.reason_text,
                "signal_date": str(t.signal_date) if t.signal_date else None,
                "stop_price": t.stop_price,
                "trade_key": t.trade_key,
                "holding_days_target": t.holding_days_target,
            }
            for t in recent_trades
        ],
        "tomorrow_orders": [
            {
                "symbol": o.symbol,
                "strategy_id": o.strategy_id,
                "planned_entry": o.planned_entry,
                "stop_price": o.stop_price,
                "research_qty": o.research_qty,
                "practical_qty": o.practical_qty,
                "signal_date": str(o.signal_date),
                "planned_exit_date": str(o.planned_exit_date) if o.planned_exit_date else None,
                "signal_reason": o.signal_reason,
                "holding_days_target": o.holding_days_target,
            }
            for o in tomorrow_orders
        ],
        "staleness": {
            "last_data_date": str(last_data_date) if last_data_date else None,
            "missed_sessions": stale_sessions,
            "is_stale": stale_sessions > 3 if stale_sessions >= 0 else True,
        },
        "last_evaluation_id": last_eval.id if last_eval else None,
        "disclaimer": (
            "⚠ Survivorship bias warning: results use the current universe, not the universe "
            "as it existed on the signal date. Past strategy performance does not guarantee future results."
        ),
    }


# ─── Evaluation audit log ─────────────────────────────────────────────────────

@router.get("/study/{study_id}/eval-status")
def get_eval_status(study_id: str, limit: int = 10, db: Session = Depends(get_db)):
    """Return the most recent evaluation audit records for a study."""
    from app.lab.models_lab import LabEvaluation
    evals = (
        db.query(LabEvaluation)
        .filter(LabEvaluation.study_id == study_id)
        .order_by(LabEvaluation.started_at.desc())
        .limit(min(limit, 50))
        .all()
    )
    return [
        {
            "id": e.id,
            "status": e.status,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "data_through_date": str(e.data_through_date) if e.data_through_date else None,
            "engine_version": e.engine_version,
            "trade_count": e.trade_count,
            "open_count": e.open_count,
            "equity_row_count": e.equity_row_count,
            "error_detail": e.error_detail,
        }
        for e in evals
    ]


# ─── Tomorrow orders ──────────────────────────────────────────────────────────

@router.get("/study/{study_id}/tomorrow")
def get_tomorrow_orders(study_id: str, db: Session = Depends(get_db)):
    """Return pending tomorrow orders for a study (the actionable watchlist)."""
    from app.lab.models_lab import LabStudy, LabTomorrowOrder
    study = db.query(LabStudy).filter(LabStudy.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    orders = (
        db.query(LabTomorrowOrder)
        .filter(LabTomorrowOrder.study_id == study_id, LabTomorrowOrder.status == "PENDING")
        .order_by(LabTomorrowOrder.signal_date.desc())
        .all()
    )
    return {
        "study_id": study_id,
        "study_name": study.name,
        "orders": [
            {
                "symbol": o.symbol,
                "strategy_id": o.strategy_id,
                "signal_date": str(o.signal_date),
                "planned_entry": o.planned_entry,
                "stop_price": o.stop_price,
                "research_qty": o.research_qty,
                "practical_qty": o.practical_qty,
                "planned_exit_date": str(o.planned_exit_date) if o.planned_exit_date else None,
                "holding_days_target": o.holding_days_target,
                "signal_reason": o.signal_reason,
            }
            for o in orders
        ],
        "disclaimer": (
            "These are simulated paper orders based on algorithmic signals. "
            "No broker orders are placed. Manual execution only. Not investment advice."
        ),
    }


# ─── Nightly batch evaluation ─────────────────────────────────────────────────

@router.post("/jobs/nightly")
def run_nightly_evaluation(db: Session = Depends(get_db)):
    """Nightly batch: evaluate all ACTIVE studies.

    Requires LAB_PAPER_ENABLED=true. Called by GitHub Actions cron at ~15:47 IST.
    """
    _require_lab_paper()
    from app.lab.models_lab import LabStudy
    from app.lab.evaluator import evaluate_study
    from app.lab.persist import persist_evaluation_result

    studies = db.query(LabStudy).filter(LabStudy.status == "ACTIVE").all()
    results = []
    for study in studies:
        try:
            result = evaluate_study(study_id=study.id, db=db)
            if result.get("status") == "OK":
                eval_id = persist_evaluation_result(study_id=study.id, result=result, db=db)
                db.commit()
                results.append({
                    "study_id": study.id,
                    "study_name": study.name,
                    "status": "OK",
                    "evaluation_id": eval_id,
                    "data_through_date": result.get("data_through_date"),
                })
            else:
                results.append({
                    "study_id": study.id,
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                })
        except Exception as e:
            logger.exception(f"[nightly] Study {study.id} failed: {e}")
            results.append({"study_id": study.id, "status": "ERROR", "error": str(e)})

    return {"evaluated": len(studies), "results": results}


# ─── Chart data for trade cards ───────────────────────────────────────────────

def _build_chart_response(
    symbol: str,
    bars_before: int,
    bars_after: int,
    entry_date: Optional[datetime.date],
    exit_date: Optional[datetime.date],
    signal_date: Optional[datetime.date],
    stop_price: Optional[float],
    entry_price: Optional[float],
    planned_exit_date: Optional[datetime.date],
    exit_reason: Optional[str],
    reason_text: Optional[str],
    signal_context: Optional[Dict],
    db: Session,
) -> Dict[str, Any]:
    """Fetch bars from DB and build chart response with trade markers."""
    from app.models import DailyBar
    from app.engine.indicators import add_all_indicators
    import pandas as pd

    # Determine the window
    anchor = entry_date or signal_date
    if anchor is None:
        raise HTTPException(status_code=400, detail="No entry or signal date available for chart")

    # Fetch bars for the symbol
    rows = (
        db.query(DailyBar)
        .filter(DailyBar.symbol == symbol)
        .order_by(DailyBar.date.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No bars found for {symbol}")

    df = pd.DataFrame([{
        "date": r.date,
        "open": float(r.split_adj_open or r.open or 0),
        "high": float(r.split_adj_high or r.high or 0),
        "low": float(r.split_adj_low or r.low or 0),
        "close": float(r.split_adj_close or r.close or 0),
        "volume": float(r.volume or 0),
    } for r in rows])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)

    if "atr14" not in df.columns:
        try:
            df = add_all_indicators(df)
        except Exception:
            pass

    # Find anchor index
    dates = df["date"].tolist()
    try:
        anchor_idx = next(i for i, d in enumerate(dates) if d >= anchor)
    except StopIteration:
        anchor_idx = len(dates) - 1

    start_idx = max(0, anchor_idx - bars_before)
    end_idx_base = anchor_idx + bars_after + 1
    if exit_date:
        try:
            exit_idx = next(i for i, d in enumerate(dates) if d >= exit_date)
            end_idx_base = max(end_idx_base, exit_idx + bars_after + 1)
        except StopIteration:
            pass
    end_idx = min(len(df), end_idx_base)

    window = df.iloc[start_idx:end_idx].copy()

    bars = []
    for _, row in window.iterrows():
        bar: Dict[str, Any] = {
            "time": row["date"].isoformat(),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        }
        for col in ["ema20", "ema50", "sma50", "sma200", "rsi14", "atr14"]:
            if col in row and row[col] is not None:
                import math
                val = float(row[col])
                if not math.isnan(val):
                    bar[col] = round(val, 4)
        bars.append(bar)

    # Build trade markers
    markers = []
    if signal_date:
        markers.append({
            "date": signal_date.isoformat(),
            "price": entry_price or 0,
            "type": "SIGNAL",
            "label": "Signal",
            "color": "#a78bfa",
        })
    if entry_date and entry_price:
        markers.append({
            "date": entry_date.isoformat(),
            "price": entry_price,
            "type": "BUY",
            "label": f"Buy @ ₹{entry_price:.2f}",
            "color": "#34d399",
        })
    if planned_exit_date:
        markers.append({
            "date": planned_exit_date.isoformat(),
            "price": entry_price or 0,
            "type": "PLANNED_EXIT",
            "label": "Planned exit",
            "color": "#fbbf24",
        })
    if exit_date and exit_reason:
        exit_color = "#ef4444" if "STOP" in (exit_reason or "") else "#60a5fa"
        exit_label_map = {
            "STOP_HIT": "Stop hit",
            "GAP_THROUGH_STOP": "Gap-through stop",
            "TIME_EXIT": "Time exit",
        }
        markers.append({
            "date": exit_date.isoformat(),
            "price": 0,
            "type": "SELL",
            "label": exit_label_map.get(exit_reason, exit_reason),
            "color": exit_color,
        })

    # Build stop segment (entry → exit, bounded)
    segments = []
    if stop_price and entry_date:
        seg_end = exit_date or planned_exit_date or (datetime.date.today() if dates else entry_date)
        segments.append({
            "startDate": entry_date.isoformat(),
            "endDate": seg_end.isoformat(),
            "price": stop_price,
            "type": "STOP",
            "color": "#ef4444",
            "style": "dashed",
        })

    return {
        "symbol": symbol,
        "bars": bars,
        "markers": markers,
        "segments": segments,
        "trade_info": {
            "symbol": symbol,
            "signal_date": signal_date.isoformat() if signal_date else None,
            "entry_date": entry_date.isoformat() if entry_date else None,
            "entry_price": entry_price,
            "exit_date": exit_date.isoformat() if exit_date else None,
            "stop_price": stop_price,
            "exit_reason": exit_reason,
            "planned_exit_date": planned_exit_date.isoformat() if planned_exit_date else None,
            "reason_text": reason_text,
            "signal_context": signal_context,
        },
    }


@router.get("/trade/paper/{trade_id}/chart")
def get_paper_trade_chart(
    trade_id: int,
    before: int = 60,
    after: int = 10,
    db: Session = Depends(get_db),
):
    """Return candle bars + trade markers for a paper trade card."""
    from app.lab.models_lab import LabPaperTrade
    trade = db.query(LabPaperTrade).filter(LabPaperTrade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Paper trade {trade_id} not found")

    ctx = None
    if trade.signal_context_json:
        try:
            ctx = json.loads(trade.signal_context_json)
        except Exception:
            pass

    return _build_chart_response(
        symbol=trade.symbol,
        bars_before=min(before, 200),
        bars_after=min(after, 60),
        entry_date=trade.exec_date if trade.side == "BUY" else None,
        exit_date=trade.exec_date if trade.side == "SELL" else None,
        signal_date=trade.signal_date,
        stop_price=trade.stop_price,
        entry_price=trade.fill_price if trade.side == "BUY" else None,
        planned_exit_date=trade.planned_exit_date,
        exit_reason=trade.exit_reason,
        reason_text=trade.reason_text,
        signal_context=ctx,
        db=db,
    )


@router.get("/trade/backtest/{trade_id}/chart")
def get_backtest_trade_chart(
    trade_id: int,
    before: int = 60,
    after: int = 10,
    db: Session = Depends(get_db),
):
    """Return candle bars + trade markers for a backtest trade card."""
    from app.lab.models_lab import LabTrade
    trade = db.query(LabTrade).filter(LabTrade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Backtest trade {trade_id} not found")

    ctx = None
    if getattr(trade, "signal_context_json", None):
        try:
            ctx = json.loads(trade.signal_context_json)
        except Exception:
            pass

    return _build_chart_response(
        symbol=trade.symbol,
        bars_before=min(before, 200),
        bars_after=min(after, 60),
        entry_date=trade.entry_date,
        exit_date=trade.exit_date,
        signal_date=getattr(trade, "signal_date", None) or trade.entry_date,
        stop_price=trade.stop_price,
        entry_price=trade.entry_price,
        planned_exit_date=getattr(trade, "planned_exit_date", None),
        exit_reason=trade.exit_reason,
        reason_text=getattr(trade, "reason_text", None),
        signal_context=ctx,
        db=db,
    )


# ─── All paper trades (paginated) ─────────────────────────────────────────────

@router.get("/trades/paper")
def list_paper_trades(
    study_id: Optional[str] = None,
    strategy_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """List paper trades with optional filters. Used by TradeCardList."""
    from app.lab.models_lab import LabPaperTrade

    q = db.query(LabPaperTrade).filter(LabPaperTrade.trade_key.isnot(None))
    if study_id:
        q = q.filter(LabPaperTrade.study_id == study_id)
    if strategy_id:
        q = q.filter(LabPaperTrade.strategy_id == strategy_id)

    total = q.count()
    trades = (
        q.order_by(LabPaperTrade.exec_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Determine open vs closed by checking if there's a matching closing SELL
    # For now, we categorize by side
    items = []
    for t in trades:
        items.append({
            "id": t.id,
            "source": "paper",
            "study_id": t.study_id,
            "strategy_id": t.strategy_id,
            "symbol": t.symbol,
            "side": t.side,
            "qty": t.qty,
            "exec_date": str(t.exec_date),
            "fill_price": t.fill_price,
            "net_pnl": t.net_pnl,
            "gross_pnl": t.gross_pnl,
            "r_multiple": t.r_multiple,
            "exit_reason": t.exit_reason,
            "reason_text": t.reason_text,
            "signal_date": str(t.signal_date) if t.signal_date else None,
            "stop_price": t.stop_price,
            "planned_exit_date": str(t.planned_exit_date) if t.planned_exit_date else None,
            "holding_days_target": t.holding_days_target,
            "trade_key": t.trade_key,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}
