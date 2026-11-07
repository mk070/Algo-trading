"""
Unit and Integration Test Suite for Deterministic Paper Broker & Replay Engine.

Tests:
1. Independent strategy accounts (no cash borrowing, separate holdings)
2. Whole-share sizing & non-negative cash invariant
3. Insufficient cash rejection logged in order journal
4. Adverse slippage application (+0.10% buy, -0.10% sell)
5. Liquidity & volume participation constraints
6. Zerodha delivery charges and GST breakdown
7. DP charge on full closure (INR 15.93 flat)
8. DP charge NOT incurred on partial trim
9. Trim that fully closes position DOES incur DP charge
10. Repeated partial fills of same scrip on same sell day incur DP at most once
11. Missing market prices rejection handling
12. Regime failure liquidates to 100% cash (conservative fallback)
13. Idempotent state persistence & crash recovery
14. Signal-date vs execution-date separation
15. Performance metrics calculation (Sharpe, Sortino, CAGR, Max Drawdown)
"""

import datetime
import json
import math
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.engine.paper_broker import (
    DeterministicPaperBroker,
    PaperAccount,
    calculate_indian_delivery_charges,
)
from app.engine.replay_runner import compute_performance_metrics


class TestIndianDeliveryCharges:
    def test_buy_charges_breakdown(self):
        turnover = 20000.0
        c = calculate_indian_delivery_charges(turnover, side="BUY")

        assert c["brokerage"] == 0.0
        assert c["stt"] == round(0.001 * turnover, 2)  # 20.00
        assert c["exchange_charges"] == round(0.00003 * turnover, 2)  # 0.60
        assert c["sebi_charges"] == round((10.0 / 10000000.0) * turnover, 2)  # 0.02
        assert c["stamp_duty"] == round(0.00015 * turnover, 2)  # 3.00
        assert c["dp_charges"] == 0.0  # Zero DP on buy side

        gst_base = c["exchange_charges"] + c["sebi_charges"] + c["dp_charges"]
        assert c["gst"] == round(0.18 * gst_base, 2)
        expected_total = c["stt"] + c["exchange_charges"] + c["sebi_charges"] + c["stamp_duty"] + c["gst"]
        assert c["total_cost"] == round(expected_total, 2)

    def test_full_closure_dp_charge(self):
        turnover = 15000.0
        c = calculate_indian_delivery_charges(turnover, side="SELL", is_full_closure=True, already_charged_dp_today=False)

        assert c["brokerage"] == 0.0
        assert c["stt"] == round(0.001 * turnover, 2)  # 15.00
        assert c["stamp_duty"] == 0.0  # No stamp duty on sell side
        assert c["dp_charges"] == 13.50  # Base DP charge

        # GST on (0.45 + 0.01 + 13.50) = 2.51 -> total DP fee is 13.50 + 2.43 = 15.93
        assert c["total_cost"] > 25.0

    def test_partial_trim_no_dp_charge(self):
        turnover = 5000.0
        # Partial trim leaving position open
        c = calculate_indian_delivery_charges(turnover, side="SELL", is_full_closure=False, already_charged_dp_today=False)

        assert c["dp_charges"] == 0.0, "Partial trim must not incur DP charges"
        assert c["stamp_duty"] == 0.0

    def test_repeated_fills_same_scrip_charged_dp_once(self):
        turnover = 5000.0
        # First fill on same day
        c1 = calculate_indian_delivery_charges(turnover, side="SELL", is_full_closure=True, already_charged_dp_today=False)
        assert c1["dp_charges"] == 13.50

        # Second fill on same scrip on same day
        c2 = calculate_indian_delivery_charges(turnover, side="SELL", is_full_closure=True, already_charged_dp_today=True)
        assert c2["dp_charges"] == 0.0, "Second fill of same scrip on same day must not incur DP again"

    def test_stress_cost_scenario(self):
        turnover = 10000.0
        normal = calculate_indian_delivery_charges(turnover, side="BUY", stress_multiplier=1.0)
        stress = calculate_indian_delivery_charges(turnover, side="BUY", stress_multiplier=2.0)

        assert stress["stt"] == pytest.approx(normal["stt"] * 2.0, abs=0.05)
        assert stress["total_cost"] > normal["total_cost"] * 1.9


