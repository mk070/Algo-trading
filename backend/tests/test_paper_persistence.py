"""
Tests for Cycle 4 Forward Paper-Trading PostgreSQL Persistence.
Validates:
1. ORM model mapping and schema table existence.
2. Cycle4PaperEngine state persistence and restoration from PostgreSQL.
3. Idempotent daily history mark-to-market persistence.
4. Holdings table synchronization (insert, update, delete on exit).
5. Orders and trades journaling with Zerodha fee tracking.
6. Rebalance audit logging.
7. Database-first prospective API endpoints with fallback.
8. Cleanup of all test artifacts so database remains pristine.
"""

import datetime
import json
import pytest
from fastapi.testclient import TestClient

from app.db import transaction_context, engine
from app.main import app
from app.models import (
    PaperAccount,
    PaperDailyHistory,
    PaperOrder,
    PaperTrade,
    PaperHolding,
    PaperRebalanceAudit,
)
from app.engine.cycle4_paper import Cycle4PaperEngine, PortfolioState


TEST_STRAT_CAND = "test_persistence_candidate"
TEST_STRAT_CTRL = "test_persistence_control"


@pytest.fixture(autouse=True)
def cleanup_test_records():
    """Ensure any test-created paper trading records are cleaned up before and after each test."""
    test_strats = [TEST_STRAT_CAND, TEST_STRAT_CTRL]
    with transaction_context() as session:
        session.query(PaperTrade).filter(PaperTrade.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperOrder).filter(PaperOrder.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperHolding).filter(PaperHolding.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperDailyHistory).filter(PaperDailyHistory.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperAccount).filter(PaperAccount.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperRebalanceAudit).filter(PaperRebalanceAudit.signal_date == datetime.date(2026, 11, 6)).delete(synchronize_session=False)

    yield

    with transaction_context() as session:
        session.query(PaperTrade).filter(PaperTrade.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperOrder).filter(PaperOrder.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperHolding).filter(PaperHolding.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperDailyHistory).filter(PaperDailyHistory.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperAccount).filter(PaperAccount.strategy_id.in_(test_strats)).delete(synchronize_session=False)
        session.query(PaperRebalanceAudit).filter(PaperRebalanceAudit.signal_date == datetime.date(2026, 11, 6)).delete(synchronize_session=False)


