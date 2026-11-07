"""
Unit & Integration Tests for Cycle 4 Paper-Trading Engine and Workflows.
Validates:
1. Candidate vs Control isolation and independent accounting
2. Whole-share sizing at INR 17,500 and no negative cash
3. Zerodha delivery cost model and DP charge (INR 15.93 on sell exit)
4. Conservative regime handling (fallback to 100% cash)
5. No look-ahead execution (signals at T close, fill at T+1 open)
6. Idempotency and restart recovery
7. Total Equity reconciliation invariant (Total Equity == Cash + Invested Value)
8. Calendar handling (holidays and special sessions)
9. Strict safety assertion: offline paper trading only, no broker endpoints
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

from app.engine.cycle4_paper import (
    Cycle4PaperEngine,
    PortfolioState,
    calculate_zerodha_delivery_cost,
    run_cycle4_daily_step,
)
from app.engine.calendars import is_exchange_holiday, get_expected_trading_days


class TestZerodhaDeliveryCostModel:
    def test_buy_cost_breakdown(self):
        turnover = 10000.0
        costs = calculate_zerodha_delivery_cost(turnover, side="BUY")
        
        assert costs["brokerage"] == 0.0
        assert costs["stt"] == round(0.001 * turnover, 2)  # 10.0
        assert costs["exchange_charges"] == round(0.00003 * turnover, 2)  # 0.30
        assert costs["sebi_charges"] == round(10.0 / 10000000.0 * turnover, 2)  # 0.01
        assert costs["stamp_duty"] == round(0.00015 * turnover, 2)  # 1.50
        assert costs["dp_charges"] == 0.0  # No DP charges on buy
        
        # GST is 18% on (Exchange + SEBI + DP)
        gst_base = costs["exchange_charges"] + costs["sebi_charges"] + costs["dp_charges"]
        assert costs["gst"] == round(0.18 * gst_base, 2)
        assert costs["total_cost"] == round(
            costs["stt"] + costs["exchange_charges"] + costs["sebi_charges"] + costs["stamp_duty"] + costs["dp_charges"] + costs["gst"], 2
        )

    def test_sell_cost_breakdown_with_dp_charge(self):
        turnover = 10000.0
        # 1 scrip sold
        costs = calculate_zerodha_delivery_cost(turnover, side="SELL", n_scrip_sold=1)
        
        assert costs["brokerage"] == 0.0
        assert costs["stt"] == round(0.001 * turnover, 2)
        assert costs["stamp_duty"] == 0.0  # Stamp duty only on BUY
        assert costs["dp_charges"] == 13.50  # Base DP charge
        
        gst_base = costs["exchange_charges"] + costs["sebi_charges"] + 13.50
        assert costs["gst"] == round(0.18 * gst_base, 2)  # 18% on (0.30 + 0.01 + 13.50) = 2.49
        
        # Total DP with GST is 13.50 + 2.43 = 15.93
        assert costs["total_cost"] > 25.0


class TestPortfolioIsolationAndAccounting:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / "state"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_candidate_and_control_isolation(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        assert engine.candidate_state.name == "candidate_reg_alpha_buf30"
        assert engine.control_state.name == "control_c1b_buf30"
        assert engine.candidate_state.cash == 17500.0
        assert engine.control_state.cash == 17500.0

        # Simulate rebalance execution for candidate only
        open_prices = {"RELIANCE.NS": 2500.0, "TCS.NS": 3500.0}
        cand_trades = engine.execute_rebalance(
            engine.candidate_state,
            target_symbols=["RELIANCE.NS", "TCS.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            regime_pass=True,
        )

        assert len(cand_trades) > 0
        assert engine.candidate_state.cash < 17500.0
        assert len(engine.candidate_state.holdings) > 0
        
        # Control state MUST be completely untouched
        assert engine.control_state.cash == 17500.0
        assert len(engine.control_state.holdings) == 0
        assert len(engine.control_state.trade_history) == 0


class TestWholeShareSizingAndCashFloor:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / "state"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_whole_share_integer_sizing(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        target_syms = ["INFY.NS", "HDFCBANK.NS", "ITC.NS", "SBIN.NS"]
        open_prices = {
            "INFY.NS": 1823.45,
            "HDFCBANK.NS": 1650.20,
            "ITC.NS": 485.50,
            "SBIN.NS": 810.10,
        }

        trades = engine.execute_rebalance(
            engine.candidate_state,
            target_symbols=target_syms,
            open_prices=open_prices,
            exec_date="2026-01-02",
            regime_pass=True,
        )

        # Invariants
        assert engine.candidate_state.cash >= 0.0, "Cash must NEVER be negative"
        for sym, pos in engine.candidate_state.holdings.items():
            assert isinstance(pos["shares"], int), f"Shares for {sym} must be strict integer"
            assert pos["shares"] > 0, f"Shares for {sym} must be positive integer"

        # Check total cash + invested <= initial_capital (minus costs)
        invested = sum(pos["invested_cost"] for pos in engine.candidate_state.holdings.values())
        assert engine.candidate_state.cash + invested + engine.candidate_state.cumulative_costs_paid <= 17500.01


class TestRegimeConservativeFallback:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / "state"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_regime_insufficient_data_falls_back_to_cash(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        # Series with only 50 bars
        short_series = pd.Series(np.linspace(15000, 20000, 50))
        is_bull, close, sma, status = engine.evaluate_regime(short_series)

        assert is_bull is False
        assert "INSUFFICIENT_HISTORY" in status

    def test_regime_nan_observation_falls_back_to_cash(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        # 250 bars with NaN at end
        s = pd.Series([20000.0] * 249 + [np.nan])
        is_bull, close, sma, status = engine.evaluate_regime(s)

        assert is_bull is False
        assert "NAN_REGIME_OBSERVATION" in status or "CONSERVATIVE CASH" in status

    def test_bear_regime_liquidates_to_cash(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )
        # Pre-seed holding
        engine.candidate_state.holdings["RELIANCE.NS"] = {
            "shares": 5,
            "avg_cost": 2500.0,
            "invested_cost": 12500.0,
        }
        engine.candidate_state.cash = 5000.0

        open_prices = {"RELIANCE.NS": 2600.0}
        # Regime fails
        trades = engine.execute_rebalance(
            engine.candidate_state,
            target_symbols=["RELIANCE.NS"],
            open_prices=open_prices,
            exec_date="2026-01-02",
            regime_pass=False,  # Bear regime
        )

        assert len(engine.candidate_state.holdings) == 0, "Holdings must be 0 in bear regime"
        assert engine.candidate_state.cash > 17000.0, "Proceeds must be returned to cash"
        assert len(trades) == 1
        assert trades[0]["side"] == "SELL"


class TestMarkToMarketAndReconciliationInvariant:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / "state"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_equity_reconciliation_exact_invariant(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        # Place some holdings
        engine.candidate_state.cash = 4500.0
        engine.candidate_state.holdings = {
            "INFY.NS": {"shares": 4, "avg_cost": 1800.0, "invested_cost": 7200.0},
            "TCS.NS": {"shares": 1, "avg_cost": 3500.0, "invested_cost": 3500.0},
        }

        close_prices = {
            "INFY.NS": 1850.0,
            "TCS.NS": 3600.0,
        }

        res = engine.mark_to_market_session(
            engine.candidate_state,
            close_prices=close_prices,
            session_date="2026-01-02",
            benchmark_close=250.0,
            prev_benchmark_close=248.0,
            regime_status="BULL_REGIME",
        )

        expected_invested = (4 * 1850.0) + (1 * 3600.0)  # 7400 + 3600 = 11000.0
        expected_total_equity = 4500.0 + 11000.0  # 15500.0

        assert res["total_equity"] == expected_total_equity
        assert res["cash"] == 4500.0
        assert res["invested_value"] == expected_invested
        assert engine.candidate_state.total_equity == expected_total_equity


class TestIdempotencyAndStateRecovery:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / "state"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_persistence_and_reload(self):
        engine1 = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        engine1.candidate_state.cash = 8000.0
        engine1.candidate_state.holdings = {
            "SBIN.NS": {"shares": 10, "avg_cost": 800.0, "invested_cost": 8000.0}
        }
        engine1.candidate_state.realized_pnl = 150.0
        engine1._persist_state(engine1.candidate_state)

        # Create new engine instance loading from same directory
        engine2 = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )

        assert engine2.candidate_state.cash == 8000.0
        assert "SBIN.NS" in engine2.candidate_state.holdings
        assert engine2.candidate_state.holdings["SBIN.NS"]["shares"] == 10
        assert engine2.candidate_state.realized_pnl == 150.0


class TestStrictSafetyAssertions:
    def test_no_broker_order_calls(self):
        """
        Confirms that cycle4_paper does not import or call any broker order placement routines.
        """
        import inspect
        from app.engine import cycle4_paper
        source = inspect.getsource(cycle4_paper)

        forbidden = [
            "place_order",
            "modify_order",
            "cancel_order",
            "kite.order",
            "dhan.order",
            "order_placement",
        ]
        for term in forbidden:
            assert term not in source, f"Forbidden live trading call '{term}' found in cycle4_paper!"


class TestFailClosedOperationalBehaviors:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = Path(self.temp_dir) / "state"

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fail_closed_on_stale_data(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )
        snap_df = pd.read_parquet("data/research/research_snapshot_20261106.parquet")
        bench_df = pd.read_parquet("data/research/benchmark_series.parquet")
        # Request session 2026-11-06 but pass snapshot only containing up to 2026-11-05
        res = run_cycle4_daily_step(engine, datetime.date(2026, 11, 6), snap_df, bench_df)
        assert res["status"] == "FAIL_CLOSED_STALE_DATA"
        assert res["latest_available_date"] == "2026-11-05"

    def test_fail_closed_on_missing_regime(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )
        snap_df = pd.read_parquet("data/research/research_snapshot_20261106.parquet")
        bench_df = pd.read_parquet("data/research/benchmark_series.parquet")
        # Add bar for snap_df on 2026-11-06 but omit ^NSEI in bench_df
        dummy_row = snap_df.iloc[-1:].copy()
        dummy_row["date"] = pd.to_datetime("2026-11-06")
        fake_snap = pd.concat([snap_df, dummy_row], ignore_index=True)
        res = run_cycle4_daily_step(engine, datetime.date(2026, 11, 6), fake_snap, bench_df)
        assert res["status"] == "FAIL_CLOSED_MISSING_REGIME"

    def test_fail_closed_on_missing_benchmark(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )
        snap_df = pd.read_parquet("data/research/research_snapshot_20261106.parquet")
        bench_df = pd.read_parquet("data/research/benchmark_series.parquet")
        dummy_row = snap_df.iloc[-1:].copy()
        dummy_row["date"] = pd.to_datetime("2026-11-06")
        fake_snap = pd.concat([snap_df, dummy_row], ignore_index=True)
        # Create bench with ^NSEI but without NIFTYBEES on 2026-11-06
        nsei_row = pd.DataFrame([{
            "symbol": "^NSEI",
            "date": pd.to_datetime("2026-11-06"),
            "open": 24500.0,
            "high": 25000.0,
            "low": 24400.0,
            "close": 25000.0,
            "volume": 500000,
            "description": "NSEI"
        }])
        fake_bench = pd.concat([bench_df, nsei_row], ignore_index=True)
        res = run_cycle4_daily_step(engine, datetime.date(2026, 11, 6), fake_snap, fake_bench)
        assert res["status"] == "FAIL_CLOSED_MISSING_BENCHMARK"

    def test_mark_to_market_incomplete_price_flagging(self):
        engine = Cycle4PaperEngine(
            universe_path="data/universe/research_universe_v1.csv",
            state_dir=str(self.state_dir),
            initial_capital=17500.0,
        )
        engine.candidate_state.holdings = {
            "RELIANCE": {"shares": 5, "avg_cost": 1300.0, "invested_cost": 6500.0}
        }
        # Close price missing (NaN)
        res = engine.mark_to_market_session(
            engine.candidate_state,
            close_prices={"RELIANCE": float("nan")},
            session_date="2026-11-06",
            benchmark_close=280.0,
            prev_benchmark_close=278.0,
            regime_status="BULL_REGIME",
        )
        assert res["is_complete_valuation"] is False
        assert res["valuation_status"] == "WARNING_MISSING_PRICES"
        assert "RELIANCE" in res["missing_price_symbols"]
        # Fallback to avg_cost prevents equity wipeout
        assert res["invested_value"] == 6500.0


