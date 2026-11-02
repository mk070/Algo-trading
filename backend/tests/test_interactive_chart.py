import datetime
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Signal


@pytest.fixture
def client():
    return TestClient(app)


def test_chart_daily_bars_endpoint(client):
    """Test /api/bars/{symbol} returns daily bars and technical indicators."""
    resp = client.get("/api/bars/RELIANCE?market=IN&tf=1d")
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "RELIANCE"
    assert data["market"] == "IN"
    assert data["timeframe"] == "1d"
    assert "feed_status" in data
    assert "provider" in data
    assert len(data["bars"]) > 0

    latest_bar = data["bars"][-1]
    assert "time" in latest_bar
    assert "open" in latest_bar
    assert "high" in latest_bar
    assert "low" in latest_bar
    assert "close" in latest_bar
    assert "volume" in latest_bar
    # Moving Averages & Oscillators
    assert "ema20" in latest_bar
    assert "ema50" in latest_bar
    assert "sma50" in latest_bar
    assert "sma150" in latest_bar
    assert "sma200" in latest_bar
    assert "rsi14" in latest_bar
    assert "atr14" in latest_bar


def test_chart_intraday_15m_bars_endpoint(client):
    """Test /api/bars/{symbol} with 15m timeframe returns intraday candles."""
    resp = client.get("/api/bars/RELIANCE?market=IN&tf=15m")
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "RELIANCE"
    assert data["timeframe"] == "15m"
    assert len(data["bars"]) > 0

    latest_bar = data["bars"][-1]
    # For intraday bars, time must be numeric Unix timestamp in seconds
    assert isinstance(latest_bar["time"], int)
    assert latest_bar["time"] > 1000000000


def test_chart_strategy_overlay(client, isolated_db_session):
    """Test that existing strategy output (VCP / Pullback, trigger, stop, target, trend template) is visualised."""
    test_sig = Signal(
        symbol="RELIANCE",
        market="IN",
        setup="VCP",
        trigger=1350.0,
        entry_zone_high=1365.0,
        stop=1280.0,
        target1=1490.0,
        qty=10,
        risk_amount=700.0,
        cost_estimate=13500.0,
        cost_in_r=0.05,
        rs_rank=0.88,
        score=92.5,
        atr=25.0,
        state="TRIGGERED_CONFIRMED",
        reasons_json='["Tight base consolidation of 20 sessions with depth 12.0%", "Support confirmed above 50 SMA with pivot at 1340.00"]',
    )
    isolated_db_session.add(test_sig)
    isolated_db_session.flush()

    resp = client.get("/api/bars/RELIANCE?market=IN&tf=1d")
    assert resp.status_code == 200
    data = resp.json()

    overlay = data.get("strategy_overlay")
    assert overlay is not None
    assert overlay["setup"] == "VCP"
    assert overlay["trigger"] == 1350.0
    assert overlay["entry_zone_high"] == 1365.0
    assert overlay["stop"] == 1280.0
    assert overlay["target1"] == 1490.0
    assert overlay["state"] == "TRIGGERED_CONFIRMED"
    assert len(overlay["reasons"]) == 2
    assert "trend_template" in overlay


def test_chart_us_market_bars(client):
    """Test US market bars fetching (e.g. AAPL) with indicators."""
    resp = client.get("/api/bars/AAPL?market=US&tf=1d")
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "AAPL"
    assert data["market"] == "US"
    assert len(data["bars"]) > 0
    assert data["bars"][-1]["close"] > 0
