"""Strategy Lab — API Routes.

Endpoints:
  GET  /api/lab/strategies              — registry list
  POST /api/lab/strategies/sync         — sync YAML → DB
  POST /api/lab/run                     — submit backtest job
  GET  /api/lab/runs                    — list runs
  GET  /api/lab/runs/{run_id}           — run status
  GET  /api/lab/results                 — query results (filterable)
  GET  /api/lab/results/{strategy_id}   — results for one strategy
  POST /api/lab/study                   — create paper study
  GET  /api/lab/study                   — list / active study
  GET  /api/lab/study/{study_id}        — study detail
  GET  /api/lab/study/{study_id}/paper  — paper trades + daily
  POST /api/lab/plan                    — save plan items for today
  GET  /api/lab/plan                    — today's plan
  GET  /api/lab/plan/history            — plan history
  POST /api/lab/plan/{item_id}/execute  — mark plan item executed
  GET  /api/lab/rank                    — ranked results for auto-select
"""

import datetime
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lab", tags=["Strategy Lab"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    strategy_id: str = Field(..., description="S01..S10")
    holding_days: int = Field(..., ge=1, le=60)
    capital: float = Field(default=500_000.0, ge=1000)
    risk_pct: float = Field(default=0.5, ge=0.1, le=5.0)
    max_positions: int = Field(default=5, ge=1, le=20)


class RunAllRequest(BaseModel):
    strategy_ids: Optional[List[str]] = None   # None = all enabled
    holding_days: List[int] = Field(default=[4, 7, 10, 15])
    capital: float = Field(default=500_000.0)
    risk_pct: float = Field(default=0.5)
    max_positions: int = Field(default=5)


class StudyCreateRequest(BaseModel):
    name: str
    strategies: List[Dict[str, Any]]           # [{strategy_id, holding_days}]
    capital: float = Field(default=500_000.0)
    risk_pct: float = Field(default=0.5)
    max_positions: int = Field(default=5)
    kill_switch_threshold_pct: float = Field(default=10.0)
    planned_end_date: Optional[str] = None
    notes: Optional[str] = None


class PlanItemCreate(BaseModel):
    plan_date: Optional[str] = None            # defaults to today
    strategy_id: str
    symbol: str
    action: str                                # BUY|SELL|WATCH
    suggested_entry: Optional[float] = None
    suggested_stop: Optional[float] = None
    suggested_qty: Optional[int] = None
    rationale: Optional[str] = None


class PlanItemExecute(BaseModel):
    executed_price: float
    executed_qty: int
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Strategies / Registry
# ---------------------------------------------------------------------------

@router.get("/strategies")
def list_strategies(db: Session = Depends(get_db)):
    """List all registered strategies from DB (synced from YAML)."""
    from app.lab.models_lab import LabStrategy
    strategies = db.query(LabStrategy).order_by(LabStrategy.id).all()
    if not strategies:
        # Auto-sync on first access
        try:
            from app.lab.registry import sync_registry_to_db
            sync_registry_to_db(db)
            strategies = db.query(LabStrategy).order_by(LabStrategy.id).all()
        except Exception as e:
            logger.warning(f"Registry auto-sync failed: {e}")
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "enabled": s.enabled,
            "parameters": json.loads(s.parameters_json) if s.parameters_json else {},
            "config_hash": s.config_hash,
            "min_history_bars": s.min_history_bars,
        }
        for s in strategies
    ]


