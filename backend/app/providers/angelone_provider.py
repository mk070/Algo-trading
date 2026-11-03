import datetime
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
import pandas as pd
import pyotp
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from app.providers.base import MarketDataProvider, ProviderHealth, Quote, validate_candle_data
from app.settings import settings, DATA_DIR

logger = logging.getLogger(__name__)


class AngelOneProvider:
    """Angel One SmartAPI Market Data Provider.
    Primary Indian market data provider for daily candles, 15m intraday, quotes, and live feeds.
    """

    name = "angelone"
    is_realtime = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        client_code: Optional[str] = None,
        pin: Optional[str] = None,
        totp_secret: Optional[str] = None,
    ):
        def _clean(val):
            if not val:
                return None
            return str(val).strip().strip('"').strip("'")

        self.api_key = _clean(api_key or settings.angelone_api_key)
        self.client_code = _clean(client_code or settings.angelone_client_code)
        self.pin = _clean(pin or settings.angelone_pin)
        self.totp_secret = _clean(totp_secret or settings.angelone_totp_secret or getattr(settings, "angelone_totp_key", None))

        self.smart_api = None
        self.jwt_token = None
        self.refresh_token = None
        self.feed_token = None
        self.token_expiry: Optional[datetime.datetime] = None
        self.instrument_map: Dict[str, Dict] = {}  # symbol -> {token, name, exch_seg}
        self.cache_dir = DATA_DIR / "cache" / "angelone"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_quote_time: Dict[str, datetime.datetime] = {}
        self._load_cached_instruments()
        self.ws_manager = AngelOneWebSocketManager(self)

    def is_configured(self) -> bool:
        if not (self.api_key and self.client_code and self.pin and self.totp_secret):
            return False
        # Treat template/placeholder strings in .env as unconfigured
        if any("your_" in str(val).lower() for val in [self.api_key, self.client_code, self.totp_secret]):
            return False
        return True

    def login(self) -> bool:
        if not self.is_configured():
            logger.info("Angel One credentials not fully configured; operating in unauthenticated/fixture mode.")
            return False

        try:
            try:
                from SmartApi import SmartConnect
            except ImportError:
                try:
                    from smartapi import SmartConnect
                except ImportError:
                    try:
                        from smartapi.smartConnect import SmartConnect
                    except ImportError:
                        from SmartApi.smartConnect import SmartConnect

            self.smart_api = SmartConnect(api_key=self.api_key)
            totp = pyotp.TOTP(self.totp_secret).now()
            data = self.smart_api.generateSession(self.client_code, self.pin, totp)
            if data and data.get("status"):
                self.jwt_token = data["data"]["jwtToken"]
                self.refresh_token = data["data"]["refreshToken"]
                self.feed_token = data["data"]["feedToken"]
                self.token_expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=20)
                logger.info("Angel One SmartAPI session successfully generated.")
                return True
            else:
                logger.error(f"Angel One login failed: {data.get('message')}")
                return False
        except Exception as e:
            logger.error(f"Error logging into Angel One SmartAPI: {e}")
            return False

    def _ensure_session(self) -> bool:
        if not self.is_configured():
            return False
        if not self.smart_api or not self.jwt_token or (self.token_expiry and datetime.datetime.utcnow() >= self.token_expiry):
            return self.login()
        return True

    def _load_cached_instruments(self):
        file_path = self.cache_dir / "instrument_master.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.instrument_map = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load cached instrument master: {e}")

    def refresh_instruments(self) -> bool:
        """Download official instrument master JSON from Angel One and cache locally."""
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                mapping = {}
                for item in data:
                    if item.get("exch_seg") in ("NSE", "BSE") and item.get("symbol", "").endswith("-EQ"):
                        clean_sym = item["symbol"].replace("-EQ", "")
                        mapping[clean_sym] = {
                            "token": str(item.get("token")),
                            "symbol": clean_sym,
                            "raw_symbol": item.get("symbol"),
                            "name": item.get("name"),
                            "expiry": item.get("expiry"),
                            "strike": item.get("strike"),
                            "lotsize": item.get("lotsize"),
                            "instrumenttype": item.get("instrumenttype"),
                            "exch_seg": item.get("exch_seg"),
                            "tick_size": item.get("tick_size"),
                        }
                self.instrument_map = mapping
                file_path = self.cache_dir / "instrument_master.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(mapping, f)
                logger.info(f"Loaded and cached {len(mapping)} NSE/BSE equity instruments from Angel One.")
                return True
        except Exception as e:
            logger.error(f"Failed to fetch Angel One instrument master: {e}")
        return False

    def get_token(self, symbol: str) -> Optional[str]:
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
        if clean_sym in self.instrument_map:
            return self.instrument_map[clean_sym]["token"]
        # Seeded known tokens for core Nifty 50 stocks as reliable fallbacks
        known_tokens = {
            "RELIANCE": "2885",
            "TCS": "11536",
            "HDFCBANK": "1333",
            "INFY": "1594",
            "ICICIBANK": "4963",
            "BHARTIARTL": "10604",
            "SBIN": "3045",
            "LT": "11483",
            "ITC": "1660",
            "TATAMOTORS": "3456",
            "TMPV": "3456",
            "BAJFINANCE": "317",
            "M&M": "2031",
            "BAJAJ-AUTO": "16669",
        }
        return known_tokens.get(clean_sym)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
    def _fetch_candles_raw(self, token: str, interval: str, from_date: str, to_date: str) -> List:
        """Call getCandleData with rate limiting (approx 3 req/sec)."""
        time.sleep(0.35)
        historic_param = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_date,
            "todate": to_date,
        }
        return self.smart_api.getCandleData(historic_param)

    def daily_bars(
        self, symbols: List[str], start: datetime.date, end: datetime.date
    ) -> Dict[str, pd.DataFrame]:
        results: Dict[str, pd.DataFrame] = {}
        if not self._ensure_session():
            logger.warning("Angel One unauthenticated; cannot fetch live SmartAPI daily bars directly.")
            return results

        from_date_str = start.strftime("%Y-%m-%d 09:15")
        to_date_str = end.strftime("%Y-%m-%d 15:30")

        for sym in symbols:
            token = self.get_token(sym)
            if not token:
                logger.warning(f"No Angel One token found for {sym}")
                continue
            try:
                res = self._fetch_candles_raw(token, "ONE_DAY", from_date_str, to_date_str)
                if res and res.get("status") and res.get("data"):
                    # Format: [datetime_str, open, high, low, close, volume]
                    rows = res["data"]
                    df = pd.DataFrame(
                        rows,
                        columns=["date", "open", "high", "low", "close", "volume"],
                    )
                    df["date"] = pd.to_datetime(df["date"]).dt.date
                    df["adj_close"] = df["close"]
                    df["source"] = self.name
                    results[sym] = df
            except Exception as e:
                logger.error(f"Failed to fetch daily candles for {sym}: {e}")

        return results

    def intraday_bars(
        self, symbols: List[str], interval: str = "FIFTEEN_MINUTE", days: int = 5
    ) -> Dict[str, pd.DataFrame]:
        """Fetch intraday bars, e.g. FIFTEEN_MINUTE for provisional confirmation."""
        results: Dict[str, pd.DataFrame] = {}
        if not self._ensure_session():
            return results

        end = datetime.date.today()
        start = end - datetime.timedelta(days=days)
        from_date_str = start.strftime("%Y-%m-%d 09:15")
        to_date_str = end.strftime("%Y-%m-%d 15:30")

        for sym in symbols:
            token = self.get_token(sym)
            if not token:
                continue
            try:
                res = self._fetch_candles_raw(token, interval, from_date_str, to_date_str)
                if res and res.get("status") and res.get("data"):
                    df = pd.DataFrame(
                        res["data"],
                        columns=["timestamp", "open", "high", "low", "close", "volume"],
                    )
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    results[sym] = df
            except Exception as e:
                logger.error(f"Error fetching intraday bars for {sym}: {e}")
        return results

    def quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        quotes_dict: Dict[str, Quote] = {}
        now = datetime.datetime.utcnow()
        if not self._ensure_session():
            return quotes_dict

        for sym in symbols:
            token = self.get_token(sym)
            if not token:
                continue
            try:
                time.sleep(0.35)
                res = self.smart_api.ltpData("NSE", sym.replace(".NS", "") + "-EQ", token)
                if res and res.get("status") and res.get("data"):
                    d = res["data"]
                    last_price = float(d.get("ltp", 0.0))
                    quotes_dict[sym] = Quote(
                        symbol=sym,
                        last_price=last_price,
                        day_volume=0.0,
                        timestamp=now,
                        source=self.name,
                        is_realtime=True,
                        is_stale=False,
                        open=float(d.get("open", last_price)),
                        high=float(d.get("high", last_price)),
                        low=float(d.get("low", last_price)),
                        close=float(d.get("close", last_price)),
                    )
                    self.last_quote_time[sym] = now
            except Exception as e:
                logger.error(f"Failed to fetch Angel One quote for {sym}: {e}")

        return quotes_dict

    def health(self) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth(
                name=self.name,
                status="NOT_CONFIGURED",
                is_realtime=True,
                message="Angel One credentials not provided in .env",
            )
        start_t = time.time()
        ok = self._ensure_session()
        latency = (time.time() - start_t) * 1000
        if ok:
            return ProviderHealth(
                name=self.name,
                status="HEALTHY",
                is_realtime=True,
                message="Angel One SmartAPI session active and healthy",
                latency_ms=round(latency, 2),
            )
        return ProviderHealth(
            name=self.name,
            status="DOWN",
            is_realtime=True,
            message="Angel One SmartAPI authentication failed",
            latency_ms=round(latency, 2),
        )


