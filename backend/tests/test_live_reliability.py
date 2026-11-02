import datetime
import time
import pytest
from unittest.mock import MagicMock

from app.providers.base import (
    Quote,
    QuoteFreshness,
    DecisionQuote,
    IneligibleQuoteError,
)
from app.providers.request_layer import (
    CircuitBreakerOpenError,
    CircuitState,
    ProviderRequestLayer,
    SingleFlight,
)
from app.models import Alert, CustomPriceAlert, DailyBar, LatestQuote
from app.notify.dispatcher import NotificationDispatcher
from app.scheduler.monitor import LiveBreakoutMonitor


# --------------------------------------------------------------------------
# 1. Quote Contract & Two Lanes Tests
# --------------------------------------------------------------------------

def test_decision_lane_accepts_fresh_realtime_quote():
    now = datetime.datetime.utcnow()
    q = Quote(
        symbol="TCS",
        market="IN",
        price=3500.0,
        provider="angelone",
        exchange_ts=now,
        received_ts=now,
        freshness=QuoteFreshness.FRESH,
        realtime=True,
    )
    dq = q.to_decision_quote()
    assert isinstance(dq, DecisionQuote)
    assert dq.symbol == "TCS"
    assert dq.price == 3500.0
    assert dq.freshness == QuoteFreshness.FRESH
    assert dq.realtime is True


def test_decision_lane_rejects_stale_or_delayed_quote():
    now = datetime.datetime.utcnow()

    # Stale quote
    q_stale = Quote(
        symbol="TCS",
        price=3500.0,
        provider="angelone",
        exchange_ts=now,
        received_ts=now,
        freshness=QuoteFreshness.STALE,
        realtime=True,
    )
    with pytest.raises(IneligibleQuoteError) as exc_info:
        q_stale.to_decision_quote()
    assert "STALE" in str(exc_info.value)

    # Delayed quote
    q_delayed = Quote(
        symbol="AAPL",
        price=180.0,
        provider="yfinance",
        exchange_ts=now,
        received_ts=now,
        freshness=QuoteFreshness.DELAYED,
        realtime=False,
    )
    with pytest.raises(IneligibleQuoteError) as exc_info:
        q_delayed.to_decision_quote()
    assert "DELAYED" in str(exc_info.value) or "real-time" in str(exc_info.value)


# --------------------------------------------------------------------------
# 2. Request Layer: Single-Flight, TTL, Concurrency, Circuit Breaker
# --------------------------------------------------------------------------

def test_single_flight_coalesces_concurrent_calls():
    sf = SingleFlight()
    call_count = 0

    def slow_fetch():
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return "data_123"

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(sf.execute, "key_A", slow_fetch) for _ in range(5)]
        results = [f.result() for f in futures]

    assert results == ["data_123"] * 5
    assert call_count == 1  # Executed exactly once


def test_request_layer_ttl_cache():
    layer = ProviderRequestLayer("test_provider", max_concurrency=2, default_timeout=2.0)
    counter = 0

    def fetch_data():
        nonlocal counter
        counter += 1
        return f"result_{counter}"

    # First call - cache miss
    val1 = layer.execute("k1", fetch_data, ttl_sec=0.2)
    assert val1 == "result_1"
    assert counter == 1

    # Second call within TTL - cache hit
    val2 = layer.execute("k1", fetch_data, ttl_sec=0.2)
    assert val2 == "result_1"
    assert counter == 1

    # Sleep past TTL
    time.sleep(0.25)
    val3 = layer.execute("k1", fetch_data, ttl_sec=0.2)
    assert val3 == "result_2"
    assert counter == 2


def test_request_layer_circuit_breaker_cooldown():
    layer = ProviderRequestLayer(
        "flaky_provider",
        max_concurrency=2,
        default_timeout=2.0,
        failure_threshold=2,
        cooldown_sec=0.2,
    )

    def failing_fn():
        raise RuntimeError("External API timeout 504")

    # Failure 1
    with pytest.raises(RuntimeError):
        layer.execute("req", failing_fn, max_retries=0)
    assert layer.circuit_state == CircuitState.CLOSED.value

    # Failure 2 -> Trips to OPEN
    with pytest.raises(RuntimeError):
        layer.execute("req", failing_fn, max_retries=0)
    assert layer.circuit_state == CircuitState.OPEN.value

    # Subsequent request immediately blocked by circuit breaker
    with pytest.raises(CircuitBreakerOpenError):
        layer.execute("req", failing_fn, max_retries=0)

    # Wait for cooldown to expire
    time.sleep(0.25)
    assert layer.circuit_state == CircuitState.HALF_OPEN.value

    # Successful probe resets to CLOSED
    ok_res = layer.execute("req", lambda: "recovered", max_retries=0)
    assert ok_res == "recovered"
    assert layer.circuit_state == CircuitState.CLOSED.value


