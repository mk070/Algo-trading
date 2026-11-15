import datetime
import math
from typing import Dict, Optional
import pandas as pd
from pydantic import BaseModel
from app.engine.calendars import get_expected_trading_days
from app.engine.indicators import compute_sma
from app.settings import settings


class RegimeResult(BaseModel):
    market: str
    status: str  # BULLISH, CAUTION, WEAK, UNKNOWN
    index_symbol: str
    last_close: float
    sma50: float
    sma200: float
    is_bullish: bool
    allows_entries: bool
    size_multiplier: float
    detail: str


def evaluate_market_regime(
    index_df: pd.DataFrame,
    market: str = "IN",
    asof_date: Optional[datetime.date] = None,
) -> RegimeResult:
    mkt_cfg = settings.get_market_config(market)
    regime_cfg = settings.strategy_config.get("regime", {})
    block_weak = regime_cfg.get("block_new_entries", True)
    caution_mult = float(regime_cfg.get("caution_size_mult", 0.5))
    ref_d = asof_date or datetime.date.today()

    # Rule 6 & 11: Fail loudly on missing or insufficient data
    if index_df is None or len(index_df) < 200:
        bars_count = len(index_df) if index_df is not None else 0
        return RegimeResult(
            market=market,
            status="UNKNOWN",
            index_symbol=mkt_cfg.index_symbol,
            last_close=0.0,
            sma50=0.0,
            sma200=0.0,
            is_bullish=False,
            allows_entries=False,
            size_multiplier=0.0,
            detail=f"Insufficient index history ({bars_count} bars < 200 required). New entries withheld.",
        )

    df = index_df.copy()
    close_series = df["close"]

    # Freshness check: last bar date must not lag expected trading sessions
    last_bar_d: Optional[datetime.date] = None
    if isinstance(df.index, pd.DatetimeIndex):
        last_bar_d = df.index[-1].date()
    elif "date" in df.columns:
        last_val = df["date"].iloc[-1]
        last_bar_d = last_val.date() if isinstance(last_val, (datetime.datetime, pd.Timestamp)) else datetime.date.fromisoformat(str(last_val)[:10])

    if last_bar_d is not None and last_bar_d < ref_d:
        expected_days = get_expected_trading_days(market, last_bar_d, ref_d)
        # If there are 2 or more expected open trading days between last bar and ref_d, data is stale
        if len(expected_days) > 2:
            return RegimeResult(
                market=market,
                status="UNKNOWN",
                index_symbol=mkt_cfg.index_symbol,
                last_close=float(close_series.iloc[-1]) if pd.notna(close_series.iloc[-1]) else 0.0,
                sma50=0.0,
                sma200=0.0,
                is_bullish=False,
                allows_entries=False,
                size_multiplier=0.0,
                detail=f"Stale index data: last bar date {last_bar_d} lags reference date {ref_d} by {len(expected_days) - 1} trading sessions. New entries withheld.",
            )

    sma50_series = df["sma50"] if "sma50" in df.columns else compute_sma(close_series, 50)
    sma200_series = df["sma200"] if "sma200" in df.columns else compute_sma(close_series, 200)

    last_close = float(close_series.iloc[-1])
    sma50 = float(sma50_series.iloc[-1]) if pd.notna(sma50_series.iloc[-1]) else float("nan")
    sma200 = float(sma200_series.iloc[-1]) if pd.notna(sma200_series.iloc[-1]) else float("nan")

    # Validate finite float values
    if not (math.isfinite(last_close) and math.isfinite(sma50) and math.isfinite(sma200) and last_close > 0 and sma50 > 0 and sma200 > 0):
        return RegimeResult(
            market=market,
            status="UNKNOWN",
            index_symbol=mkt_cfg.index_symbol,
            last_close=last_close if math.isfinite(last_close) else 0.0,
            sma50=0.0,
            sma200=0.0,
            is_bullish=False,
            allows_entries=False,
            size_multiplier=0.0,
            detail="Invalid or non-finite moving average values calculated for market index. New entries withheld.",
        )

    if last_close > sma200 and last_close > sma50:
        status = "BULLISH"
        allows = True
        mult = 1.0
        detail = f"Index {last_close:.2f} is above SMA50 ({sma50:.2f}) and SMA200 ({sma200:.2f})"
    elif last_close > sma200 and last_close <= sma50:
        status = "CAUTION"
        allows = True
        mult = caution_mult
        detail = f"Index {last_close:.2f} is above SMA200 ({sma200:.2f}) but below SMA50 ({sma50:.2f})"
    else:
        status = "WEAK"
        allows = not block_weak
        mult = 0.0 if block_weak else 0.5
        detail = f"Index {last_close:.2f} is below SMA200 ({sma200:.2f}). Weak market regime."

    return RegimeResult(
        market=market,
        status=status,
        index_symbol=mkt_cfg.index_symbol,
        last_close=round(last_close, 2),
        sma50=round(sma50, 2),
        sma200=round(sma200, 2),
        is_bullish=(status == "BULLISH"),
        allows_entries=allows,
        size_multiplier=mult,
        detail=detail,
    )

