import datetime
import pytest
from app.models import Alert
from app.notify.dispatcher import NotificationDispatcher


def test_full_alert_catalogue_formatters():
    disp = NotificationDispatcher()

    # BUY Provisional vs Confirmed
    prov_text = disp.format_buy_alert(
        symbol="TCS",
        setup="VCP",
        price=3500.0,
        trigger=3500.0,
        stop=3400.0,
        target1=3700.0,
        qty=20,
        risk_cur=2000.0,
        reasons=["Tight consolidation", "Volume contraction"],
        is_provisional=True,
    )
    assert "PROVISIONAL" in prov_text

    conf_text = disp.format_buy_alert(
        symbol="TCS",
        setup="VCP",
        price=3510.0,
        trigger=3500.0,
        stop=3400.0,
        target1=3700.0,
        qty=20,
        risk_cur=2000.0,
        reasons=["Tight consolidation", "Volume contraction"],
        is_provisional=False,
    )
    assert "CONFIRMED" in conf_text

    # SELL catalogue
    sell_hard = disp.format_sell_alert("RELIANCE", "HARD_STOP", 2400.0, "Hit initial stop at 2400.0")
    assert "HARD STOP HIT" in sell_hard

    sell_trail = disp.format_sell_alert("RELIANCE", "TRAIL", 2650.0, "Hit trailing stop at 2650.0")
    assert "TRAILING STOP HIT" in sell_trail

    sell_part = disp.format_sell_alert("RELIANCE", "PARTIAL", 2700.0, "Reached 2R target")
    assert "TARGET REACHED" in sell_part

    sell_trend = disp.format_sell_alert("RELIANCE", "TREND_BREAK", 2550.0, "Closed below 50-day moving average")
    assert "TREND BREAK" in sell_trend

    sell_time = disp.format_sell_alert("RELIANCE", "TIME_STOP", 2480.0, "Held for 15 sessions without reaching +0.5R")
    assert "TIME STOP" in sell_time


def test_alert_deduplication(mem_db):
    disp = NotificationDispatcher()
    id1 = disp.dispatch("BUY", "BUY: INFY", "Buy body", symbol="INFY", db=mem_db, max_retries=0)
    assert id1 is not None

    # Immediate duplicate call
    id2 = disp.dispatch("BUY", "BUY: INFY", "Buy body", symbol="INFY", db=mem_db, max_retries=0)
    assert id2 is None  # Skipped


def test_delivery_retry_with_backoff(monkeypatch):
    disp = NotificationDispatcher()
    calls = []

    def mock_send(text):
        calls.append(text)
        if len(calls) < 2:
            return False  # Fail first attempt
        return True  # Succeed on second attempt

    from app.notify.telegram import telegram_notifier
    monkeypatch.setattr(telegram_notifier, "send_message", mock_send)

    delivered, retries = disp._deliver_telegram_with_retry("Test message", max_retries=2, backoff_sec=0.01)
    assert delivered is True
    assert retries == 1
    assert len(calls) == 2


def test_repeated_notifications_for_unacknowledged_critical_alerts(mem_db, monkeypatch):
    disp = NotificationDispatcher()
    monkeypatch.setattr("app.notify.telegram.telegram_notifier.send_message", lambda text: True)

    # 1. Create a critical alert from 10 minutes ago
    ten_min_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    alert = Alert(
        ts=ten_min_ago,
        type="BUY_CONFIRMED",
        symbol="SBIN",
        market="IN",
        title="BUY CONFIRMED: SBIN",
        body="Execute buy 100 shares at 800",
        acknowledged=False,
        retry_count=0,
        last_reminder_ts=None,
    )
    mem_db.add(alert)
    mem_db.commit()

    # 2. Run reminder check (repeat interval 5 mins)
    reminded = disp.repeat_unacknowledged_critical_alerts(mem_db, max_age_min=30, repeat_interval_min=5, max_repeats=3)
    assert alert.id in reminded

    mem_db.refresh(alert)
    assert alert.retry_count == 1
    assert alert.last_reminder_ts is not None

    # 3. Acknowledge alert
    ok = disp.acknowledge_alert(alert.id, mem_db)
    assert ok is True

    mem_db.refresh(alert)
    assert alert.acknowledged is True

    # 4. Next reminder run should NOT remind this alert
    reminded_again = disp.repeat_unacknowledged_critical_alerts(mem_db, max_age_min=30, repeat_interval_min=5)
    assert alert.id not in reminded_again