# --------------------------------------------------------------------------
# 3. Quote Audit Snapshot Persistence in Alerts
# --------------------------------------------------------------------------

def test_alert_dispatcher_embeds_quote_audit():
    dispatcher = NotificationDispatcher()
    now = datetime.datetime.utcnow()

    q = Quote(
        symbol="INFY",
        market="IN",
        price=1520.50,
        provider="angelone",
        exchange_ts=now,
        received_ts=now,
        freshness=QuoteFreshness.FRESH,
        realtime=True,
    )

    mock_db = MagicMock()
    saved_alert = None

    def capture_add(row):
        nonlocal saved_alert
        saved_alert = row

    mock_db.add = capture_add
    mock_db.query.return_value.filter.return_value.first.return_value = None

    dispatcher.dispatch(
        alert_type="BUY",
        title="BUY INFY",
        body="Trigger hit",
        symbol="INFY",
        market="IN",
        quote=q,
        db=mock_db,
    )

    assert saved_alert is not None
    import json
    payload = json.loads(saved_alert.payload_json)
    assert "quote_audit" in payload
    audit = payload["quote_audit"]
    assert audit["price"] == 1520.50
    assert audit["provider"] == "angelone"
    assert audit["freshness"] == "FRESH"
    assert audit["realtime"] is True


# --------------------------------------------------------------------------
# 4. Custom Price Alerts Evaluation & Triggering
# --------------------------------------------------------------------------

def test_custom_price_alert_lifecycle(isolated_db_session):
    # Setup test custom price alert
    alert = CustomPriceAlert(
        symbol="MOCK_TEST_SYM",
        market="IN",
        target_price=2500.0,
        condition="ABOVE",
        notes="Breakout test level",
        active=True,
        triggered=False,
    )
    isolated_db_session.add(alert)
    isolated_db_session.commit()
    alert_id = alert.id

    monitor = LiveBreakoutMonitor()

    # Quote below target price: should not trigger
    q_below = Quote(
        symbol="MOCK_TEST_SYM",
        market="IN",
        price=2480.0,
        provider="test",
        freshness=QuoteFreshness.FRESH,
        realtime=True,
    )

    custom_alerts = isolated_db_session.query(CustomPriceAlert).filter(
        CustomPriceAlert.symbol == "MOCK_TEST_SYM",
        CustomPriceAlert.active == True,
        CustomPriceAlert.triggered == False,
    ).all()
    assert len(custom_alerts) == 1
    assert q_below.last_price < custom_alerts[0].target_price

    # Quote reaches or exceeds target price: should trigger
    q_above = Quote(
        symbol="MOCK_TEST_SYM",
        market="IN",
        price=2505.0,
        provider="test",
        freshness=QuoteFreshness.FRESH,
        realtime=True,
    )
    assert q_above.last_price >= custom_alerts[0].target_price
    alert.triggered = True
    alert.triggered_price = q_above.last_price
    alert.triggered_at = datetime.datetime.utcnow()
    isolated_db_session.commit()

    refreshed = isolated_db_session.query(CustomPriceAlert).filter(CustomPriceAlert.id == alert_id).first()
    assert refreshed.triggered is True
    assert refreshed.triggered_price == 2505.0


# --------------------------------------------------------------------------
# 5. Market Pulse & Quick Search Integration Tests
# --------------------------------------------------------------------------

def test_market_pulse_and_search_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. Market pulse endpoint
    resp = client.get("/api/market/pulse?market=IN")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market"] == "IN"
    assert "breadth" in data
    b = data["breadth"]
    assert "total_tracked" in b
    assert "pct_above_50_sma" in b
    assert "advancers" in b
    assert "decliners" in b
    assert "sectors" in data
    assert isinstance(data["sectors"], list)

    # 2. Search endpoint
    search_resp = client.get("/api/search?q=rel&market=IN")
    assert search_resp.status_code == 200
    matches = search_resp.json()
    assert isinstance(matches, list)
    assert len(matches) > 0
    assert any("RELIANCE" in m["symbol"] for m in matches)

    # 3. Custom Alerts API CRUD
    create_resp = client.post("/api/alerts/custom", json={
        "symbol": "TCS",
        "market": "IN",
        "target_price": 3950.0,
        "condition": "ABOVE",
        "notes": "Testing target",
    })
    assert create_resp.status_code == 200
    alert_info = create_resp.json()
    assert alert_info["symbol"] == "TCS"
    aid = alert_info["id"]

    list_resp = client.get("/api/alerts/custom?market=IN")
    assert list_resp.status_code == 200
    assert any(a["id"] == aid for a in list_resp.json())

    del_resp = client.delete(f"/api/alerts/custom/{aid}")
    assert del_resp.status_code == 200
