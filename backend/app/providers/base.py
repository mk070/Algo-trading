import datetime
from typing import Dict, List, Optional, Protocol, runtime_checkable
import pandas as pd
from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    last_price: float
    day_volume: float
    timestamp: datetime.datetime
    source: str  # angelone, alpaca, yfinance, mock
    is_realtime: bool = True
    is_stale: bool = False
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None


class ProviderHealth(BaseModel):
    name: str
    status: str  # HEALTHY, DEGRADED, DOWN, NOT_CONFIGURED
    is_realtime: bool = False
    message: str = ""
    latency_ms: Optional[float] = None
    last_check: datetime.datetime = datetime.datetime.utcnow()


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

