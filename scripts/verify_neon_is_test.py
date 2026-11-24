"""
Strategy Lab — Neon PostgreSQL Verification Study Evidence Script.

Runs an end-to-end live test against Neon PostgreSQL:
1. Creates an active study marked `is_test = True` starting 20 sessions before the latest bar.
2. Executes Run 1: evaluate_study() + persist_evaluation_result().
3. Queries Neon for counts: trades, daily rows, tomorrow orders, evaluations.
4. Executes Run 2: evaluate_study() + persist_evaluation_result().
5. Queries Neon again and asserts row counts remain identical (idempotency proof).
6. Runs backtest engine for same strategy/parameters and compares metrics.
"""

import datetime
import json
import uuid
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import transaction_context
from app.models import Instrument, DailyBar
from app.lab.models_lab import (
    LabStudy,
    LabStudyStrategy,
    LabPaperTrade,
    LabPaperDaily,
    LabTomorrowOrder,
    LabEvaluation,
)
from app.lab.evaluator import evaluate_study
from app.lab.persist import persist_evaluation_result
from app.lab.engine import run_single_strategy_backtest, compute_config_hash
from app.engine.research_loader import load_research_bars_for_paper


def main():
    print("=" * 70)
    print("NEON POSTGRESQL VERIFICATION EVIDENCE: IS_TEST STUDY IDEMPOTENCY")
    print("=" * 70)

    with transaction_context() as db:
        # 1. Determine latest bar date for Indian equities in Neon
        from sqlalchemy import func
        latest_date = (
            db.query(func.max(DailyBar.date))
            .join(Instrument, Instrument.symbol == DailyBar.symbol)
            .filter(Instrument.market == "IN")
            .scalar()
        )
        if not latest_date:
            latest_date = datetime.date(2026, 11, 23)

        # 20 trading sessions is ~30 calendar days
        start_date = latest_date - datetime.timedelta(days=32)
        study_id = f"test_neon_{uuid.uuid4().hex[:8]}"

        print(f"Data through date in Neon: {latest_date}")
        print(f"Study ID:                  {study_id}")
        print(f"Study start date:          {start_date}")
        print(f"is_test flag:              True")

        strategy_id = "S01"
        holding_days = 4
        params = {"ema_len": 20, "rsi_len": 14, "trend_sma": 200, "stop_atr_mult": 1.5}
        cfg_hash = compute_config_hash(strategy_id, params, holding_days)

        study = LabStudy(
            id=study_id,
            name=f"NEON_VERIFICATION_IS_TEST_{study_id[-6:]}",
            status="ACTIVE",
            start_date=start_date,
            capital=500000.0,
            risk_pct=0.5,
            max_positions=5,
            strategies_json=json.dumps([{"strategy_id": strategy_id, "holding_days": holding_days}]),
            is_test=True,
        )
        db.add(study)

        study_strat = LabStudyStrategy(
            study_id=study_id,
            strategy_id=strategy_id,
            holding_days=holding_days,
            config_hash=cfg_hash,
            parameters_json=json.dumps(params),
        )
        db.add(study_strat)
        db.commit()

    try:
        # Pre-load bars once
        print("\nLoading research bars for paper evaluation from Neon DB...")
        with transaction_context() as db:
            bars_dict, data_through = load_research_bars_for_paper(db=db)

        # ─── RUN 1 ────────────────────────────────────────────────────────────
        print("\n--> Executing Evaluation RUN 1...")
        with transaction_context() as db:
            res1 = evaluate_study(
                study_id=study_id,
                db=db,
                preloaded_bars=bars_dict,
                preloaded_data_through_date=data_through,
                allow_stale_for_test=True,
            )
            print(f"RUN 1 Status: {res1.get('status')}")
            eval_id_1 = persist_evaluation_result(study_id=study_id, result=res1, db=db)
            db.commit()

        # Query Neon row counts after Run 1
        with transaction_context() as db:
            c_trades_1 = db.query(LabPaperTrade).filter(LabPaperTrade.study_id == study_id).count()
            c_daily_1 = db.query(LabPaperDaily).filter(LabPaperDaily.study_id == study_id).count()
            c_orders_1 = db.query(LabTomorrowOrder).filter(LabTomorrowOrder.study_id == study_id).count()
            c_evals_1 = db.query(LabEvaluation).filter(LabEvaluation.study_id == study_id).count()

        print(f"\n[NEON ROW COUNTS AFTER RUN 1]")
        print(f"  lab_paper_trades:    {c_trades_1}")
        print(f"  lab_paper_daily:     {c_daily_1}")
        print(f"  lab_tomorrow_orders: {c_orders_1}")
        print(f"  lab_evaluations:     {c_evals_1} (Evaluation ID: {eval_id_1})")

        # ─── RUN 2 (IDEMPOTENCY TEST) ─────────────────────────────────────────
        print("\n--> Executing Evaluation RUN 2 (Idempotency Re-evaluation)...")
        with transaction_context() as db:
            res2 = evaluate_study(
                study_id=study_id,
                db=db,
                preloaded_bars=bars_dict,
                preloaded_data_through_date=data_through,
                allow_stale_for_test=True,
            )
            print(f"RUN 2 Status: {res2.get('status')}")
            eval_id_2 = persist_evaluation_result(study_id=study_id, result=res2, db=db)
            db.commit()

        # Query Neon row counts after Run 2
        with transaction_context() as db:
            c_trades_2 = db.query(LabPaperTrade).filter(LabPaperTrade.study_id == study_id).count()
            c_daily_2 = db.query(LabPaperDaily).filter(LabPaperDaily.study_id == study_id).count()
            c_orders_2 = db.query(LabTomorrowOrder).filter(LabTomorrowOrder.study_id == study_id).count()
            c_evals_2 = db.query(LabEvaluation).filter(LabEvaluation.study_id == study_id).count()

        print(f"\n[NEON ROW COUNTS AFTER RUN 2]")
        print(f"  lab_paper_trades:    {c_trades_2} (Delta: {c_trades_2 - c_trades_1})")
        print(f"  lab_paper_daily:     {c_daily_2} (Delta: {c_daily_2 - c_daily_1})")
        print(f"  lab_tomorrow_orders: {c_orders_2} (Delta: {c_orders_2 - c_orders_1})")
        print(f"  lab_evaluations:     {c_evals_2} (Delta: {c_evals_2 - c_evals_1})")

        # Assertions
        assert c_trades_1 == c_trades_2, f"Idempotency failed: trades changed ({c_trades_1} -> {c_trades_2})"
        assert c_daily_1 == c_daily_2, f"Idempotency failed: daily rows changed ({c_daily_1} -> {c_daily_2})"
        assert c_orders_1 == c_orders_2, f"Idempotency failed: tomorrow orders changed ({c_orders_1} -> {c_orders_2})"
        assert c_evals_2 == c_evals_1 + 1, f"Audit log did not append properly ({c_evals_1} -> {c_evals_2})"
        print("\n>>> IDEMPOTENCY VERIFIED: ZERO DUPLICATE ROWS INSERTED IN NEON POSTGRESQL <<<")

        # ─── RUN BACKTEST FOR PARITY COMPARISON ───────────────────────────────
        print("\n--> Running backtest engine for same strategy and parameters...")
        bt_trades, bt_summary = run_single_strategy_backtest(
            strategy_id=strategy_id,
            params=params,
            holding_days=holding_days,
            bars_dict=bars_dict,
            capital=500000.0,
            risk_pct=0.5,
            max_positions=5,
        )

        # Filter backtest trades to the paper window for comparison
        window_bt_trades = [
            t for t in bt_trades
            if (t.entry_date.date() if hasattr(t.entry_date, 'date') else t.entry_date) >= start_date
        ]
        print(f"Total backtest trades (full history):       {len(bt_trades)}")
        print(f"Backtest trades in study window:             {len(window_bt_trades)}")
        print(f"Forward paper closed trades in study window: {c_trades_2}")
        print(f"Backtest Expectancy R (full history):        {bt_summary.get('expectancy_r', 0):.4f}R")
        print(f"Backtest Win Rate:                           {bt_summary.get('win_rate', 0):.1f}%")

    finally:
        # Clean up test rows
        print("\nCleaning up verification study rows from Neon...")
        with transaction_context() as db:
            db.query(LabTomorrowOrder).filter(LabTomorrowOrder.study_id == study_id).delete()
            db.query(LabPaperDaily).filter(LabPaperDaily.study_id == study_id).delete()
            db.query(LabPaperTrade).filter(LabPaperTrade.study_id == study_id).delete()
            db.query(LabEvaluation).filter(LabEvaluation.study_id == study_id).delete()
            db.query(LabStudyStrategy).filter(LabStudyStrategy.study_id == study_id).delete()
            db.query(LabStudy).filter(LabStudy.id == study_id).delete()
            db.commit()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
