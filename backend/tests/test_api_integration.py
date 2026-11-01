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