class TestCycle4DatabasePersistence:
    def test_orm_models_table_creation(self):
        """Verify that all 6 tables exist in the PostgreSQL engine schema."""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        assert "paper_accounts" in table_names
        assert "paper_daily_history" in table_names
        assert "paper_orders" in table_names
        assert "paper_trades" in table_names
        assert "paper_holdings" in table_names
        assert "paper_rebalance_audits" in table_names

    def test_state_persistence_and_restoration(self, tmp_path):
        """Verify saving and restoring PortfolioState via PostgreSQL."""
        engine_inst = Cycle4PaperEngine(state_dir=str(tmp_path), use_db=True)

        state = PortfolioState(name=TEST_STRAT_CAND, initial_capital=17500.0)
        state.cash = 12000.0
        state.total_equity = 17850.0
        state.peak_equity = 17850.0
        state.realized_pnl = 150.0
        state.unrealized_pnl = 200.0
        state.cumulative_costs_paid = 18.50
        state.last_processed_date = "2026-11-06"
        state.holdings = {
            "RELIANCE": {"shares": 2, "avg_cost": 2500.0, "invested_cost": 5000.0},
            "INFY": {"shares": 5, "avg_cost": 1500.0, "invested_cost": 7500.0},
        }

        # Persist state
        engine_inst._persist_state(state)

        # Restore state directly from DB
        restored = engine_inst._load_state_from_db(TEST_STRAT_CAND)
        assert restored is not None
        assert restored.name == TEST_STRAT_CAND
        assert restored.cash == 12000.0
        assert restored.total_equity == 17850.0
        assert restored.realized_pnl == 150.0
        assert restored.cumulative_costs_paid == 18.50
        assert restored.last_processed_date == "2026-11-06"
        assert len(restored.holdings) == 2
        assert restored.holdings["RELIANCE"]["shares"] == 2
        assert restored.holdings["INFY"]["avg_cost"] == 1500.0

    def test_holdings_synchronization_delete_on_exit(self, tmp_path):
        """Verify that liquidating a position removes its row from paper_holdings."""
        engine_inst = Cycle4PaperEngine(state_dir=str(tmp_path), use_db=True)

        state = PortfolioState(name=TEST_STRAT_CAND, initial_capital=17500.0)
        state.holdings = {
            "TCS": {"shares": 3, "avg_cost": 3400.0, "invested_cost": 10200.0},
            "WIPRO": {"shares": 10, "avg_cost": 450.0, "invested_cost": 4500.0},
        }
        engine_inst._persist_state(state)

        # Liquidate WIPRO
        del state.holdings["WIPRO"]
        engine_inst._persist_state(state)

        restored = engine_inst._load_state_from_db(TEST_STRAT_CAND)
        assert restored is not None
        assert "TCS" in restored.holdings
        assert "WIPRO" not in restored.holdings

    def test_daily_history_idempotent_upsert(self, tmp_path):
        """Verify that persisting daily history twice for same session updates rather than duplicates."""
        engine_inst = Cycle4PaperEngine(state_dir=str(tmp_path), use_db=True)
        state = PortfolioState(name=TEST_STRAT_CAND, initial_capital=17500.0)

        daily_rec_1 = {
            "date": "2026-11-06",
            "portfolio": TEST_STRAT_CAND,
            "cash": 17500.0,
            "invested_value": 0.0,
            "total_equity": 17500.0,
            "peak_equity": 17500.0,
            "drawdown_pct": 0.0,
            "cumulative_return_pct": 0.0,
            "cumulative_costs": 0.0,
            "cost_pct_of_capital": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "holdings_count": 0,
            "benchmark_close": 270.5,
            "benchmark_daily_return": 0.005,
            "regime_status": "BULL_REGIME",
            "valuation_status": "VERIFIED_COMPLETE",
            "is_complete_valuation": True,
            "missing_price_symbols": [],
            "stale_price_carry_forwards": {},
        }
        engine_inst._persist_daily_to_db(state, daily_rec_1)

        # Re-run same date with updated valuation (e.g. crash recovery or re-evaluation)
        daily_rec_2 = dict(daily_rec_1)
        daily_rec_2["total_equity"] = 17650.0
        daily_rec_2["cumulative_return_pct"] = 0.86
        engine_inst._persist_daily_to_db(state, daily_rec_2)

        with transaction_context() as session:
            rows = (
                session.query(PaperDailyHistory)
                .filter(
                    PaperDailyHistory.strategy_id == TEST_STRAT_CAND,
                    PaperDailyHistory.session_date == datetime.date(2026, 11, 6),
                )
                .all()
            )
            assert len(rows) == 1
            assert rows[0].total_equity == 17650.0
            assert rows[0].cumulative_return_pct == 0.86

    def test_trade_and_order_journaling(self, tmp_path):
        """Verify trade and order persistence with Zerodha statutory delivery cost breakdown."""
        engine_inst = Cycle4PaperEngine(state_dir=str(tmp_path), use_db=True)

        trade = {
            "exec_date": "2026-11-06",
            "portfolio": TEST_STRAT_CAND,
            "symbol": "HDFCBANK",
            "side": "BUY",
            "action": "ENTER_NEW",
            "shares": 5,
            "ref_open": 1600.0,
            "fill_price": 1601.60,
            "gross_turnover": 8008.0,
            "costs": {
                "brokerage": 0.0,
                "stt": 8.01,
                "exchange_charges": 0.24,
                "sebi_charges": 0.01,
                "stamp_duty": 1.20,
                "dp_charges": 0.0,
                "gst": 0.05,
                "total_cost": 9.51,
            },
            "net_cash_delta": -8017.51,
            "realized_pnl": 0.0,
            "regime_pass": True,
        }
        engine_inst._persist_trade_to_db(trade)

        order = {
            "order_id": f"ORD_{TEST_STRAT_CAND}_2026-11-06_HDFCBANK_ENTER_NEW",
            "strategy_id": TEST_STRAT_CAND,
            "symbol": "HDFCBANK",
            "side": "BUY",
            "order_type": "MARKET",
            "requested_shares": 5,
            "status": "FILLED",
            "rejection_reason": None,
            "signal_date": "2026-11-06",
            "exec_date": "2026-11-06",
        }
        engine_inst._persist_order_to_db(order)

        with transaction_context() as session:
            saved_trade = (
                session.query(PaperTrade)
                .filter(PaperTrade.strategy_id == TEST_STRAT_CAND, PaperTrade.symbol == "HDFCBANK")
                .first()
            )
            assert saved_trade is not None
            assert saved_trade.shares == 5
            assert saved_trade.fill_price == 1601.60
            assert saved_trade.total_cost == 9.51
            costs = json.loads(saved_trade.costs_json)
            assert costs["stt"] == 8.01

            saved_order = (
                session.query(PaperOrder)
                .filter(PaperOrder.order_id == order["order_id"])
                .first()
            )
            assert saved_order is not None
            assert saved_order.status == "FILLED"
            assert saved_order.requested_shares == 5

    def test_rebalance_audit_persistence(self, tmp_path):
        """Verify rebalance signal and ranked top 5 persistence."""
        engine_inst = Cycle4PaperEngine(state_dir=str(tmp_path), use_db=True)

        audit_payload = {
            "signal_date": "2026-11-06",
            "is_bull_regime": True,
            "nsei_close": 24200.0,
            "nsei_sma200": 23500.0,
            "candidate_targets": ["RELIANCE", "TCS", "INFY"],
            "control_targets": ["RELIANCE", "ICICIBANK", "LT"],
            "candidate_top5_ranked": ["RELIANCE", "TCS", "INFY", "BHARTIARTL", "ITC"],
            "control_top5_ranked": ["RELIANCE", "ICICIBANK", "LT", "SBIN", "AXISBANK"],
        }
        engine_inst._persist_rebalance_audit_to_db(audit_payload)

        with transaction_context() as session:
            saved_audit = (
                session.query(PaperRebalanceAudit)
                .filter(PaperRebalanceAudit.signal_date == datetime.date(2026, 11, 6))
                .first()
            )
            assert saved_audit is not None
            assert saved_audit.is_bull_regime is True
            assert saved_audit.nsei_close == 24200.0
            cand_targets = json.loads(saved_audit.candidate_targets_json)
            assert "RELIANCE" in cand_targets
            assert len(cand_targets) == 3

    def test_database_first_api_read(self, tmp_path):
        """Verify prospective overview and strategy detail read from PostgreSQL when available."""
        client = TestClient(app)
        engine_inst = Cycle4PaperEngine(state_dir=str(tmp_path), use_db=True)

        # Seed candidate state into DB
        state = PortfolioState(name=TEST_STRAT_CAND, initial_capital=17500.0)
        state.cash = 10000.0
        state.total_equity = 17500.0
        state.last_processed_date = "2026-11-06"
        state.holdings = {"RELIANCE": {"shares": 3, "avg_cost": 2500.0, "invested_cost": 7500.0}}
        engine_inst._persist_state(state)

        # Query strategy detail API
        from unittest.mock import patch
        with patch.dict("app.api.routes_paper_trading._PROSPECTIVE_STRATEGY_MAP", {TEST_STRAT_CAND: TEST_STRAT_CAND}):
            resp = client.get(f"/api/paper-trading/prospective/strategy/{TEST_STRAT_CAND}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["strategy_id"] == TEST_STRAT_CAND
            assert data["data_source"] == "NEON_POSTGRESQL"
            assert data["account"]["cash"] == 10000.0
            assert "RELIANCE" in data["holdings"]
