"""
Strategy Lab Verification Study & Idempotency Proof.

Verifies:
1. Creating a verification study with `is_test=True`.
2. Running evaluate_study() and persist_evaluation_result() twice.
3. Asserting that counts of trades, daily equity rows, and tomorrow orders remain identical
   after the second run (idempotency proof).
4. Asserting no duplicate trade keys or order keys exist.
"""

import datetime
import json
import uuid
import pytest
from unittest.mock import patch

from app.db import transaction_context
from app.lab.models_lab import (
    LabStudy,
    LabStudyStrategy,
    LabPaperTrade,
    LabPaperDaily,
    LabTomorrowOrder,
    LabEvaluation,
)
from app.lab.evaluator import evaluate_study, ClosedTrade
from app.lab.persist import persist_evaluation_result


def test_verification_study_idempotency():
    study_id = f"test_study_{uuid.uuid4().hex[:8]}"

    # Mock evaluate_study result to simulate deterministic engine output
    sample_closed_trade = ClosedTrade(
        symbol="TCS",
        strategy_id="S01",
        config_hash="test_hash_s01",
        signal_date=datetime.date(2026, 1, 15),
        entry_date=datetime.date(2026, 1, 16),
        entry_price=3500.0,
        exit_date=datetime.date(2026, 1, 22),
        exit_price=3620.0,
        stop_price=3420.0,
        qty=10,
        gross_pnl=1200.0,
        costs=45.0,
        net_pnl=1155.0,
        r_multiple=1.44,
        exit_reason="TIME_EXIT",
        planned_exit_date=datetime.date(2026, 1, 22),
        reason_text="EMA pullback confirmation",
        signal_context={"rsi14": 52.3},
        trade_key=f"tkey_{study_id}_tcs",
        holding_days_target=4,
    )

    eval_result = {
        "status": "OK",
        "study_id": study_id,
        "data_through_date": datetime.date(2026, 1, 24),
        "registry_hash": "hash_reg_test",
        "engine_version": "v1.0",
        "closed_trades": [sample_closed_trade],
        "open_positions": [],
        "tomorrow_orders": {
            "S01": [
                {
                    "order_key": f"okey_{study_id}_infy",
                    "study_id": study_id,
                    "strategy_id": "S01",
                    "config_hash": "test_hash_s01",
                    "symbol": "INFY",
                    "signal_date": datetime.date(2026, 1, 24),
                    "signal_reason": "EMA pullback",
                    "signal_context_json": "{}",
                    "planned_entry": 1650.0,
                    "stop_price": 1600.0,
                    "research_qty": 20,
                    "practical_qty": 2,
                    "planned_exit_date": datetime.date(2026, 1, 30),
                    "holding_days_target": 4,
                    "status": "PENDING",
                }
            ]
        },
        "daily_equity": {
            "S01": [
                {
                    "strategy_id": "S01",
                    "session_date": datetime.date(2026, 1, 24),
                    "cash": 501155.0,
                    "invested_value": 0.0,
                    "total_equity": 501155.0,
                    "peak_equity": 501155.0,
                    "drawdown_pct": 0.0,
                    "cumulative_return_pct": 0.231,
                    "realized_pnl": 1155.0,
                    "unrealized_pnl": 0.0,
                    "open_positions": 0,
                    "trades_today": 1,
                    "cumulative_costs": 45.0,
                }
            ]
        },
    }

    with transaction_context() as db:
        # Create verification study
        study = LabStudy(
            id=study_id,
            name="Verification Test Study",
            status="ACTIVE",
            start_date=datetime.date(2026, 1, 1),
            capital=500000.0,
            risk_pct=0.5,
            max_positions=5,
            strategies_json=json.dumps([{"strategy_id": "S01", "holding_days": 4}]),
            is_test=True,
        )
        db.add(study)
        db.commit()

    try:
        # 1. First persistence pass
        with transaction_context() as db:
            eval_id_1 = persist_evaluation_result(study_id, eval_result, db)
            db.commit()

        # Check records after 1st run
        with transaction_context() as db:
            trade_count_1 = db.query(LabPaperTrade).filter(LabPaperTrade.study_id == study_id).count()
            daily_count_1 = db.query(LabPaperDaily).filter(LabPaperDaily.study_id == study_id).count()
            order_count_1 = db.query(LabTomorrowOrder).filter(LabTomorrowOrder.study_id == study_id).count()

        assert trade_count_1 == 1, f"Expected 1 trade, got {trade_count_1}"
        assert daily_count_1 == 1, f"Expected 1 daily row, got {daily_count_1}"
        assert order_count_1 == 1, f"Expected 1 tomorrow order, got {order_count_1}"

        # 2. Second persistence pass (Idempotency check)
        with transaction_context() as db:
            eval_id_2 = persist_evaluation_result(study_id, eval_result, db)
            db.commit()

        # Check records after 2nd run — MUST BE UNCHANGED
        with transaction_context() as db:
            trade_count_2 = db.query(LabPaperTrade).filter(LabPaperTrade.study_id == study_id).count()
            daily_count_2 = db.query(LabPaperDaily).filter(LabPaperDaily.study_id == study_id).count()
            order_count_2 = db.query(LabTomorrowOrder).filter(LabTomorrowOrder.study_id == study_id).count()

        assert trade_count_2 == trade_count_1 == 1, "Duplicate trades inserted on 2nd pass!"
        assert daily_count_2 == daily_count_1 == 1, "Duplicate daily equity rows inserted on 2nd pass!"
        assert order_count_2 == order_count_1 == 1, "Duplicate tomorrow orders inserted on 2nd pass!"

    finally:
        # Cleanup test study
        with transaction_context() as db:
            db.query(LabTomorrowOrder).filter(LabTomorrowOrder.study_id == study_id).delete()
            db.query(LabPaperDaily).filter(LabPaperDaily.study_id == study_id).delete()
            db.query(LabPaperTrade).filter(LabPaperTrade.study_id == study_id).delete()
            db.query(LabEvaluation).filter(LabEvaluation.study_id == study_id).delete()
            db.query(LabStudy).filter(LabStudy.id == study_id).delete()
            db.commit()
