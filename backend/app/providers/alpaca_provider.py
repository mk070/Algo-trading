import datetime
import logging
from typing import Dict, List, Optional
import httpx
import pandas as pd

from app.providers.base import MarketDataProvider, ProviderHealth, Quote
from app.settings import settings

logger = logging.getLogger(__name__)


class AlpacaProvider:
    """US Market Data Provider adapter (Alpaca candidate).
    Provides real-time US quotes and historical bars if configured.
    Explicitly uses Alpaca IEX data feed (representing ~2.5% of US consolidated volume).
    """

    name = "alpaca_iex"
    is_realtime = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        self.api_key = api_key or settings.alpaca_api_key
        self.secret_key = secret_key or settings.alpaca_secret_key
        self.endpoint = endpoint or settings.alpaca_endpoint
        self.data_url = "https://data.alpaca.markets/v2"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key or "",
            "APCA-API-SECRET-KEY": self.secret_key or "",
        }

    def daily_bars(
        self,
        symbols: List[str],
        start: datetime.date,
        end: datetime.date,
        adjustment: str = "split",
    ) -> Dict[str, pd.DataFrame]:
        results: Dict[str, pd.DataFrame] = {}
        if not self.is_configured() or not symbols:
            if not self.is_configured():
                logger.info("Alpaca credentials not configured. US live bars unavailable from Alpaca.")
            return results

        # Clean symbol list (handle BRK.B -> BRK/B for Alpaca API)
        alpaca_symbols = [s.replace(".B", "/B").replace(".A", "/A") for s in symbols]
        sym_reverse_map = {alpaca_sym: orig_sym for alpaca_sym, orig_sym in zip(alpaca_symbols, symbols)}

        url = f"{self.data_url}/stocks/bars"
        collected_bars: Dict[str, List[Dict]] = {s: [] for s in alpaca_symbols}
        page_token = None

        try:
            with httpx.Client(timeout=25.0) as client:
                while True:
                    params = {
                        "symbols": ",".join(alpaca_symbols),
                        "timeframe": "1Day",
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "feed": "iex",
                        "adjustment": adjustment,
                        "limit": 10000,
                    }
                    if page_token:
                        params["page_token"] = page_token

                    resp = client.get(url, headers=self._headers(), params=params)
                    if resp.status_code != 200:
                        logger.error(f"Alpaca API error {resp.status_code}: {resp.text}")
                        break

                    payload = resp.json()
                    bars_data = payload.get("bars", {})
                    for sym, bars in bars_data.items():
                        if sym in collected_bars:
                            collected_bars[sym].extend(bars)

                    page_token = payload.get("next_page_token")
                    if not page_token:
                        break

            for alpaca_sym, bars in collected_bars.items():
                orig_sym = sym_reverse_map.get(alpaca_sym, alpaca_sym)
                if bars:
                    df = pd.DataFrame(bars)
                    df = df.rename(
                        columns={
                            "t": "date",
                            "o": "open",
                            "h": "high",
                            "l": "low",
                            "c": "close",
                            "v": "volume",
                        }
                    )
                    df["date"] = pd.to_datetime(df["date"]).dt.date
                    df = df.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
                    if adjustment in ("split", "all"):
                        df["split_adj_open"] = df["open"]
                        df["split_adj_high"] = df["high"]
                        df["split_adj_low"] = df["low"]
                        df["split_adj_close"] = df["close"]
                        df["is_split_adjusted"] = True
                    else:
                        df["split_adj_open"] = df["open"]
                        df["split_adj_high"] = df["high"]
                        df["split_adj_low"] = df["low"]
                        df["split_adj_close"] = df["close"]
                        df["is_split_adjusted"] = False
                    df["adj_close"] = df["close"]
                    df["dividend_factor"] = 1.0
                    df["source"] = self.name
                    results[orig_sym] = df
        except Exception as e:
            logger.error(f"Alpaca daily bars error: {e}")

        return results

    def intraday_bars(
        self, symbols: List[str], interval: str = "15m", days: int = 5
    ) -> Dict[str, pd.DataFrame]:
        """Fetch US intraday bars (1m, 5m, 15m, 30m, 1h) from Alpaca IEX real-time feed."""
        results: Dict[str, pd.DataFrame] = {}
        if not self.is_configured() or not symbols:
            return results

        tf_map = {
            "1m": "1Min", "1min": "1Min", "one_minute": "1Min",
            "5m": "5Min", "5min": "5Min", "five_minute": "5Min",
            "15m": "15Min", "15min": "15Min", "fifteen_minute": "15Min",
            "30m": "30Min", "30min": "30Min", "thirty_minute": "30Min",
            "1h": "1Hour", "60m": "1Hour", "one_hour": "1Hour",
        }
        alpaca_tf = tf_map.get(interval.lower(), "15Min")

        end = datetime.datetime.now(datetime.timezone.utc)
        start = end - datetime.timedelta(days=days)
        symbols_str = ",".join(symbols)
        url = f"{self.data_url}/stocks/bars"
        params = {
            "symbols": symbols_str,
            "timeframe": alpaca_tf,
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": "iex",
            "limit": 1000,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                if resp.status_code == 200:
                    bars_data = resp.json().get("bars", {})
                    for sym, bars in bars_data.items():
                        df = pd.DataFrame(bars)
                        if not df.empty:
                            df = df.rename(
                                columns={
                                    "t": "timestamp",
                                    "o": "open",
                                    "h": "high",
                                    "l": "low",
                                    "c": "close",
                                    "v": "volume",
                                }
                            )
                            df["timestamp"] = pd.to_datetime(df["timestamp"])
                            df["adj_close"] = df["close"]
                            df["source"] = self.name
                            results[sym] = df
        except Exception as e:
            logger.error(f"Alpaca intraday bars error: {e}")

        return results

    def quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        quotes_dict: Dict[str, Quote] = {}
        if not self.is_configured():
            return quotes_dict

        url = f"{self.data_url}/stocks/snapshots"
        params = {"symbols": ",".join(symbols), "feed": "iex"}

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    now = datetime.datetime.utcnow()
                    for sym, snap in data.items():
                        trade = snap.get("latestTrade", {})
                        daily_bar = snap.get("dailyBar", {})
                        prev_bar = snap.get("prevDailyBar", {})
                        latest_quote = snap.get("latestQuote", {})

                        price = float(trade.get("p", 0.0))
                        if price <= 0:
                            price = float(daily_bar.get("c", 0.0)) or float(snap.get("minuteBar", {}).get("c", 0.0))

                        vol = float(daily_bar.get("v", 0.0))
                        open_p = float(daily_bar.get("o", price))
                        high_p = float(daily_bar.get("h", price))
                        low_p = float(daily_bar.get("l", price))
                        prev_close = float(prev_bar.get("c", 0.0)) or open_p

                        chg = round(price - prev_close, 2) if prev_close > 0 else 0.0
                        chg_pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0

                        bid_p = float(latest_quote.get("bp", 0.0)) or None
                        ask_p = float(latest_quote.get("ap", 0.0)) or None

                        quotes_dict[sym] = Quote(
                            symbol=sym,
                            last_price=price,
                            price=price,
                            day_volume=vol,
                            timestamp=now,
                            exchange_ts=now,
                            received_ts=now,
                            source=self.name,
                            provider=self.name,
                            is_realtime=True,
                            realtime=True,
                            is_stale=False,
                            open=open_p,
                            high=high_p,
                            low=low_p,
                            close=prev_close,
                            prev_close=prev_close,
                            change=chg,
                            change_pct=chg_pct,
                            bid=bid_p,
                            ask=ask_p,
                        )
        except Exception as e:
            logger.error(f"Alpaca quotes error: {e}")

        return quotes_dict

    def health(self) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth(
                name=self.name,
                status="NOT_CONFIGURED",
                is_realtime=True,
                message="Alpaca API credentials not configured in .env. US live signals are unavailable.",
            )
        return ProviderHealth(
            name=self.name,
            status="HEALTHY",
            is_realtime=True,
            message="Alpaca US market data provider configured.",
        )
