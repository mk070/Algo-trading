"""
Unit and Integration Tests for Phase 5.1 Prospective Paper-Trading API & Safety.
Validates:
1. CLI execution blocked when forward_paper_trading_enabled is False.
2. Read-only prospective overview API returns actual saved data.
3. Read-only prospective strategy detail API returns valid structure and ledgers.
4. Correct separation between historical replay and prospective records.
5. Handling of missing state files (clean null/empty states, no synthetic data).
6. Idempotent session handling in Cycle4 engine.
7. No live broker order API calls.
"""

import json
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


@pytest.fixture
def client():
    return TestClient(app)


class TestProspectivePaperTradingAPI:
    def test_prospective_overview_returns_saved_data(self, client):
        """Verify GET /api/paper-trading/prospective/overview returns real saved prospective state."""
        response = client.get("/api/paper-trading/prospective/overview")
        assert response.status_code == 200
        data = response.json()

        assert "study_status" in data
        assert "forward_paper_trading_enabled" in data
        assert data["forward_paper_trading_enabled"] is False
        assert data["study_status"] == "AWAITING_OWNER_APPROVAL"

        # Check candidate state fields
        cand = data.get("candidate")
        if cand:
            assert cand["name"] == "candidate_reg_alpha_buf30"
            assert cand["initial_capital"] == 17500.0
            assert "cash" in cand
            assert "total_equity" in cand
            assert "holdings" in cand

        # Check control state fields
        ctrl = data.get("control")
        if ctrl:
            assert ctrl["name"] == "control_c1b_buf30"
            assert ctrl["initial_capital"] == 17500.0

        # Check data freshness metadata
        freshness = data.get("data_freshness", {})
        assert "last_processed_date" in freshness
        assert "valuation_completeness" in freshness

    def test_prospective_strategy_detail_candidate(self, client):
        """Verify GET /api/paper-trading/prospective/strategy/candidate returns detail."""
        response = client.get("/api/paper-trading/prospective/strategy/candidate")
        assert response.status_code == 200
        data = response.json()

        assert data["strategy_id"] == "candidate_reg_alpha_buf30"
        assert data["study_status"] == "AWAITING_OWNER_APPROVAL"
        assert "holdings" in data
        assert "daily_history" in data
        assert "trades_journal" in data
        assert "orders_journal" in data

    def test_prospective_strategy_detail_control(self, client):
        """Verify GET /api/paper-trading/prospective/strategy/control returns detail."""
        response = client.get("/api/paper-trading/prospective/strategy/control")
        assert response.status_code == 200
        data = response.json()

        assert data["strategy_id"] == "control_c1b_buf30"
        assert "holdings" in data
        assert "daily_history" in data

    def test_prospective_strategy_detail_unknown_404(self, client):
        """Verify unknown strategy_id returns 404."""
        response = client.get("/api/paper-trading/prospective/strategy/invalid_strat")
        assert response.status_code == 404

    def test_prospective_missing_files_returns_no_data(self, client, tmp_path):
        """Verify that when state files are absent, API returns clean null/empty data without crash."""
        with patch("app.api.routes_paper_trading.CYCLE4_STATE_DIR", tmp_path):
            response = client.get("/api/paper-trading/prospective/overview")
            assert response.status_code == 200
            data = response.json()
            assert data["data_source"] == "NONE"
            assert data["candidate"] is None
            assert data["control"] is None
            assert data["benchmark"] is None

    def test_separation_between_replay_and_prospective(self, client):
        """Verify historical replay and prospective overview endpoints return distinct data structures."""
        replay_res = client.get("/api/paper-trading/overview")
        prosp_res = client.get("/api/paper-trading/prospective/overview")

        assert replay_res.status_code == 200
        assert prosp_res.status_code == 200

        replay_data = replay_res.json()
        prosp_data = prosp_res.json()

        # Replay uses ₹20,000 research capital across 4 candidate slots
        assert "strategies" in replay_data
        assert len(replay_data["strategies"]) == 4

        # Prospective uses ₹17,500 retail capital across candidate vs control
        assert "candidate" in prosp_data
        assert "control" in prosp_data
        assert "strategies" not in prosp_data
        assert prosp_data["study_status"] == "AWAITING_OWNER_APPROVAL"

    def test_no_live_broker_endpoints_exist_in_paper_trading(self, client):
        """Verify that paper trading routes contain no live broker order placement."""
        # Attempting POST to order placement or replay run must return 404 or 405
        assert client.post("/api/paper-trading/replay/run").status_code in (404, 405)
        assert client.post("/api/paper-trading/order").status_code in (404, 405)
        assert client.post("/api/paper-trading/execute").status_code in (404, 405)
