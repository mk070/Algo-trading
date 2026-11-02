import datetime
import logging
from typing import Any, Dict, Optional, Tuple
import httpx
from app.settings import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends trading alerts, trade plans, and system warnings to Telegram.
    Strictly outbound notification channel; no commands or broker execution.
    """

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token if token is not None else settings.telegram_bot_token
        self.chat_id = chat_id if chat_id is not None else settings.telegram_chat_id
        self.last_check_ts: Optional[datetime.datetime] = None
        self.cached_bot_info: Optional[Dict[str, Any]] = None

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    @staticmethod
    def mask_chat_id(chat_id: Optional[str]) -> str:
        """Masks sensitive chat ID, e.g. '909235485' -> '*****5485'."""
        if not chat_id:
            return "Not configured"
        cid_str = str(chat_id).strip()
        if len(cid_str) <= 4:
            return "****"
        return f"{'*' * (len(cid_str) - 4)}{cid_str[-4:]}"

    def get_bot_info(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Validates bot credentials using Telegram's getMe API."""
        if not self.token:
            return False, None, "Bot token is missing in configuration (.env)"

        url = f"https://api.telegram.org/bot{self.token}/getMe"
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url)
                data = resp.json()
                if resp.status_code == 200 and data.get("ok"):
                    self.cached_bot_info = data.get("result", {})
                    self.last_check_ts = datetime.datetime.now(datetime.timezone.utc)
                    return True, self.cached_bot_info, None
                err_desc = data.get("description", f"Telegram API HTTP {resp.status_code}")
                return False, None, err_desc
        except Exception as e:
            logger.error(f"Telegram getMe validation failed: {e}")
            return False, None, f"Network error contacting Telegram API: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """Returns connection status, bot username, masked chat ID, and last check timestamp."""
        if not self.is_configured():
            return {
                "status": "NOT_CONFIGURED",
                "configured": False,
                "bot_username": None,
                "bot_name": None,
                "masked_chat_id": self.mask_chat_id(self.chat_id) if self.chat_id else None,
                "last_check": self.last_check_ts.isoformat() if self.last_check_ts else None,
                "error": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in backend configuration.",
            }

        ok, info, err = self.get_bot_info()
        if ok and info:
            uname = info.get("username")
            return {
                "status": "CONNECTED",
                "configured": True,
                "bot_username": f"@{uname}" if uname else None,
                "bot_name": info.get("first_name"),
                "masked_chat_id": self.mask_chat_id(self.chat_id),
                "last_check": self.last_check_ts.isoformat() if self.last_check_ts else None,
                "error": None,
            }
        else:
            return {
                "status": "ERROR",
                "configured": True,
                "bot_username": None,
                "bot_name": None,
                "masked_chat_id": self.mask_chat_id(self.chat_id),
                "last_check": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "error": err or "Failed to connect to Telegram API",
            }

    def send_message(self, text: str) -> bool:
        """Sends an HTML formatted message to the configured Telegram chat."""
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
                data = resp.json()
                if resp.status_code == 200 and data.get("ok"):
                    return True
                else:
                    logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to deliver Telegram message: {e}")
            return False

    def send_test_message(self) -> Tuple[bool, str]:
        """Validates the bot using getMe, then sends exactly one test message to the configured chat.
        Displays success only when Telegram confirms the message was sent.
        """
        if not self.is_configured():
            return False, "Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env."

        # Step 1: Validate bot token with getMe
        ok, info, err = self.get_bot_info()
        if not ok or not info:
            return False, f"Bot validation failed: {err}"

        # Step 2: Send test message
        test_text = (
            "✅ <b>Swing Trading Platform</b>\n\n"
            "Telegram notifications are working correctly.\n"
            "You will receive important trading alerts here."
        )

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": test_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                data = resp.json()
                if resp.status_code == 200 and data.get("ok"):
                    self.last_check_ts = datetime.datetime.now(datetime.timezone.utc)
                    bot_user = f"@{info.get('username')}" if info.get('username') else "Bot"
                    return True, f"Test message delivered successfully by {bot_user}."
                else:
                    desc = data.get("description", resp.text)
                    return False, f"Telegram delivery failed ({resp.status_code}): {desc}"
        except Exception as e:
            return False, f"Network error sending test message: {str(e)}"


telegram_notifier = TelegramNotifier()
