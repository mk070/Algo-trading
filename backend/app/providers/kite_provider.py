import csv
import datetime
import hashlib
import io
import json
import logging
from typing import Dict, List, Optional
import httpx

from app.providers.base import PortfolioProvider
from app.settings import settings

logger = logging.getLogger(__name__)


class KitePortfolioReader:
    """Strictly READ-ONLY client for Zerodha Kite Connect Personal.
    MANDATORY RULE: This class and module contain ONLY read endpoints.
    Never add order placement, modification, cancellation, position conversion or GTT mutation methods.
    """

    name = "kite_personal"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.api_key = api_key or settings.kite_api_key
        self.api_secret = api_secret or settings.kite_api_secret
        self.access_token = access_token or settings.kite_access_token
        self.base_url = "https://api.kite.trade"
        self.token_expiry: Optional[datetime.datetime] = None
        self.last_sync_time: Optional[datetime.datetime] = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _restore_session_from_db_if_needed(self):
        if not self.access_token:
            try:
                from app.db import SessionLocal
                from app.models import SettingKV
                with SessionLocal() as db:
                    row = db.query(SettingKV).filter(SettingKV.key == "kite_session").first()
                    if row and row.value_json:
                        data = json.loads(row.value_json)
                        exp_str = data.get("token_expiry")
                        if exp_str:
                            exp_dt = datetime.datetime.fromisoformat(exp_str)
                            if datetime.datetime.utcnow() < exp_dt:
                                self.access_token = data.get("access_token")
                                self.token_expiry = exp_dt
                                logger.info("Restored Kite session from database.")
            except Exception as e:
                logger.warning(f"Failed to restore Kite session from DB: {e}")

    def is_authenticated(self) -> bool:
        if not self.access_token:
            self._restore_session_from_db_if_needed()
        if not self.access_token:
            return False
        if self.token_expiry and datetime.datetime.utcnow() >= self.token_expiry:
            return False
        return True

    def get_login_url(self) -> str:
        """Returns the login URL for the 'Connect Zerodha' button."""
        if not self.api_key:
            return "https://kite.zerodha.com/connect/login?v=3"
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={self.api_key}"

    def exchange_request_token(self, request_token: str) -> Dict:
        """Exchanges Kite request_token for daily access_token using SHA-256 checksum."""
        if not self.api_key or not self.api_secret:
            raise ValueError("Kite API key and API secret must be configured to generate session.")

        checksum_str = f"{self.api_key}{request_token}{self.api_secret}"
        checksum = hashlib.sha256(checksum_str.encode("utf-8")).hexdigest()

        url = f"{self.base_url}/session/token"
        data = {
            "api_key": self.api_key,
            "request_token": request_token,
            "checksum": checksum,
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data=data)
            resp_data = resp.json()

            if resp.status_code == 200 and resp_data.get("status") == "success":
                session_data = resp_data["data"]
                self.access_token = session_data["access_token"]
                # Kite token expires at 06:00 IST the next morning (~24 hrs max)
                self.token_expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=20)
                logger.info("Successfully generated Kite access token for session.")
                return session_data
            else:
                error_msg = resp_data.get("message", "Session generation failed")
                logger.error(f"Failed to generate Kite session: {error_msg}")
                raise RuntimeError(error_msg)

    def _get_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise PermissionError("Kite access token missing or expired. Reconnect Zerodha.")
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}",
        }

    def _get(self, path: str) -> Dict:
        """Internal helper for strictly GET requests."""
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=self._get_headers())
            if resp.status_code == 403 or resp.status_code == 401:
                self.access_token = None
                raise PermissionError("Kite token expired or unauthorized. Please re-authenticate.")
            resp.raise_for_status()
            return resp.json().get("data", {})

    def profile(self) -> Dict:
        """GET /user/profile"""
        if not self.is_authenticated():
            return {
                "user_name": "Offline / Demo User",
                "user_id": "DEMO01",
                "email": "demo@example.com",
                "broker": "ZERODHA",
                "status": "NOT_CONNECTED",
            }
        try:
            return self._get("/user/profile")
        except Exception as e:
            logger.error(f"Error fetching Kite profile: {e}")
            return {"status": "ERROR", "message": str(e)}

    def funds(self) -> Dict:
        """GET /user/margins (equity segment)"""
        if not self.is_authenticated():
            return {
                "available_cash": 17500.0,
                "net": 17500.0,
                "collateral": 0.0,
                "utilized": 0.0,
                "source": "manual_fallback",
            }
        try:
            data = self._get("/user/margins/equity")
            return {
                "available_cash": float(data.get("available", {}).get("live_balance", 0.0)),
                "net": float(data.get("net", 0.0)),
                "collateral": float(data.get("available", {}).get("collateral", 0.0)),
                "utilized": float(data.get("utilised", {}).get("debits", 0.0)),
                "source": "kite_personal",
            }
        except Exception as e:
            logger.error(f"Error fetching Kite margins: {e}")
            return {"available_cash": 17500.0, "source": "error_fallback"}

    def holdings(self) -> List[Dict]:
        """GET /portfolio/holdings"""
        if not self.is_authenticated():
            # Return demo/mock portfolio holdings when not authenticated
            return [
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "quantity": 10,
                    "average_price": 2840.50,
                    "last_price": 2890.00,
                    "pnl": 495.0,
                    "source": "Zerodha (Mock/Demo)",
                },
                {
                    "tradingsymbol": "TCS",
                    "exchange": "NSE",
                    "quantity": 5,
                    "average_price": 3820.00,
                    "last_price": 3895.00,
                    "pnl": 375.0,
                    "source": "Zerodha (Mock/Demo)",
                },
            ]
        try:
            items = self._get("/portfolio/holdings")
            self.last_sync_time = datetime.datetime.utcnow()
            res = []
            for item in items:
                res.append(
                    {
                        "tradingsymbol": item.get("tradingsymbol"),
                        "exchange": item.get("exchange"),
                        "instrument_token": item.get("instrument_token"),
                        "quantity": int(item.get("quantity", 0)),
                        "average_price": float(item.get("average_price", 0.0)),
                        "last_price": float(item.get("last_price", 0.0)),
                        "pnl": float(item.get("pnl", 0.0)),
                        "close_price": float(item.get("close_price", 0.0)),
                        "source": "Zerodha",
                    }
                )
            return res
        except Exception as e:
            logger.error(f"Error fetching Kite holdings: {e}")
            return []

    def positions(self) -> List[Dict]:
        """GET /portfolio/positions (day and net)"""
        if not self.is_authenticated():
            return []
        try:
            data = self._get("/portfolio/positions")
            net_positions = data.get("net", [])
            res = []
            for p in net_positions:
                res.append(
                    {
                        "tradingsymbol": p.get("tradingsymbol"),
                        "exchange": p.get("exchange"),
                        "quantity": int(p.get("quantity", 0)),
                        "average_price": float(p.get("average_price", 0.0)),
                        "last_price": float(p.get("last_price", 0.0)),
                        "pnl": float(p.get("pnl", 0.0)),
                        "product": p.get("product"),
                        "source": "Zerodha",
                    }
                )
            return res
        except Exception as e:
            logger.error(f"Error fetching Kite positions: {e}")
            return []

    def orders(self) -> List[Dict]:
        """GET /orders"""
        if not self.is_authenticated():
            return []
        try:
            return self._get("/orders")
        except Exception as e:
            logger.error(f"Error fetching Kite orders: {e}")
            return []

    def trades(self) -> List[Dict]:
        """GET /trades"""
        if not self.is_authenticated():
            return []
        try:
            return self._get("/trades")
        except Exception as e:
            logger.error(f"Error fetching Kite trades: {e}")
            return []

    def status(self) -> Dict:
        return {
            "configured": self.is_configured(),
            "authenticated": self.is_authenticated(),
            "token_expiry": self.token_expiry.isoformat() if self.token_expiry else None,
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "provider": self.name,
            "access": "STRICTLY_READ_ONLY",
        }


