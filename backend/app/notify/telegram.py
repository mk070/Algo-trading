import logging
from typing import Optional
import httpx
from app.settings import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends trading alerts, trade plans, and system warnings to Telegram."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.is_configured():
            logger.info(f"Telegram not configured. Alert logged: {text[:80]}...")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                else:
                    logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to deliver Telegram message: {e}")
            return False


telegram_notifier = TelegramNotifier()