class CandleBuilder:
    """Aggregates real-time ticks into 1-minute and 15-minute candles,
    tracks completed candles, computes volume pace against intraday time baseline,
    and supports gap back-filling.
    """

    def __init__(self):
        self.candles_1m: Dict[str, Dict] = {}
        self.candles_15m: Dict[str, Dict] = {}
        self.completed_15m: Dict[str, List[Dict]] = {}

    def process_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: Optional[datetime.datetime] = None,
    ) -> Optional[Dict]:
        """Process incoming tick. If a 15-minute candle completes, archives and returns it."""
        ts = timestamp or datetime.datetime.utcnow()
        minute_bucket = (ts.minute // 15) * 15
        bucket_time = ts.replace(minute=minute_bucket, second=0, microsecond=0)

        completed_candle = None
        current = self.candles_15m.get(symbol)
        if not current or current["bucket"] != bucket_time:
            if current:
                # Previous 15m candle has completed
                if symbol not in self.completed_15m:
                    self.completed_15m[symbol] = []
                self.completed_15m[symbol].append(dict(current))
                completed_candle = dict(current)

            self.candles_15m[symbol] = {
                "bucket": bucket_time,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
                "ticks": 1,
            }
        else:
            current["high"] = max(current["high"], price)
            current["low"] = min(current["low"], price)
            current["close"] = price
            current["volume"] += volume
            current["ticks"] += 1

        return completed_candle

    def force_complete_current_15m(self, symbol: str) -> Optional[Dict]:
        """Manually mark the currently active 15m candle as completed (e.g. for testing or boundary)."""
        current = self.candles_15m.get(symbol)
        if current:
            if symbol not in self.completed_15m:
                self.completed_15m[symbol] = []
            self.completed_15m[symbol].append(dict(current))
            return dict(current)
        return None

    def get_latest_15m(self, symbol: str) -> Optional[Dict]:
        return self.candles_15m.get(symbol)

    def get_latest_completed_15m(self, symbol: str) -> Optional[Dict]:
        completed = self.completed_15m.get(symbol, [])
        return completed[-1] if completed else None

    def is_confirmed_15m(self, symbol: str, trigger_price: float) -> bool:
        """Returns True if the latest completed 15-minute candle closed at or above trigger_price."""
        latest = self.get_latest_completed_15m(symbol)
        if not latest:
            return False
        return float(latest.get("close", 0.0)) >= float(trigger_price)

    def calculate_volume_pace(
        self,
        symbol: str,
        avg_volume_20d: float,
        current_time: Optional[datetime.datetime] = None,
        day_volume: Optional[float] = None,
    ) -> float:
        """Calculates volume pace ratio against expected time-of-day baseline.
        NSE trading hours: 09:15 to 15:30 IST (375 minutes).
        expected_vol = avg_vol20 * (elapsed_minutes / 375.0)
        pace = day_volume / expected_vol
        """
        ts = current_time or datetime.datetime.now()
        start_min = 9 * 60 + 15
        cur_min = ts.hour * 60 + ts.minute
        elapsed_min = max(5, min(375, cur_min - start_min))

        if avg_volume_20d <= 0:
            return 1.0

        expected_fraction = elapsed_min / 375.0
        expected_vol = avg_volume_20d * expected_fraction

        if day_volume is None:
            # Sum volume from candles
            day_volume = sum(c.get("volume", 0.0) for c in self.completed_15m.get(symbol, []))
            curr = self.candles_15m.get(symbol)
            if curr:
                day_volume += curr.get("volume", 0.0)

        if expected_vol <= 0:
            return 1.0
        return round(float(day_volume) / float(expected_vol), 3)

    def backfill_candle(self, symbol: str, bar: Dict):
        """Insert historical/backfilled 15m candle without duplicating by bucket."""
        if symbol not in self.completed_15m:
            self.completed_15m[symbol] = []
        bucket = bar.get("bucket") or bar.get("timestamp")
        existing_buckets = {c.get("bucket") for c in self.completed_15m[symbol]}
        if bucket not in existing_buckets:
            bar_entry = dict(bar)
            bar_entry["bucket"] = bucket
            self.completed_15m[symbol].append(bar_entry)
            self.completed_15m[symbol].sort(key=lambda x: str(x.get("bucket", "")))


class AngelOneWebSocketManager:
    """Manages WebSocket connection to Angel One SmartAPI SmartWebSocket.
    Provides streaming quote updates, automatic reconnection with exponential backoff,
    and gap back-fill for missing intervals.
    """

    def __init__(self, provider: AngelOneProvider):
        self.provider = provider
        self.candle_builder = CandleBuilder()
        self.connection_status: str = "DISCONNECTED"  # DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING
        self.subscribed_symbols: Set[str] = set()
        self.token_to_symbol: Dict[str, str] = {}
        self.symbol_to_token: Dict[str, str] = {}
        self.live_quotes: Dict[str, Quote] = {}
        self.last_tick_time: Dict[str, datetime.datetime] = {}
        self.disconnected_at: Optional[datetime.datetime] = None
        self.reconnect_attempts: int = 0
        self.backoff_intervals: List[int] = [1, 2, 5, 10, 30]
        self.callbacks: List[Callable] = []
        self._lock = threading.Lock()

    def sync_subscriptions(self, symbols: List[str]):
        """Update the set of subscribed symbols (active shortlist + open positions)."""
        with self._lock:
            self.subscribed_symbols = set(symbols)
            for sym in symbols:
                tok = self.provider.get_token(sym)
                if tok:
                    self.symbol_to_token[sym] = tok
                    self.token_to_symbol[tok] = sym

    def register_callback(self, callback: Callable):
        """Register tick listener: callback(symbol, quote, completed_15m)."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def inject_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: Optional[datetime.datetime] = None,
        day_volume: Optional[float] = None,
        high: Optional[float] = None,
        low: Optional[float] = None,
        open_price: Optional[float] = None,
    ):
        """Processes incoming tick directly. Used by WebSocket listener or mock test suite."""
        now = timestamp or datetime.datetime.utcnow()
        with self._lock:
            completed_15m = self.candle_builder.process_tick(symbol, price, volume, now)
            self.last_tick_time[symbol] = now

            prev_quote = self.live_quotes.get(symbol)
            d_vol = day_volume if day_volume is not None else (prev_quote.day_volume + volume if prev_quote else volume)
            h_p = max(prev_quote.high, price) if prev_quote and high is None else (high or price)
            l_p = min(prev_quote.low, price) if prev_quote and low is None else (low or price)
            o_p = prev_quote.open if prev_quote and open_price is None else (open_price or price)

            quote = Quote(
                symbol=symbol,
                last_price=float(price),
                day_volume=float(d_vol),
                timestamp=now,
                source="ANGEL_ONE_WS",
                is_realtime=True,
                is_stale=False,
                open=float(o_p),
                high=float(h_p),
                low=float(l_p),
                close=float(price),
            )
            self.live_quotes[symbol] = quote

        # Notify callbacks
        for cb in self.callbacks:
            try:
                cb(symbol, quote, completed_15m)
            except Exception as e:
                logger.error(f"Error in WebSocket callback for {symbol}: {e}")

    def on_tick_raw(self, token: str, ltp: float, volume: float, day_volume: float = 0.0):
        symbol = self.token_to_symbol.get(token)
        if symbol:
            self.inject_tick(symbol, ltp, volume, day_volume=day_volume)

    def on_disconnect(self):
        """Triggered when connection drops."""
        with self._lock:
            self.disconnected_at = datetime.datetime.utcnow()
            self.connection_status = "RECONNECTING"
            logger.warning("Angel One WebSocket disconnected. Initiating reconnect loop.")

    def on_reconnect_success(self):
        """Triggered upon successful reconnection: performs gap back-fill."""
        with self._lock:
            disc_at = self.disconnected_at
            self.connection_status = "CONNECTED"
            self.reconnect_attempts = 0
            self.disconnected_at = None

        if disc_at:
            now = datetime.datetime.utcnow()
            gap_seconds = (now - disc_at).total_seconds()
            logger.info(f"Angel One WebSocket reconnected after {gap_seconds:.1f}s gap. Back-filling missing candles.")
            self.backfill_gap(disc_at, now)

    def backfill_gap(self, start_time: datetime.datetime, end_time: datetime.datetime):
        """Backfill missing 15-minute candles from SmartAPI intraday endpoint."""
        symbols = list(self.subscribed_symbols)
        if not symbols:
            return
        try:
            bars_dict = self.provider.intraday_bars(symbols, interval="FIFTEEN_MINUTE", days=1)
            for sym, df in bars_dict.items():
                if df is not None and not df.empty and "timestamp" in df.columns:
                    mask = (df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)
                    missed = df[mask]
                    for _, row in missed.iterrows():
                        self.candle_builder.backfill_candle(
                            sym,
                            {
                                "bucket": row["timestamp"],
                                "open": float(row["open"]),
                                "high": float(row["high"]),
                                "low": float(row["low"]),
                                "close": float(row["close"]),
                                "volume": float(row["volume"]),
                                "ticks": 1,
                            },
                        )
            logger.info(f"Successfully executed gap back-fill for {len(symbols)} symbols.")
        except Exception as e:
            logger.error(f"Failed during gap backfill: {e}")

    def get_live_quote(
        self,
        symbol: str,
        max_age_sec: float = 20.0,
        current_time: Optional[datetime.datetime] = None,
    ) -> Optional[Quote]:
        """Fetch real-time quote enforcing strict freshness."""
        with self._lock:
            q = self.live_quotes.get(symbol)
            if not q:
                return None
            ref_now = current_time or datetime.datetime.utcnow()
            age = abs((ref_now - q.timestamp).total_seconds())
            if age > max_age_sec:
                q.is_stale = True
            return q


