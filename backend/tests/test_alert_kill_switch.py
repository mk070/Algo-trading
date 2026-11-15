import pytest
from unittest.mock import MagicMock
from app.notify.dispatcher import dispatcher
from app.settings import settings


def test_kill_switch_defaults_to_suppressed():
    """Verify that alerts are disabled by default (fail-closed guarantee)."""
    assert settings.alerts_enabled is False


def test_dispatch_suppresses_all_channels_when_disabled(monkeypatch):
    """Verify that when alerts_enabled is False, Telegram, DB, and SSE are all suppressed."""
    monkeypatch.setattr(settings, "alerts_enabled", False)

    mock_db = MagicMock()
    mock_db.add = MagicMock()

    res = dispatcher.dispatch(
        alert_type="BUY",
        title="TEST ALERT",
        body="Should be suppressed",
        symbol="TCS",
        market="IN",
        db=mock_db,
    )

    assert res.accepted is False
    assert res.delivered_telegram is False
    assert res.persisted_db is False
    assert res.broadcast_sse is False
    assert res.suppression_reason == "ALERTS_DISABLED_BY_DEFAULT"
    # Ensure database add was never called
    mock_db.add.assert_not_called()


def test_dispatch_accepts_when_explicitly_enabled(monkeypatch):
    """Verify that when alerts_enabled is True, dispatch is accepted."""
    monkeypatch.setattr(settings, "alerts_enabled", True)
    dispatcher.sent_alert_keys.clear()

    mock_db = MagicMock()
    saved_row = None

    def capture_add(row):
        nonlocal saved_row
        saved_row = row

    mock_db.add = capture_add
    mock_db.query.return_value.filter.return_value.first.return_value = None

    res = dispatcher.dispatch(
        alert_type="BUY",
        title="TEST EXPLICIT ENABLED",
        body="This should pass",
        symbol="INFY",
        market="IN",
        db=mock_db,
    )

    assert res.accepted is True
    assert res.persisted_db is True
    assert saved_row is not None
    assert saved_row.symbol == "INFY"
