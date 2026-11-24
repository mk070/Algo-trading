"""Strategy Lab — Robust Serial Backtest Runner.

Features:
1. Serial execution: at most ONE backtest runs at a time to prevent CPU/memory exhaustion.
2. In-memory FIFO queue with DB persistence: jobs are created PENDING in DB,
   then processed sequentially.
3. Interrupted job recovery: at startup, any orphaned PENDING/RUNNING jobs from previous
   process runs are marked as INTERRUPTED.
"""

import datetime
import json
import logging
import queue
import threading
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Queue holding job specifications for sequential processing
_job_queue: queue.Queue = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()
_current_running_job_id: Optional[str] = None


def get_current_running_job_id() -> Optional[str]:
    return _current_running_job_id


def recover_interrupted_jobs():
    """Mark any orphaned PENDING or RUNNING jobs from prior server run as INTERRUPTED."""
    from app.db import transaction_context
    from app.lab.models_lab import LabRun
    try:
        with transaction_context() as db:
            orphaned = db.query(LabRun).filter(LabRun.status.in_(["RUNNING", "PENDING"])).all()
            for r in orphaned:
                r.status = "INTERRUPTED"
                r.error_message = "Interrupted by application restart."
                r.completed_at = datetime.datetime.now(datetime.timezone.utc)
            if orphaned:
                logger.info(f"[Lab] Marked {len(orphaned)} orphaned backtest jobs as INTERRUPTED.")
    except Exception as e:
        logger.warning(f"[Lab] recover_interrupted_jobs failed: {e}")


def _worker_loop():
    """Worker daemon thread that continuously processes jobs from the queue."""
    global _current_running_job_id
    logger.info("[Lab] Backtest worker queue thread started.")
    while True:
        try:
            job_spec = _job_queue.get()
            if job_spec is None:
                break
            run_id = job_spec["run_id"]
            _current_running_job_id = run_id
            try:
                _execute_job(
                    run_id=run_id,
                    strategy_id=job_spec["strategy_id"],
                    holding_days=job_spec["holding_days"],
                    params=job_spec["params"],
                    capital=job_spec["capital"],
                    risk_pct=job_spec["risk_pct"],
                    max_positions=job_spec["max_positions"],
                    config_hash=job_spec["config_hash"],
                )
            except Exception as e:
                logger.exception(f"[Lab] Unhandled error executing job {run_id}: {e}")
            finally:
                _current_running_job_id = None
                _job_queue.task_done()
        except Exception as e:
            logger.exception(f"[Lab] Queue worker error: {e}")


def _ensure_worker_started():
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="lab_backtest_worker")
            _worker_thread.start()