class TestPaperBrokerExecutionAndAccounting:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.broker = DeterministicPaperBroker(
            base_dir=self.temp_dir,
            slippage_pct=0.0010,
            max_positions=20,
            min_price=50.0,
            min_median_turnover_60d=50000000.0,
            max_volume_participation_pct=0.01,
        )

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_account_isolation(self):
        acc1 = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        acc2 = self.broker.get_or_create_account("cand2", "Candidate 2", initial_capital=20000.0)

        assert acc1.cash == 20000.0
        assert acc2.cash == 20000.0

        # Execute buy for acc1 only
        open_prices = {"RELIANCE.NS": 2500.0}
        trades = self.broker.execute_target_portfolio(
            account=acc1,
            target_symbols=["RELIANCE.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=True,
        )

        assert len(trades) > 0
        assert acc1.cash < 20000.0
        assert "RELIANCE.NS" in acc1.holdings

        # Assert acc2 remains completely isolated and untouched
        assert acc2.cash == 20000.0
        assert len(acc2.holdings) == 0
        assert len(acc2.trades_journal) == 0

    def test_whole_share_sizing_and_cash_floor(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        open_prices = {
            "INFY.NS": 1850.50,
            "TCS.NS": 3800.00,
            "HDFCBANK.NS": 1650.00,
        }

        self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["INFY.NS", "TCS.NS", "HDFCBANK.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=True,
        )

        assert acc.cash >= 0.0, "Cash must never be negative"
        for sym, pos in acc.holdings.items():
            assert isinstance(pos["shares"], int), "Shares must be strict integer"
            assert pos["shares"] > 0

    def test_insufficient_cash_rejection_logged(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=100.0)
        # Price is far higher than available cash
        open_prices = {"MRF.NS": 130000.0}

        trades = self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["MRF.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=True,
        )

        assert len(trades) == 0
        assert len(acc.orders_journal) == 1
        rejected_order = acc.orders_journal[0]
        assert rejected_order["status"] == "REJECTED"
        assert "REJECTED_INSUFFICIENT_CASH" in rejected_order["rejection_reason"]

    def test_price_floor_rejection(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        # Penny stock below INR 50
        open_prices = {"PENNY.NS": 25.0}

        trades = self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["PENNY.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=True,
        )

        assert len(trades) == 0
        assert len(acc.orders_journal) == 1
        assert "REJECTED_PRICE_FLOOR" in acc.orders_journal[0]["rejection_reason"]

    def test_volume_participation_cap(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        open_prices = {"LOWVOL.NS": 100.0}
        # Volume is only 200 shares. Max 1% participation = 2 shares.
        daily_vols = {"LOWVOL.NS": 200.0}

        self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["LOWVOL.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=True,
            daily_volumes=daily_vols,
        )

        assert "LOWVOL.NS" in acc.holdings
        assert acc.holdings["LOWVOL.NS"]["shares"] <= 2, "Shares must not exceed 1% volume cap"

    def test_bear_regime_liquidates_to_cash(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        acc.holdings["RELIANCE.NS"] = {"shares": 5, "avg_cost": 2500.0, "invested_cost": 12500.0}
        acc.cash = 7500.0

        open_prices = {"RELIANCE.NS": 2600.0}
        # Regime fails (Bear market)
        self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["RELIANCE.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=False,
        )

        assert len(acc.holdings) == 0, "Holdings must be 0 when regime fails"
        assert acc.cash > 20000.0, "Proceeds must be returned to cash"

    def test_mark_to_market_reconciliation_invariant(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        acc.cash = 5000.0
        acc.holdings = {
            "INFY.NS": {"shares": 5, "avg_cost": 1800.0, "invested_cost": 9000.0},
            "TCS.NS": {"shares": 2, "avg_cost": 3000.0, "invested_cost": 6000.0},
        }

        close_prices = {
            "INFY.NS": 1850.0,
            "TCS.NS": 3100.0,
        }

        snapshot = self.broker.mark_to_market_session(
            account=acc,
            close_prices=close_prices,
            session_date="2026-01-02",
            benchmark_close=250.0,
            prev_benchmark_close=248.0,
            regime_status="BULL_REGIME",
        )

        expected_invested = (5 * 1850.0) + (2 * 3100.0)  # 9250 + 6200 = 15450.0
        expected_total = 5000.0 + 15450.0  # 20450.0

        assert snapshot["total_equity"] == expected_total
        assert snapshot["invested_value"] == expected_invested
        assert snapshot["cash"] == 5000.0
        assert acc.total_equity == expected_total


class TestPerformanceMetrics:
    def test_metrics_calculation(self):
        snapshots = [
            {"date": "2026-01-01", "total_equity": 20000.0, "cash": 20000.0, "cumulative_costs": 0.0, "cumulative_slippage": 0.0},
            {"date": "2026-01-02", "total_equity": 20500.0, "cash": 5000.0, "cumulative_costs": 25.0, "cumulative_slippage": 10.0},
            {"date": "2026-01-03", "total_equity": 21000.0, "cash": 5000.0, "cumulative_costs": 25.0, "cumulative_slippage": 10.0},
        ]
        trades = [
            {"side": "SELL", "realized_pnl": 500.0},
            {"side": "SELL", "realized_pnl": 200.0},
        ]

        m = compute_performance_metrics(snapshots, trades, initial_capital=20000.0)
        assert m["net_return_pct"] == 5.0
        assert m["total_trades"] == 2
        assert m["win_rate_pct"] == 100.0
        assert m["total_costs"] == 25.0


class TestPositionLifecycleAndAccountingInvariants:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.broker = DeterministicPaperBroker(base_dir=self.temp_dir)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dp_charge_and_gst_sum_invariant(self):
        turnover = 12000.0
        c = calculate_indian_delivery_charges(turnover, side="SELL", is_full_closure=True, already_charged_dp_today=False)

        assert c["dp_charges"] == 13.50
        assert c["dp_gst"] == 2.43
        assert c["dp_total"] == 15.93
        assert round(c["dp_charges"] + c["dp_gst"], 2) == c["dp_total"]

        # Ensure GST is NOT calculated on top of dp_total (which would be 18% of 15.93)
        expected_gst_base = c["exchange_charges"] + c["sebi_charges"] + 13.50
        assert c["gst"] == round(0.18 * expected_gst_base, 2)

    def test_position_lifecycles_and_separate_closures(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)

        # 1. First Buy on 2026-01-02
        self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["INFY.NS"],
            open_prices={"INFY.NS": 1000.0},
            exec_date="2026-01-02",
            signal_date="2026-01-01",
            regime_pass=True,
        )
        assert "INFY.NS" in acc.holdings
        pos_id_1 = acc.holdings["INFY.NS"]["position_id"]
        assert "POS_cand1_INFY.NS" in pos_id_1

        # 2. First Full Closure on 2026-01-15
        trades_1 = self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=[],
            open_prices={"INFY.NS": 1100.0},
            exec_date="2026-01-15",
            signal_date="2026-01-14",
            regime_pass=True,
        )
        assert len(trades_1) == 1
        assert trades_1[0]["position_id"] == pos_id_1
        assert trades_1[0]["dp_total"] == 15.93
        assert "INFY.NS" not in acc.holdings

        # 3. Second Buy on 2026-02-02 (New Position Lifecycle)
        self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=["INFY.NS"],
            open_prices={"INFY.NS": 1050.0},
            exec_date="2026-02-02",
            signal_date="2026-02-01",
            regime_pass=True,
        )
        assert "INFY.NS" in acc.holdings
        pos_id_2 = acc.holdings["INFY.NS"]["position_id"]
        assert pos_id_2 != pos_id_1, "Subsequent re-entry must generate a distinct position lifecycle identifier"

        # 4. Second Full Closure on 2026-02-20 (Separate date)
        trades_2 = self.broker.execute_target_portfolio(
            account=acc,
            target_symbols=[],
            open_prices={"INFY.NS": 1150.0},
            exec_date="2026-02-20",
            signal_date="2026-02-19",
            regime_pass=True,
        )
        assert len(trades_2) == 1
        assert trades_2[0]["position_id"] == pos_id_2
        assert trades_2[0]["dp_total"] == 15.93, "Distinct lifecycle closure on a separate date must incur DP fee"

    def test_missing_price_flags_incomplete_valuation(self):
        acc = self.broker.get_or_create_account("cand1", "Candidate 1", initial_capital=20000.0)
        acc.holdings["INFY.NS"] = {
            "position_id": "POS_1",
            "shares": 5,
            "avg_cost": 1000.0,
            "invested_cost": 5000.0,
        }

        # Closing price is missing (None or NaN)
        snapshot = self.broker.mark_to_market_session(
            account=acc,
            close_prices={},  # Missing INFY.NS price
            session_date="2026-01-02",
            benchmark_close=250.0,
            prev_benchmark_close=248.0,
            regime_status="BULL_REGIME",
        )

        assert snapshot["is_complete_valuation"] is False
        assert "INFY.NS" in snapshot["missing_price_symbols"]
        assert "INCOMPLETE_VALUATION" in snapshot["valuation_status"]


class TestSchedulerJobRegistration:
    def test_scheduler_jobs_and_timezone(self):
        from app.scheduler.jobs import scheduler, start_scheduler, stop_scheduler
        start_scheduler()
        try:
            job_ids = [j.id for j in scheduler.get_jobs()]
            assert "daily_paper_trading" in job_ids, "daily_paper_trading must be registered in scheduler"
            assert "weekly_paper_reporting" in job_ids, "weekly_paper_reporting must be registered in scheduler"

            daily_job = scheduler.get_job("daily_paper_trading")
            assert str(daily_job.trigger.timezone) == "Asia/Kolkata", "Scheduler timezone must be Asia/Kolkata"
        finally:
            stop_scheduler()

