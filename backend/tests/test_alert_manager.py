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


def test_telegram_mask_chat_id():
    from app.notify.telegram import TelegramNotifier
    assert TelegramNotifier.mask_chat_id(None) == "Not configured"
    assert TelegramNotifier.mask_chat_id("") == "Not configured"
    assert TelegramNotifier.mask_chat_id("1234") == "****"
    assert TelegramNotifier.mask_chat_id("909235485") == "*****5485"
    assert TelegramNotifier.mask_chat_id("-1001234567890") == "**********7890"


def test_telegram_status_unconfigured():
    from app.notify.telegram import TelegramNotifier
    notifier = TelegramNotifier(token="", chat_id="")
    status = notifier.get_status()
    assert status["status"] == "NOT_CONFIGURED"
    assert status["configured"] is False
    assert status["bot_username"] is None


def test_telegram_get_status_and_test_message(monkeypatch):
    from app.notify.telegram import TelegramNotifier
    notifier = TelegramNotifier(token="mock_token", chat_id="909235485")

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = str(json_data)

        def json(self):
            return self._json

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            if "getMe" in url:
                return MockResponse(200, {
                    "ok": True,
                    "result": {
                        "id": 123456,
                        "username": "SwingMaster7_bot",
                        "first_name": "SwingTrader",
                        "is_bot": True,
                    }
                })
            return MockResponse(404, {"ok": False})

        def post(self, url, json=None, **kwargs):
            if "sendMessage" in url:
                assert json["chat_id"] == "909235485"
                assert "Swing Trading Platform" in json["text"]
                return MockResponse(200, {"ok": True, "result": {"message_id": 999}})
            return MockResponse(400, {"ok": False})

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    # 1. Test status
    status = notifier.get_status()
    assert status["status"] == "CONNECTED"
    assert status["bot_username"] == "@SwingMaster7_bot"
    assert status["masked_chat_id"] == "*****5485"
    assert status["last_check"] is not None

    # 2. Test send_test_message
    ok, msg = notifier.send_test_message()
    assert ok is True
    assert "delivered successfully" in msg


def test_telegram_test_message_failure(monkeypatch):
    from app.notify.telegram import TelegramNotifier
    notifier = TelegramNotifier(token="mock_token", chat_id="909235485")

    class MockResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
            self.text = "Bad Request: chat not found"

        def json(self):
            return self._json

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            return MockResponse(200, {"ok": True, "result": {"username": "SwingMaster7_bot"}})

        def post(self, url, **kwargs):
            return MockResponse(400, {"ok": False, "description": "Bad Request: chat not found"})

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    ok, msg = notifier.send_test_message()
    assert ok is False
    assert "chat not found" in msg


def test_telegram_api_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.notify.telegram import telegram_notifier

    client = TestClient(app)

    monkeypatch.setattr(telegram_notifier, "get_status", lambda: {
        "status": "CONNECTED",
        "configured": True,
        "bot_username": "@SwingMaster7_bot",
        "bot_name": "SwingTrader",
        "masked_chat_id": "*****5485",
        "last_check": "2026-11-01T18:00:00Z",
        "error": None,
    })

    monkeypatch.setattr(telegram_notifier, "send_test_message", lambda: (True, "Test message delivered successfully by @SwingMaster7_bot."))

    # GET status
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "CONNECTED"
    assert data["bot_username"] == "@SwingMaster7_bot"
    assert "token" not in data  # Token must never leak

    # POST test
    resp_post = client.post("/api/telegram/test")
    assert resp_post.status_code == 200
    post_data = resp_post.json()
    assert post_data["success"] is True
    assert "delivered successfully" in post_data["detail"]


def test_alert_deduplication_across_backend_restarts(mem_db):
    # Simulate an alert recorded earlier before backend restart
    past_time = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    alert = Alert(
        ts=past_time,
        type="BUY",
        symbol="INFY",
        market="IN",
        title="BUY: INFY @ 1800",
        body="Actionable breakout alert",
        acknowledged=False,
        retry_count=0,
    )
    mem_db.add(alert)
    mem_db.commit()

    # Simulate fresh backend start: new NotificationDispatcher with empty in-memory set
    new_disp = NotificationDispatcher()
    assert len(new_disp.sent_alert_keys) == 0

    # Dispatch identical alert with db passed
    res = new_disp.dispatch(
        alert_type="BUY",
        title="BUY: INFY @ 1800",
        body="Actionable breakout alert",
        symbol="INFY",
        market="IN",
        db=mem_db,
    )
    # Must be deduplicated via database check to prevent re-sending after reboot
    assert res is None


