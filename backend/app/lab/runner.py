"""Strategy Lab — Background Backtest Runner.

Runs backtest jobs asynchronously. Each job:
1. Loads historical bars from parquet (never queries Neon per-symbol).
2. Runs the lab engine for the strategy/holding combo.
3. Persists results and trades to Neon PostgreSQL.
4. Updates job status/progress.
"""

import datetime
import json
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# In-process job thread registry (simple; for production use Celery or APScheduler)
_active_jobs: Dict[str, threading.Thread] = {}


def _run_job(run_id: str, strategy_id: str, holding_days: int, params: Dict,
             capital: float, risk_pct: float, max_positions: int, config_hash: str):
    """Execute backtest in background thread and persist results."""
    from app.db import transaction_context
    from app.lab.models_lab import LabRun, LabResult, LabTrade
    from app.lab.engine import run_single_strategy_backtest
    from app.engine.research_loader import load_research_bars
    from app.engine.indicators import add_all_indicators
    import pandas as pd

    logger.info(f"[Lab] Starting run {run_id}: {strategy_id} H={holding_days}")

    # Mark as RUNNING
    with transaction_context() as db:
        run = db.query(LabRun).filter(LabRun.id == run_id).first()
        if run:
            run.status = "RUNNING"
            run.started_at = datetime.datetime.now(datetime.timezone.utc)

    try:
        # Load bars from parquet (all symbols)
        bars_dict = load_research_bars(symbols=[], start_date=None, end_date=None)
        if not bars_dict:
            raise RuntimeError("No historical bars found. Check parquet snapshot.")

        # Update progress
        with transaction_context() as db:
            run = db.query(LabRun).filter(LabRun.id == run_id).first()
            if run:
                run.progress_pct = 10
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

        # Persist results
        with transaction_context() as db:
            # Upsert result
            result = LabResult(
                run_id=run_id,
                strategy_id=strategy_id,
                holding_days=holding_days,
                config_hash=config_hash,
                total_trades=summary["total_trades"],
                win_rate=summary.get("win_rate"),
                expectancy_r=summary.get("expectancy_r"),
                median_net_expectancy=summary.get("median_net_expectancy"),
                avg_win_r=summary.get("avg_win_r"),
                avg_loss_r=summary.get("avg_loss_r"),
                profit_factor=summary.get("profit_factor"),
                cagr_pct=summary.get("cagr_pct"),
                max_drawdown_pct=summary.get("max_drawdown_pct"),
                sharpe_ratio=summary.get("sharpe_ratio"),
                total_pnl=summary.get("total_pnl"),
                total_costs=summary.get("total_costs"),
                sample_ok=summary.get("sample_ok", False),
                sample_label=summary.get("sample_label"),
                half1_expectancy=summary.get("half1_expectancy"),
                half2_expectancy=summary.get("half2_expectancy"),
                half_consistency=summary.get("half_consistency"),
                metrics_json=json.dumps(summary),
            )
            db.add(result)

            # Persist individual trades (batch insert)
            for t in trades:
                entry_date = t.entry_date
                exit_date = t.exit_date
                # Convert to date if needed
                if hasattr(entry_date, "date"):
                    entry_date = entry_date.date() if callable(entry_date.date) else entry_date
                if hasattr(exit_date, "date") and exit_date is not None:
                    exit_date = exit_date.date() if callable(exit_date.date) else exit_date

                trade_rec = LabTrade(
                    run_id=run_id,
                    strategy_id=strategy_id,
                    holding_days=holding_days,
                    symbol=t.symbol,
                    entry_date=entry_date,
                    exit_date=exit_date,
                    entry_price=t.entry_price,
                    exit_price=t.exit_price,
                    stop_price=t.stop_price,
                    qty=t.qty,
                    gross_pnl=t.gross_pnl,
                    costs=t.costs,
                    net_pnl=t.net_pnl,
                    r_multiple=t.r_multiple,
                    exit_reason=t.exit_reason,
                    holding_days_actual=t.holding_days_actual,
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
    finally:
        _active_jobs.pop(run_id, None)


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
    Create a LabRun DB record and launch a background thread.
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

    t = threading.Thread(
        target=_run_job,
        args=(run_id, strategy_id, holding_days, params, capital, risk_pct, max_positions, config_hash),
        daemon=True,
    )
    _active_jobs[run_id] = t
    t.start()
    return run_id
