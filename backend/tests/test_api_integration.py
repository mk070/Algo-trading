from fastapi.testclient import TestClient
import pytest
from app.main import app

client = TestClient(app)


def test_api_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["HEALTHY", "DEGRADED"]
    assert "providers" in data
    assert "angelone" in data["providers"]
    assert "kite_personal" in data["providers"]


def test_api_regime_endpoint():
    resp = client.get("/api/regime?market=IN")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market"] == "IN"
    assert data["status"] in ["BULLISH", "CAUTION", "WEAK"]


def test_api_settings_endpoint():
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "markets" in data
    assert "risk" in data
    assert "disclaimer" in data


def test_api_portfolio_status_endpoint():
    resp = client.get("/api/portfolio/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["access"] == "STRICTLY_READ_ONLY"


def test_api_kite_login_url():
    resp = client.get("/api/portfolio/kite/login-url")
    assert resp.status_code == 200
    data = resp.json()
    assert "login_url" in data
    assert "kite.zerodha.com" in data["login_url"]


def test_api_watchlist_endpoint():
    resp = client.get("/api/watchlist?market=IN")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_positions_endpoint():
    resp = client.get("/api/positions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_journal_and_stats():
    resp = client.get("/api/journal")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    resp_stats = client.get("/api/stats")
    assert resp_stats.status_code == 200
    assert "win_rate" in resp_stats.json()


def test_api_news_endpoint():
    resp = client.get("/api/news?days=14")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_api_heatmap_endpoint():
    resp = client.get("/api/heatmap?market=US")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market"] == "US"
    assert "sectors" in data
    assert "advancing" in data
    assert "declining" in data
    assert data["total_stocks"] > 0
    assert len(data["sectors"]) > 0


def test_api_fundamentals_endpoint():
    resp = client.get("/api/fundamentals/AAPL?market=US")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert "overall_score" in data
    assert "verdict" in data
    assert "conclusion" in data
    assert "criteria_checklist" in data
    assert len(data["criteria_checklist"]) >= 10
    assert all("status" in c and c["status"] in ["PASS", "CAUTION", "FAIL"] for c in data["criteria_checklist"])
