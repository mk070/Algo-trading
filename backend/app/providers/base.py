import datetime
from enum import Enum
from typing import Dict, List, Optional, Protocol, runtime_checkable
import pandas as pd
from pydantic import BaseModel


class QuoteFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    DELAYED = "DELAYED"
    UNAVAILABLE = "UNAVAILABLE"


class IneligibleQuoteError(ValueError):
    """Raised when an ineligible (stale, delayed, or non-realtime) quote enters the Decision Lane."""
    pass


class DecisionQuote(BaseModel):
    """Guaranteed FRESH + REALTIME quote strictly verified for decision-making & alert generation."""
    symbol: str
    market: str
    price: float
    provider: str
    exchange_ts: datetime.datetime
    received_ts: datetime.datetime
    freshness: QuoteFreshness = QuoteFreshness.FRESH
    realtime: bool = True
    day_volume: float = 0.0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None

    @property
    def last_price(self) -> float:
        return self.price

    @property
    def source(self) -> str:
        return self.provider

    @property
    def timestamp(self) -> datetime.datetime:
        return self.exchange_ts

    @property
    def is_realtime(self) -> bool:
        return self.realtime

    @property
    def is_stale(self) -> bool:
        return False

    @property
    def pct_change(self) -> float:
        ref = self.close or self.open
        if ref and ref > 0:
            return round(((self.price - ref) / ref) * 100.0, 2)
        return 0.0


class Quote(BaseModel):
    """Normalized Quote Model adhering to the two-lane contract.
    Decision Lane: requires freshness == FRESH and realtime == True via to_decision_quote().
    Display Lane: allows cached/stale/delayed quotes with visible UI tagging.
    """
    symbol: str
    market: str = "IN"
    price: float
    provider: str
    exchange_ts: datetime.datetime
    received_ts: datetime.datetime
    freshness: QuoteFreshness = QuoteFreshness.FRESH
    realtime: bool = True
    day_volume: float = 0.0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None

    # Redundant fields maintained for 100% backward compatibility
    last_price: float = 0.0
    source: str = ""
    timestamp: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
    is_realtime: bool = True
    is_stale: bool = False

    def __init__(self, **data):
        # 1. Resolve price / last_price
        p = data.get("price", data.get("last_price", 0.0))
        data["price"] = float(p)
        data["last_price"] = float(p)

        # 2. Resolve provider / source
        prov = data.get("provider", data.get("source", "unknown"))
        data["provider"] = str(prov)
        data["source"] = str(prov)

        # 3. Resolve timestamps
        ex_ts = data.get("exchange_ts", data.get("timestamp", datetime.datetime.now(datetime.timezone.utc)))
        rec_ts = data.get("received_ts", ex_ts)
        data["exchange_ts"] = ex_ts
        data["timestamp"] = ex_ts
        data["received_ts"] = rec_ts

        # 4. Resolve realtime
        rt = data.get("realtime", data.get("is_realtime", True))
        data["realtime"] = bool(rt)
        data["is_realtime"] = bool(rt)

        # 5. Resolve freshness / is_stale
        if "freshness" in data:
            f_val = data["freshness"]
            if isinstance(f_val, str):
                try:
                    f_val = QuoteFreshness(f_val.upper())
                except ValueError:
                    f_val = QuoteFreshness.STALE
            data["freshness"] = f_val
            data["is_stale"] = (f_val != QuoteFreshness.FRESH)
        else:
            is_st = data.get("is_stale", False)
            if is_st:
                data["freshness"] = QuoteFreshness.STALE
                data["is_stale"] = True
            elif not rt:
                data["freshness"] = QuoteFreshness.DELAYED
                data["is_stale"] = True
            else:
                data["freshness"] = QuoteFreshness.FRESH
                data["is_stale"] = False

        super().__init__(**data)

    @property
    def pct_change(self) -> float:
        ref = self.close or self.open
        if ref and ref > 0:
            return round(((self.price - ref) / ref) * 100.0, 2)
        return 0.0

    def to_decision_quote(self) -> DecisionQuote:
        """Type-safe boundary enforcement for the Decision Lane.
        Only verified FRESH quotes with realtime=True may reach strategy pipelines.
        """
        if self.freshness != QuoteFreshness.FRESH:
            raise IneligibleQuoteError(
                f"Quote for {self.symbol} has freshness '{self.freshness.value}'; strictly blocked from Decision Lane."
            )
        if not self.realtime:
            raise IneligibleQuoteError(
                f"Quote for {self.symbol} is not real-time (realtime={self.realtime}); strictly blocked from Decision Lane."
            )
        return DecisionQuote(
            symbol=self.symbol,
            market=self.market,
            price=self.price,
            provider=self.provider,
            exchange_ts=self.exchange_ts,
            received_ts=self.received_ts,
            freshness=self.freshness,
            realtime=self.realtime,
            day_volume=self.day_volume,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            bid=self.bid,
            ask=self.ask,
        )


class ProviderHealth(BaseModel):
    name: str
    status: str  # HEALTHY, DEGRADED, DOWN, NOT_CONFIGURED
    is_realtime: bool = False
    message: str = ""
    latency_ms: Optional[float] = None
    last_check: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
    success_rate: float = 1.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    circuit_state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    cooldown_until: Optional[str] = None
    last_error: Optional[str] = None


@runtime_checkable
class MarketDataProvider(Protocol):
    name: str
    is_realtime: bool

    def daily_bars(
        self, symbols: List[str], start: datetime.date, end: datetime.date
    ) -> Dict[str, pd.DataFrame]:
        ...

    def quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        ...

    def health(self) -> ProviderHealth:
        ...


@runtime_checkable
class PortfolioProvider(Protocol):
    name: str

    def profile(self) -> Dict:
        ...

    def funds(self) -> Dict:
        ...

    def holdings(self) -> List[Dict]:
        ...

    def positions(self) -> List[Dict]:
        ...

    def orders(self) -> List[Dict]:
        ...

    def trades(self) -> List[Dict]:
        ...

    def is_authenticated(self) -> bool:
        ...


def validate_candle_data(df: pd.DataFrame) -> List[str]:
    """Validate candle series: no negative/zero prices, high >= max(open, close), low <= min(open, close)."""
    warnings = []
    if df is None or df.empty:
        return ["Empty dataframe"]

    req_cols = ["open", "high", "low", "close", "volume"]
    missing = [c for c in req_cols if c not in df.columns]
    if missing:
        return [f"Missing required columns: {missing}"]

    if (df["open"] <= 0).any() or (df["close"] <= 0).any():
        warnings.append("Detected non-positive open/close prices")
    if (df["high"] < df["open"]).any() or (df["high"] < df["close"]).any():
        warnings.append("Detected invalid high price lower than open or close")
    if (df["low"] > df["open"]).any() or (df["low"] > df["close"]).any():
        warnings.append("Detected invalid low price higher than open or close")
    if (df["volume"] < 0).any():
        warnings.append("Detected negative volume")

    return warnings