def parse_zerodha_console_csv(file_content: str, kind: str) -> Dict:
    """Parses Zerodha Console CSV reports (Tradebook, P&L, Charges).
    Returns file hash, row count, and parsed trade items.
    """
    file_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()
    reader = csv.DictReader(io.StringIO(file_content))
    rows = list(reader)

    parsed_trades = []
    for r in rows:
        # Standard Zerodha Tradebook columns: Symbol, Trade Date, Trade Type, Quantity, Price
        sym = r.get("Symbol") or r.get("tradingsymbol") or r.get("Script")
        trade_date_str = r.get("Trade Date") or r.get("trade_date") or r.get("Date")
        side = r.get("Trade Type") or r.get("Type") or r.get("trade_type") or "BUY"
        qty_str = r.get("Quantity") or r.get("qty") or "0"
        price_str = r.get("Price") or r.get("price") or "0"

        if sym and trade_date_str:
            try:
                parsed_trades.append(
                    {
                        "symbol": sym.strip().upper(),
                        "side": side.strip().upper(),
                        "qty": int(float(qty_str)),
                        "price": float(price_str),
                        "trade_date": trade_date_str.strip(),
                        "raw": r,
                    }
                )
            except Exception:
                continue

    return {
        "file_hash": file_hash,
        "row_count": len(rows),
        "valid_trades_count": len(parsed_trades),
        "trades": parsed_trades,
        "kind": kind,
    }