@router.post("/strategies/sync")
def sync_strategies(db: Session = Depends(get_db)):
    """Sync swing_registry.yaml → lab_strategies DB table."""
    from app.lab.registry import sync_registry_to_db
    try:
        result = sync_registry_to_db(db)
        return {"status": "ok", **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"Registry sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Backtest Runs
# ---------------------------------------------------------------------------

@router.post("/run")
def submit_run(req: RunRequest, db: Session = Depends(get_db)):
    """Submit a single backtest job."""
    from app.lab.models_lab import LabStrategy
    from app.lab.runner import submit_backtest_job

    strat = db.query(LabStrategy).filter(LabStrategy.id == req.strategy_id).first()
    if not strat:
        # Try auto-sync
        try:
            from app.lab.registry import sync_registry_to_db
            sync_registry_to_db(db)
            strat = db.query(LabStrategy).filter(LabStrategy.id == req.strategy_id).first()
        except Exception:
            pass
    if not strat:
        raise HTTPException(status_code=404, detail=f"Strategy {req.strategy_id} not found. Run /strategies/sync first.")
    if not strat.enabled:
        raise HTTPException(status_code=400, detail=f"Strategy {req.strategy_id} is disabled.")

    params = json.loads(strat.parameters_json) if strat.parameters_json else {}
    run_id = submit_backtest_job(
        db=db,
        strategy_id=req.strategy_id,
        holding_days=req.holding_days,
        params=params,
        capital=req.capital,
        risk_pct=req.risk_pct,
        max_positions=req.max_positions,
    )
    return {"run_id": run_id, "status": "PENDING", "strategy_id": req.strategy_id, "holding_days": req.holding_days}


@router.post("/run-all")
def submit_run_all(req: RunAllRequest, db: Session = Depends(get_db)):
    """Submit backtest jobs for all (or selected) strategies × holding days."""
    from app.lab.models_lab import LabStrategy
    from app.lab.runner import submit_backtest_job

    strategies = db.query(LabStrategy).filter(LabStrategy.enabled == True).order_by(LabStrategy.id).all()
    if not strategies:
        try:
            from app.lab.registry import sync_registry_to_db
            sync_registry_to_db(db)
            strategies = db.query(LabStrategy).filter(LabStrategy.enabled == True).order_by(LabStrategy.id).all()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Registry sync failed: {e}")

    if req.strategy_ids:
        strategies = [s for s in strategies if s.id in req.strategy_ids]

    if not strategies:
        raise HTTPException(status_code=404, detail="No enabled strategies found.")

    submitted = []
    for strat in strategies:
        params = json.loads(strat.parameters_json) if strat.parameters_json else {}
        for hd in req.holding_days:
            run_id = submit_backtest_job(
                db=db,
                strategy_id=strat.id,
                holding_days=hd,
                params=params,
                capital=req.capital,
                risk_pct=req.risk_pct,
                max_positions=req.max_positions,
            )
            submitted.append({"run_id": run_id, "strategy_id": strat.id, "holding_days": hd})

    return {"submitted": submitted, "count": len(submitted)}


@router.get("/runs")
def list_runs(
    strategy_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """List backtest runs."""
    from app.lab.models_lab import LabRun
    q = db.query(LabRun)
    if strategy_id:
        q = q.filter(LabRun.strategy_id == strategy_id)
    if status:
        q = q.filter(LabRun.status == status)
    runs = q.order_by(LabRun.submitted_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "strategy_id": r.strategy_id,
            "holding_days": r.holding_days,
            "status": r.status,
            "progress_pct": r.progress_pct,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "error_message": r.error_message,
            "universe_symbols": r.universe_symbols,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    """Get status of a specific backtest run."""
    from app.lab.models_lab import LabRun
    run = db.query(LabRun).filter(LabRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "strategy_id": run.strategy_id,
        "holding_days": run.holding_days,
        "status": run.status,
        "progress_pct": run.progress_pct,
        "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error_message": run.error_message,
        "universe_symbols": run.universe_symbols,
        "capital": run.capital,
        "risk_pct": run.risk_pct,
        "max_positions": run.max_positions,
    }


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@router.get("/results")
def list_results(
    strategy_id: Optional[str] = None,
    holding_days: Optional[int] = None,
    sample_ok_only: bool = False,
    db: Session = Depends(get_db),
):
    """List backtest results."""
    from app.lab.models_lab import LabResult
    q = db.query(LabResult)
    if strategy_id:
        q = q.filter(LabResult.strategy_id == strategy_id)
    if holding_days:
        q = q.filter(LabResult.holding_days == holding_days)
    if sample_ok_only:
        q = q.filter(LabResult.sample_ok == True)
    results = q.order_by(LabResult.strategy_id, LabResult.holding_days).all()
    return [_result_to_dict(r) for r in results]


@router.get("/results/{strategy_id}")
def get_strategy_results(strategy_id: str, db: Session = Depends(get_db)):
    """Get all results for a specific strategy."""
    from app.lab.models_lab import LabResult
    results = db.query(LabResult).filter(LabResult.strategy_id == strategy_id).order_by(LabResult.holding_days).all()
    return [_result_to_dict(r) for r in results]


def _result_to_dict(r) -> Dict:
    return {
        "id": r.id,
        "run_id": r.run_id,
        "strategy_id": r.strategy_id,
        "holding_days": r.holding_days,
        "total_trades": r.total_trades,
        "win_rate": r.win_rate,
        "expectancy_r": r.expectancy_r,
        "median_net_expectancy": r.median_net_expectancy,
        "avg_win_r": r.avg_win_r,
        "avg_loss_r": r.avg_loss_r,
        "profit_factor": r.profit_factor,
        "cagr_pct": r.cagr_pct,
        "max_drawdown_pct": r.max_drawdown_pct,
        "sharpe_ratio": r.sharpe_ratio,
        "total_pnl": r.total_pnl,
        "total_costs": r.total_costs,
        "sample_ok": r.sample_ok,
        "sample_label": r.sample_label,
        "half1_expectancy": r.half1_expectancy,
        "half2_expectancy": r.half2_expectancy,
        "half_consistency": r.half_consistency,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

@router.get("/rank")
def get_ranked_results(db: Session = Depends(get_db)):
    """Return results ranked by median net expectancy with auto-selection flags."""
    from app.lab.models_lab import LabResult
    from app.lab.ranking import rank_strategies

    results = db.query(LabResult).order_by(LabResult.strategy_id, LabResult.holding_days).all()
    result_dicts = [_result_to_dict(r) for r in results]
    ranked = rank_strategies(result_dicts)
    return {
        "ranked": ranked,
        "disclaimer": (
            "Backtest on current Nifty stocks may contain survivorship bias. "
            "Rankings screen ideas; forward paper results provide prospective evidence."
        ),
    }


# ---------------------------------------------------------------------------
# Forward Paper Studies
# ---------------------------------------------------------------------------

@router.post("/study")
def create_study(req: StudyCreateRequest, db: Session = Depends(get_db)):
    """Create a frozen forward paper trading study."""
    from app.lab.models_lab import LabStudy, LabStudyStrategy
    from app.lab.models_lab import LabStrategy
    import json

    # Validate strategies
    for entry in req.strategies:
        sid = entry.get("strategy_id")
        strat = db.query(LabStrategy).filter(LabStrategy.id == sid).first()
        if not strat:
            raise HTTPException(status_code=404, detail=f"Strategy {sid} not found.")

    study_id = str(uuid.uuid4())
    start_date = datetime.date.today()
    planned_end = None
    if req.planned_end_date:
        try:
            planned_end = datetime.date.fromisoformat(req.planned_end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="planned_end_date must be YYYY-MM-DD")

    study = LabStudy(
        id=study_id,
        name=req.name,
        status="ACTIVE",
        start_date=start_date,
        planned_end_date=planned_end,
        capital=req.capital,
        risk_pct=req.risk_pct,
        max_positions=req.max_positions,
        strategies_json=json.dumps(req.strategies),
        kill_switch_threshold_pct=req.kill_switch_threshold_pct,
        notes=req.notes,
    )
    db.add(study)

    for entry in req.strategies:
        sid = entry["strategy_id"]
        hd = int(entry.get("holding_days", 7))
        strat = db.query(LabStrategy).filter(LabStrategy.id == sid).first()
        params = json.loads(strat.parameters_json) if strat.parameters_json else {}
        from app.lab.engine import compute_config_hash
        ch = compute_config_hash(sid, params, hd)
        ss = LabStudyStrategy(
            study_id=study_id,
            strategy_id=sid,
            holding_days=hd,
            config_hash=ch,
            parameters_json=json.dumps(params),
        )
        db.add(ss)

    db.commit()
    return {"study_id": study_id, "status": "ACTIVE", "start_date": str(start_date)}


@router.get("/study")
def list_studies(db: Session = Depends(get_db)):
    """List all forward paper studies."""
    from app.lab.models_lab import LabStudy
    studies = db.query(LabStudy).order_by(LabStudy.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "status": s.status,
            "start_date": str(s.start_date),
            "planned_end_date": str(s.planned_end_date) if s.planned_end_date else None,
            "capital": s.capital,
            "kill_switch_triggered": s.kill_switch_triggered,
            "strategies": json.loads(s.strategies_json) if s.strategies_json else [],
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in studies
    ]


@router.get("/study/{study_id}")
def get_study(study_id: str, db: Session = Depends(get_db)):
    """Get a specific study with daily equity and open holdings."""
    from app.lab.models_lab import LabStudy, LabPaperHolding, LabPaperDaily, LabPaperTrade
    from app.lab.ranking import build_promotion_checklist

    study = db.query(LabStudy).filter(LabStudy.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    daily = (
        db.query(LabPaperDaily)
        .filter(LabPaperDaily.study_id == study_id)
        .order_by(LabPaperDaily.strategy_id, LabPaperDaily.session_date)
        .all()
    )
    holdings = (
        db.query(LabPaperHolding)
        .filter(LabPaperHolding.study_id == study_id)
        .all()
    )
    trades = (
        db.query(LabPaperTrade)
        .filter(LabPaperTrade.study_id == study_id)
        .order_by(LabPaperTrade.exec_date.desc())
        .all()
    )

    # Build promotion checklists per strategy
    strategies_in_study = json.loads(study.strategies_json) if study.strategies_json else []
    checklists = {}
    for entry in strategies_in_study:
        sid = entry.get("strategy_id")
        strat_trades = [
            {
                "r_multiple": t.r_multiple,
                "net_pnl": t.realized_pnl,
                "costs": json.loads(t.costs_json).get("total_cost", 0) if t.costs_json else 0,
            }
            for t in trades if t.strategy_id == sid and t.side == "SELL"
        ]
        checklists[sid] = build_promotion_checklist({}, strat_trades)

    return {
        "id": study.id,
        "name": study.name,
        "status": study.status,
        "start_date": str(study.start_date),
        "capital": study.capital,
        "kill_switch_threshold_pct": study.kill_switch_threshold_pct,
        "kill_switch_triggered": study.kill_switch_triggered,
        "strategies": strategies_in_study,
        "daily": [
            {
                "strategy_id": d.strategy_id,
                "date": str(d.session_date),
                "total_equity": d.total_equity,
                "cash": d.cash,
                "invested_value": d.invested_value,
                "drawdown_pct": d.drawdown_pct,
                "cumulative_return_pct": d.cumulative_return_pct,
                "open_positions": d.open_positions,
                "trades_today": d.trades_today,
                "cumulative_costs": d.cumulative_costs,
                "benchmark_close": d.benchmark_close,
                "benchmark_return_pct": d.benchmark_return_pct,
            }
            for d in daily
        ],
        "holdings": [
            {
                "strategy_id": h.strategy_id,
                "symbol": h.symbol,
                "qty": h.qty,
                "entry_date": str(h.entry_date),
                "entry_price": h.entry_price,
                "stop_price": h.stop_price,
                "unrealized_pnl": h.unrealized_pnl,
            }
            for h in holdings
        ],
        "recent_trades": [
            {
                "strategy_id": t.strategy_id,
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "exec_date": str(t.exec_date),
                "fill_price": t.fill_price,
                "realized_pnl": t.realized_pnl,
                "r_multiple": t.r_multiple,
                "exit_reason": t.exit_reason,
            }
            for t in trades[:50]
        ],
        "promotion_checklists": checklists,
        "disclaimer": (
            "⚠ Backtest on current Nifty stocks may contain survivorship bias. "
            "Rankings screen ideas; forward paper results provide prospective evidence."
        ),
    }


# ---------------------------------------------------------------------------
# Manual Plan
# ---------------------------------------------------------------------------

@router.post("/plan")
def create_plan_items(items: List[PlanItemCreate], db: Session = Depends(get_db)):
    """Save plan items for today (or a specified date)."""
    from app.lab.models_lab import LabPlanItem

    today = datetime.date.today()
    created = []
    for item in items:
        plan_date = today
        if item.plan_date:
            try:
                plan_date = datetime.date.fromisoformat(item.plan_date)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid plan_date: {item.plan_date}")

        rec = LabPlanItem(
            plan_date=plan_date,
            strategy_id=item.strategy_id,
            symbol=item.symbol,
            action=item.action.upper(),
            suggested_entry=item.suggested_entry,
            suggested_stop=item.suggested_stop,
            suggested_qty=item.suggested_qty,
            rationale=item.rationale,
            status="PENDING",
        )
        db.add(rec)
        created.append(item.symbol)
    db.commit()
    return {"created": len(created), "symbols": created}


@router.get("/plan")
def get_plan(
    plan_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get today's (or specified date's) trading plan."""
    from app.lab.models_lab import LabPlanItem

    target_date = datetime.date.today()
    if plan_date:
        try:
            target_date = datetime.date.fromisoformat(plan_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    items = db.query(LabPlanItem).filter(LabPlanItem.plan_date == target_date).order_by(LabPlanItem.id).all()
    return {
        "plan_date": str(target_date),
        "items": [_plan_item_to_dict(i) for i in items],
        "disclaimer": "Manual execution only. No broker orders.",
    }


@router.get("/plan/history")
def get_plan_history(
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db),
):
    """Get plan history for the last N days."""
    from app.lab.models_lab import LabPlanItem
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    items = (
        db.query(LabPlanItem)
        .filter(LabPlanItem.plan_date >= cutoff)
        .order_by(LabPlanItem.plan_date.desc(), LabPlanItem.id)
        .all()
    )
    return [_plan_item_to_dict(i) for i in items]


@router.post("/plan/{item_id}/execute")
def execute_plan_item(item_id: int, payload: PlanItemExecute, db: Session = Depends(get_db)):
    """Mark a plan item as executed with actual fill details."""
    from app.lab.models_lab import LabPlanItem

    item = db.query(LabPlanItem).filter(LabPlanItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Plan item not found")

    item.status = "EXECUTED"
    item.executed_price = payload.executed_price
    item.executed_qty = payload.executed_qty
    item.notes = payload.notes
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return _plan_item_to_dict(item)


@router.post("/plan/{item_id}/skip")
def skip_plan_item(item_id: int, db: Session = Depends(get_db)):
    """Mark a plan item as skipped."""
    from app.lab.models_lab import LabPlanItem

    item = db.query(LabPlanItem).filter(LabPlanItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Plan item not found")
    item.status = "SKIPPED"
    item.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return _plan_item_to_dict(item)


def _plan_item_to_dict(i) -> Dict:
    return {
        "id": i.id,
        "plan_date": str(i.plan_date),
        "strategy_id": i.strategy_id,
        "symbol": i.symbol,
        "action": i.action,
        "suggested_entry": i.suggested_entry,
        "suggested_stop": i.suggested_stop,
        "suggested_qty": i.suggested_qty,
        "rationale": i.rationale,
        "status": i.status,
        "executed_price": i.executed_price,
        "executed_qty": i.executed_qty,
        "notes": i.notes,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }
