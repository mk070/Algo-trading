import asyncio
import datetime
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from app.models import Alert
from app.notify.telegram import telegram_notifier

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches de-duplicated trading alerts across Telegram and UI SSE stream.
    Features:
    - Full alert catalogue (BUY provisional & confirmed, SELL trail/partial/hard/trend/time, CANCEL, SKIP extended, NEWS, DATA, SYSTEM).
    - Delivery retry with exponential backoff.
    - Repeated notifications for unacknowledged critical alerts.
    - Alert acknowledgment and deduplication tracking.
    """

    CRITICAL_ALERT_TYPES = {
        "BUY_CONFIRMED",
        "BUY",
        "SELL_HARD_STOP",
        "SELL",
        "NEWS_RED",
        "DATA_STALE",
    }

    def __init__(self):
        self.sent_alert_keys: Set[str] = set()
        self.sse_subscribers: List[asyncio.Queue] = []

    def format_buy_alert(
        self,
        symbol: str,
        setup: str,
        price: float,
        trigger: float,
        stop: float,
        target1: float,
        qty: int,
        risk_cur: float,
        reasons: List[str],
        is_provisional: bool = False,
    ) -> str:
        status_label = "PROVISIONAL (Awaiting 15m Close)" if is_provisional else "CONFIRMED (15m Confirmed)"
        return (
            f"🚨 <b>BUY TRIGGERED [{status_label}]: {symbol}</b> ({setup})\n\n"
            f"• <b>Price:</b> {price:.2f}\n"
            f"• <b>Trigger Level:</b> {trigger:.2f}\n"
            f"• <b>Stop Loss:</b> {stop:.2f}\n"
            f"• <b>Target (2R):</b> {target1:.2f}\n"
            f"• <b>Planned Qty:</b> {qty} shares\n"
            f"• <b>Risk:</b> {risk_cur:.2f}\n\n"
            f"<b>Why:</b>\n- " + "\n- ".join(reasons[:2]) + "\n\n"
            f"<i>Reminder: Enter order manually at broker & set GTT/SL order immediately.</i>"
        )

    def format_sell_alert(
        self,
        symbol: str,
        reason_type: str,  # HARD_STOP, TRAIL, PARTIAL, TREND_BREAK, TIME_STOP
        price: float,
        detail: str,
    ) -> str:
        titles = {
            "HARD_STOP": "🛑 HARD STOP HIT - EXIT IMMEDIATELY",
            "TRAIL": "📈 TRAILING STOP HIT - EXIT POSITION",
            "PARTIAL": "🎯 TARGET REACHED - TAKE PARTIAL PROFIT (50%)",
            "TREND_BREAK": "⚠️ TREND BREAK (Below 50 SMA) - EXIT POSITION",
            "TIME_STOP": "⏳ TIME STOP (15 Sessions Stagnant) - EXIT POSITION",
        }
        title = titles.get(reason_type, "EXIT SIGNAL")
        return (
            f"<b>{title}: {symbol}</b>\n\n"
            f"• <b>Current Price:</b> {price:.2f}\n"
            f"• <b>Detail:</b> {detail}\n\n"
            f"<i>Manual Action: Execute exit order through broker terminal.</i>"
        )

    def _deliver_telegram_with_retry(
        self,
        text: str,
        max_retries: int = 3,
        backoff_sec: float = 1.0,
    ) -> Tuple[bool, int]:
        """Delivery with exponential backoff retry."""
        attempt = 0
        while attempt <= max_retries:
            try:
                ok = telegram_notifier.send_message(text)
                if ok:
                    return True, attempt
            except Exception as e:
                logger.warning(f"Telegram delivery attempt {attempt + 1} failed: {e}")

            attempt += 1
            if attempt <= max_retries:
                time.sleep(backoff_sec * (2 ** (attempt - 1)))

        return False, max_retries

    def dispatch(
        self,
        alert_type: str,
        title: str,
        body: str,
        symbol: Optional[str] = None,
        market: str = "IN",
        payload: Optional[Dict] = None,
        db: Optional[Session] = None,
        max_retries: int = 2,
    ) -> Optional[int]:
        """Dispatch alert, enforce deduplication, deliver to Telegram with retry, persist, and broadcast."""
        dedupe_key = f"{alert_type}_{symbol or 'GLOBAL'}_{title}"
        if dedupe_key in self.sent_alert_keys:
            return None
        self.sent_alert_keys.add(dedupe_key)

        now = datetime.datetime.utcnow()
        msg_text = f"<b>{title}</b>\n\n{body}"

        # 1. Deliver to Telegram with retry
        delivered, retries_used = self._deliver_telegram_with_retry(msg_text, max_retries=max_retries)

        # 2. Persist to DB
        alert_id = None
        if db is not None:
            try:
                alert_row = Alert(
                    ts=now,
                    type=alert_type,
                    symbol=symbol,
                    market=market,
                    title=title,
                    body=body,
                    payload_json=json.dumps(payload or {}),
                    delivered_telegram=delivered,
                    acknowledged=False,
                    retry_count=retries_used,
                    last_reminder_ts=None,
                )
                db.add(alert_row)
                db.commit()
                alert_id = alert_row.id
            except Exception as e:
                db.rollback()
                logger.error(f"Error persisting alert to DB: {e}")

        # 3. Broadcast to SSE subscribers
        evt_data = {
            "id": alert_id,
            "type": alert_type,
            "symbol": symbol,
            "market": market,
            "title": title,
            "body": body,
            "payload": payload or {},
            "timestamp": now.isoformat(),
        }
        for q in list(self.sse_subscribers):
            try:
                q.put_nowait(evt_data)
            except Exception:
                pass

        return alert_id

    def repeat_unacknowledged_critical_alerts(
        self,
        db: Session,
        max_age_min: int = 30,
        repeat_interval_min: int = 5,
        max_repeats: int = 3,
    ) -> List[int]:
        """Checks for unacknowledged critical alerts and dispatches reminders."""
        now = datetime.datetime.utcnow()
        cutoff_min = now - datetime.timedelta(minutes=max_age_min)
        interval_cutoff = now - datetime.timedelta(minutes=repeat_interval_min)

        unacked = (
            db.query(Alert)
            .filter(
                Alert.acknowledged == False,
                Alert.ts >= cutoff_min,
                Alert.retry_count < max_repeats,
            )
            .all()
        )

        reminded_ids = []
        for alert in unacked:
            # Check if critical
            if alert.type not in self.CRITICAL_ALERT_TYPES:
                continue

            last_ts = alert.last_reminder_ts or alert.ts
            if last_ts <= interval_cutoff:
                # Dispatch repeated reminder
                reminder_title = f"⚠️ [ACTION REQUIRED] UNACKNOWLEDGED: {alert.title}"
                reminder_body = (
                    f"This critical alert has not been acknowledged:\n\n{alert.body}\n\n"
                    f"Reminder #{alert.retry_count + 1} of {max_repeats}. Please review and execute manually."
                )
                self._deliver_telegram_with_retry(f"<b>{reminder_title}</b>\n\n{reminder_body}", max_retries=1)

                alert.retry_count += 1
                alert.last_reminder_ts = now
                reminded_ids.append(alert.id)

        if reminded_ids:
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating repeated alerts in DB: {e}")

        return reminded_ids

    def acknowledge_alert(self, alert_id: int, db: Session) -> bool:
        """Mark an alert as acknowledged by user."""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.acknowledged = True
            db.commit()
            return True
        return False


dispatcher = NotificationDispatcher()
