from typing import Dict, Optional
import pandas as pd
from pydantic import BaseModel
from app.engine.indicators import compute_sma
from app.settings import settings


class RegimeResult(BaseModel):
    market: str
    status: str  # BULLISH, CAUTION, WEAK
    index_symbol: str
    last_close: float
    sma50: float
    sma200: float
    is_bullish: bool
    allows_entries: bool
    size_multiplier: float
    detail: str


def evaluate_market_regime(
    index_df: pd.DataFrame, market: str = "IN"
) -> RegimeResult:
    mkt_cfg = settings.get_market_config(market)
    regime_cfg = settings.strategy_config.get("regime", {})
    block_weak = regime_cfg.get("block_new_entries", True)
    caution_mult = float(regime_cfg.get("caution_size_mult", 0.5))

    if index_df is None or len(index_df) < 50:
        # Default fallback if index data not yet available
        return RegimeResult(
            market=market,
            status="BULLISH",
            index_symbol=mkt_cfg.index_symbol,
            last_close=24000.0 if market == "IN" else 5500.0,
            sma50=23500.0 if market == "IN" else 5400.0,
            sma200=22800.0 if market == "IN" else 5200.0,
            is_bullish=True,
            allows_entries=True,
            size_multiplier=1.0,
            detail="Default regime assessment (insufficient historical index bars)",
        )

    df = index_df.copy()
    close_series = df["close"]
    sma50_series = compute_sma(close_series, 50)
    sma200_series = compute_sma(close_series, 200)

    last_close = float(close_series.iloc[-1])
    sma50 = float(sma50_series.iloc[-1]) if pd.notna(sma50_series.iloc[-1]) else last_close
    sma200 = float(sma200_series.iloc[-1]) if pd.notna(sma200_series.iloc[-1]) else last_close

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

