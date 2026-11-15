import datetime
from fastapi.testclient import TestClient
import pytest

from app.db import get_db
from app.engine.exits import exit_manager
from app.main import app
from app.models import Fill, Journal, Position
from app.notify.dispatcher import DispatchResult, dispatcher
from app.providers.base import Quote
from app.providers.manager import provider_manager
from app.scheduler.monitor import LiveBreakoutMonitor

client = TestClient(app)


def test_position_creation_and_initial_qty(isolated_db_session):
    pos = Position(
        symbol="INFY",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1500.0,
        qty=100,
        initial_qty=100,
        initial_stop=1425.0,
        active_stop=1425.0,
        target1=1650.0,
        status="OPEN",
        target_partial_completed=False,
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    assert pos.id is not None
    assert pos.qty == 100
    assert pos.initial_qty == 100
    assert pos.target_partial_completed is False


def test_partial_target_close_atomic_accounting(isolated_db_session):
    pos = Position(
        symbol="TCS",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=3500.0,
        qty=100,
        initial_qty=100,
        initial_stop=3325.0,
        active_stop=3325.0,
        target1=3850.0,
        status="OPEN",
        target_partial_completed=False,
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    payload = {
        "qty": 50,
        "exit_price": 3850.0,
        "exit_date": "2026-04-10",
        "action_type": "PARTIAL_TARGET",
        "exit_reason": "Target 1 partial profit taken",
    }
    resp = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PARTIALLY_CLOSED"
    assert data["remaining_qty"] == 50
    assert data["target_partial_completed"] is True

    # Verify DB state
    isolated_db_session.refresh(pos)
    assert pos.status == "OPEN"
    assert pos.qty == 50
    assert pos.initial_qty == 100
    assert pos.target_partial_completed is True
    assert pos.target_partial_qty == 50
    assert pos.total_reduced_qty == 50

    fills = isolated_db_session.query(Fill).filter(Fill.position_id == pos.id).all()
    assert len(fills) == 1
    assert fills[0].side == "SELL"
    assert fills[0].qty == 50
    assert fills[0].price == 3850.0
    assert fills[0].fill_reason == "PARTIAL_TARGET"

    journals = isolated_db_session.query(Journal).filter(Journal.position_id == pos.id).all()
    assert len(journals) == 1
    assert journals[0].qty == 50
    assert journals[0].exit_price == 3850.0
    assert journals[0].exit_reason == "Target 1 partial profit taken"


def test_manual_reduction_does_not_mark_target_completed(isolated_db_session):
    pos = Position(
        symbol="RELIANCE",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=2800.0,
        qty=100,
        initial_qty=100,
        initial_stop=2660.0,
        active_stop=2660.0,
        target1=3080.0,
        status="OPEN",
        target_partial_completed=False,
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    payload = {
        "qty": 20,
        "exit_price": 2850.0,
        "exit_date": "2026-04-05",
        "action_type": "MANUAL_REDUCTION",
        "exit_reason": "De-risking portfolio",
    }
    resp = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert resp.status_code == 200

    isolated_db_session.refresh(pos)
    assert pos.status == "OPEN"
    assert pos.qty == 80
    assert pos.initial_qty == 100
    assert pos.target_partial_completed is False
    assert pos.total_reduced_qty == 20

    fills = isolated_db_session.query(Fill).filter(Fill.position_id == pos.id).all()
    assert len(fills) == 1
    assert fills[0].fill_reason == "MANUAL_REDUCTION"


def test_ambiguous_partial_exit_rejection(isolated_db_session):
    pos = Position(
        symbol="HDFCBANK",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1600.0,
        qty=100,
        initial_qty=100,
        initial_stop=1520.0,
        active_stop=1520.0,
        target1=1760.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    # Partial quantity sent with no action_type and notes implying stop loss -> ambiguous!
    payload = {
        "qty": 50,
        "exit_price": 1500.0,
        "exit_date": "2026-04-05",
        "exit_reason": "Hard stop hit, cutting half",
    }
    resp = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert resp.status_code == 400
    assert "Ambiguous exit request" in resp.json()["detail"]


def test_close_validation_quantity_and_price(isolated_db_session):
    pos = Position(
        symbol="ICICIBANK",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1100.0,
        qty=50,
        initial_qty=50,
        initial_stop=1045.0,
        active_stop=1045.0,
        target1=1210.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    # Negative qty
    resp = client.post(f"/api/positions/{pos.id}/close", json={"qty": -5, "exit_price": 1150.0, "exit_date": "2026-04-02"})
    assert resp.status_code == 400

    # Qty > available
    resp = client.post(f"/api/positions/{pos.id}/close", json={"qty": 60, "exit_price": 1150.0, "exit_date": "2026-04-02"})
    assert resp.status_code == 400

    # Negative price
    resp = client.post(f"/api/positions/{pos.id}/close", json={"qty": 10, "exit_price": -50.0, "exit_date": "2026-04-02"})
    assert resp.status_code == 400


def test_idempotency_protection_on_fill(isolated_db_session):
    pos = Position(
        symbol="KOTAKBANK",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1800.0,
        qty=100,
        initial_qty=100,
        initial_stop=1710.0,
        active_stop=1710.0,
        target1=1980.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    payload = {
        "qty": 50,
        "exit_price": 1980.0,
        "exit_date": "2026-04-12",
        "action_type": "PARTIAL_TARGET",
        "idempotency_key": "unique_tx_key_abc_123",
    }

    # First request
    resp1 = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert resp1.status_code == 200

    isolated_db_session.refresh(pos)
    assert pos.qty == 50

    # Second request with identical idempotency key
    resp2 = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert resp2.status_code == 200
    assert "already processed" in resp2.json()["message"]

    # Qty should NOT be reduced twice
    isolated_db_session.refresh(pos)
    assert pos.qty == 50
    fills = isolated_db_session.query(Fill).filter(Fill.position_id == pos.id).all()
    assert len(fills) == 1


def test_full_exit_marks_position_closed(isolated_db_session):
    pos = Position(
        symbol="LT",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=3600.0,
        qty=50,
        initial_qty=50,
        initial_stop=3420.0,
        active_stop=3420.0,
        target1=3960.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    payload = {
        "qty": 50,
        "exit_price": 3960.0,
        "exit_date": "2026-04-15",
        "action_type": "FULL_EXIT",
        "exit_reason": "Full target exit",
    }
    resp = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CLOSED"

    isolated_db_session.refresh(pos)
    assert pos.status == "CLOSED"
    assert pos.qty == 0


def test_exit_manager_indicator_safety():
    """Verify zero fabrication: when SMA50 or ATR is None, trend break and chandelier stop don't falsely execute."""
    # Price is below 0.95*entry, but current_sma50 is None -> HOLD, no trend break!
    eval_res = exit_manager.evaluate_position(
        entry_price=100.0,
        initial_stop=90.0,
        current_active_stop=90.0,
        current_price=94.0,  # Below 95, but above active_stop 90
        highest_price_since_entry=105.0,
        current_atr=None,
        current_sma50=None,
        days_held=2,
    )
    assert eval_res.action == "HOLD"

    # Chandelier stop with ATR=None moves to breakeven if > 1R
    eval_res_trail = exit_manager.evaluate_position(
        entry_price=100.0,
        initial_stop=90.0,
        current_active_stop=90.0,
        current_price=115.0,
        highest_price_since_entry=115.0,  # +1.5R
        current_atr=None,
        current_sma50=None,
        days_held=5,
    )
    assert eval_res_trail.action == "TRAIL_UPDATE"
    assert eval_res_trail.new_active_stop == 100.0  # breakeven fallback
    assert "ATR unavailable for chandelier" in eval_res_trail.reason


def test_monitor_durable_partial_alert_dedupe(isolated_db_session, monkeypatch):
    """Verify partial exit alert is dispatched only once and recorded in DB only on acceptance."""
    now = datetime.datetime(2026, 4, 10, 14, 0, tzinfo=datetime.timezone.utc)
    pos = Position(
        symbol="BAJFINANCE",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=7000.0,
        qty=100,
        initial_qty=100,
        initial_stop=6650.0,  # R0 = 350
        active_stop=6650.0,
        target1=7700.0,       # 2R = 7700.0
        status="OPEN",
        target_partial_completed=False,
        partial_exit_alerted_at=None,
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    monitor = LiveBreakoutMonitor()

    # Mock quotes with price >= 2R
    mock_quote = Quote(
        symbol="BAJFINANCE",
        market="IN",
        last_price=7750.0,
        open=7500.0,
        day_high=7800.0,
        day_low=7480.0,
        previous_close=7500.0,
        day_volume=1500000,
        timestamp=now,
        is_stale=False,
        is_realtime=True,
    )
    monkeypatch.setattr(provider_manager, "get_quotes", lambda *args, **kwargs: {"BAJFINANCE": mock_quote})
    monkeypatch.setattr(provider_manager, "get_daily_bars", lambda *args, **kwargs: {})

    # Case A: Dispatch is suppressed (kill switch active) -> timestamp should NOT be written
    monkeypatch.setattr(
        dispatcher,
        "dispatch",
        lambda *args, **kwargs: DispatchResult(
            accepted=False,
            delivered_telegram=False,
            persisted_db=False,
            broadcast_sse=False,
            alert_id=None,
            suppression_reason="KILL_SWITCH_ACTIVE",
        ),
    )

    monitor.tick_market(market="IN", db=isolated_db_session, current_time=now)
    isolated_db_session.refresh(pos)
    assert pos.partial_exit_alerted_at is None  # NOT marked as alerted

    # Case B: Dispatch is accepted -> timestamp IS written
    monkeypatch.setattr(
        dispatcher,
        "dispatch",
        lambda *args, **kwargs: DispatchResult(
            accepted=True,
            delivered_telegram=True,
            persisted_db=True,
            broadcast_sse=True,
            alert_id=101,
            suppression_reason=None,
        ),
    )

    monitor.tick_market(market="IN", db=isolated_db_session, current_time=now)
    isolated_db_session.refresh(pos)
    assert pos.partial_exit_alerted_at is not None

    # Case C: Subsequent run with alerted_at set -> dispatch is NOT called
    dispatched = False
    def fail_if_dispatched(*args, **kwargs):
        nonlocal dispatched
        dispatched = True
        return DispatchResult(accepted=True, delivered_telegram=True, persisted_db=True, broadcast_sse=True)

    monkeypatch.setattr(dispatcher, "dispatch", fail_if_dispatched)
    monitor.tick_market(market="IN", db=isolated_db_session, current_time=now)
    assert dispatched is False