def _execute_job(run_id: str, strategy_id: str, holding_days: int, params: Dict,
                 capital: float, risk_pct: float, max_positions: int, config_hash: str):
    """Execute backtest in worker thread and persist results."""
    from app.db import transaction_context
    from app.lab.models_lab import LabRun, LabResult, LabTrade
    from app.lab.engine import run_single_strategy_backtest
    from app.engine.research_loader import load_research_bars

    logger.info(f"[Lab] Starting run {run_id}: {strategy_id} H={holding_days}")

    # Mark as RUNNING
    with transaction_context() as db:
        run = db.query(LabRun).filter(LabRun.id == run_id).first()
        if run:
            run.status = "RUNNING"
            run.started_at = datetime.datetime.now(datetime.timezone.utc)

    try:
        # Load bars from parquet snapshot (never per-symbol Neon queries)
        bars_dict = load_research_bars(symbols=[], start_date=None, end_date=None)
        if not bars_dict:
            raise RuntimeError("No historical bars found. Check parquet snapshot.")

        # Update progress
        with transaction_context() as db:
            run = db.query(LabRun).filter(LabRun.id == run_id).first()
            if run:
                run.progress_pct = 15
                run.universe_symbols = len(bars_dict)

        trades, summary = run_single_strategy_backtest(
            strategy_id=strategy_id,
            params=params,
            holding_days=holding_days,
            bars_dict=bars_dict,
            capital=capital,
            risk_pct=risk_pct,
            max_positions=max_positions,
        )

        # Persist results with explicit primitive type casting
        def _to_float(v):
            return float(v) if v is not None else None

        def _to_int(v):
            return int(v) if v is not None else None

        def _to_bool(v):
            return bool(v) if v is not None else False

        def _clean_summary_for_json(d):
            clean = {}
            for k, v in d.items():
                if v is None:
                    clean[k] = None
                elif isinstance(v, (np.floating, float)):
                    clean[k] = float(v)
                elif isinstance(v, (np.integer, int)):
                    clean[k] = int(v)
                elif isinstance(v, (np.bool_, bool)):
                    clean[k] = bool(v)
                else:
                    clean[k] = str(v)
            return clean

        with transaction_context() as db:
            result = LabResult(
                run_id=run_id,
                strategy_id=strategy_id,
                holding_days=_to_int(holding_days),
                config_hash=config_hash,
                total_trades=_to_int(summary["total_trades"]),
                win_rate=_to_float(summary.get("win_rate")),
                expectancy_r=_to_float(summary.get("expectancy_r")),
                median_net_expectancy=_to_float(summary.get("median_net_expectancy")),
                avg_win_r=_to_float(summary.get("avg_win_r")),
                avg_loss_r=_to_float(summary.get("avg_loss_r")),
                profit_factor=_to_float(summary.get("profit_factor")),
                cagr_pct=_to_float(summary.get("cagr_pct")),
                max_drawdown_pct=_to_float(summary.get("max_drawdown_pct")),
                sharpe_ratio=_to_float(summary.get("sharpe_ratio")),
                total_pnl=_to_float(summary.get("total_pnl")),
                total_costs=_to_float(summary.get("total_costs")),
                sample_ok=_to_bool(summary.get("sample_ok", False)),
                sample_label=str(summary.get("sample_label")) if summary.get("sample_label") is not None else None,
                half1_expectancy=_to_float(summary.get("half1_expectancy")),
                half2_expectancy=_to_float(summary.get("half2_expectancy")),
                half_consistency=_to_float(summary.get("half_consistency")),
                metrics_json=json.dumps(_clean_summary_for_json(summary)),
            )
            db.add(result)

            # Persist individual trades (batch insert)
            for t in trades:
                entry_date = t.entry_date
                exit_date = t.exit_date
                if hasattr(entry_date, "date"):
                    entry_date = entry_date.date() if callable(entry_date.date) else entry_date
                if hasattr(exit_date, "date") and exit_date is not None:
                    exit_date = exit_date.date() if callable(exit_date.date) else exit_date

                # Enrich with signal_date, planned_exit_date, reason_text
                from app.lab.evaluator import build_reason_text
                reason = build_reason_text(strategy_id, params)

                trade_rec = LabTrade(
                    run_id=run_id,
                    strategy_id=strategy_id,
                    holding_days=_to_int(holding_days),
                    symbol=str(t.symbol),
                    entry_date=entry_date,
                    exit_date=exit_date,
                    entry_price=_to_float(t.entry_price),
                    exit_price=_to_float(t.exit_price),
                    stop_price=_to_float(t.stop_price),
                    qty=_to_int(t.qty) or 0,
                    gross_pnl=_to_float(t.gross_pnl),
                    costs=_to_float(t.costs),
                    net_pnl=_to_float(t.net_pnl),
                    r_multiple=_to_float(t.r_multiple),
                    exit_reason=str(t.exit_reason) if t.exit_reason is not None else None,
                    holding_days_actual=_to_int(t.holding_days_actual),
                    signal_date=entry_date,
                    planned_exit_date=exit_date,
                    reason_text=reason,
                )
                db.add(trade_rec)

            # Mark run complete
            run = db.query(LabRun).filter(LabRun.id == run_id).first()
            if run:
                run.status = "DONE"
                run.progress_pct = 100
                run.completed_at = datetime.datetime.now(datetime.timezone.utc)

        logger.info(f"[Lab] Run {run_id} complete: {summary['total_trades']} trades")

    except Exception as e:
        logger.exception(f"[Lab] Run {run_id} failed: {e}")
        with transaction_context() as db:
            run = db.query(LabRun).filter(LabRun.id == run_id).first()
            if run:
                run.status = "FAILED"
                run.error_message = str(e)[:2000]
                run.completed_at = datetime.datetime.now(datetime.timezone.utc)


def submit_backtest_job(
    db,
    strategy_id: str,
    holding_days: int,
    params: Dict[str, Any],
    capital: float = 500_000.0,
    risk_pct: float = 0.5,
    max_positions: int = 5,
) -> str:
    """
    Create a LabRun DB record and push the job onto the serialized worker queue.
    Returns the run_id (UUID).
    """
    from app.lab.models_lab import LabRun
    from app.lab.engine import compute_config_hash

    config_hash = compute_config_hash(strategy_id, params, holding_days)
    run_id = str(uuid.uuid4())

    run = LabRun(
        id=run_id,
        strategy_id=strategy_id,
        holding_days=holding_days,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        config_hash=config_hash,
        status="PENDING",
    )
    db.add(run)
    db.commit()

    _ensure_worker_started()
    _job_queue.put({
        "run_id": run_id,
        "strategy_id": strategy_id,
        "holding_days": holding_days,
        "params": params,
        "capital": capital,
        "risk_pct": risk_pct,
        "max_positions": max_positions,
        "config_hash": config_hash,
    })
    return run_id
