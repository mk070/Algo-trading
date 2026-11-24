"""Strategy Lab — Signal Engine.

Implements all 10 swing strategies as pure, side-effect-free signal functions.
Each function takes an enriched bar DataFrame and returns a boolean Series
(True = signal on that bar, buy next-day open).

All signals use ONLY past data (index i uses rows 0..i inclusive after enrichment).
No look-ahead bias. No live data fetch. All data must be pre-enriched with
add_all_indicators() before calling any signal function.

COST MODEL: Exact Zerodha delivery costs — same as cycle4_paper.py.
SLIPPAGE: 0.10% one-way on fill price (10 bps).
STOP: computed per strategy, documented in docstring.
EXIT: Time-based at holding_days or stop-hit (whichever comes first).
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.engine.indicators import (
    add_all_indicators,
    compute_ema,
    compute_rsi_wilder,
    compute_sma,
    compute_atr_wilder,
)

logger = logging.getLogger(__name__)

SLIPPAGE_PCT = 0.0010   # 10 bps one-way
MIN_TRADE_BARS = 30     # minimum bars for any strategy to run

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _bbands(close: pd.Series, length: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, mid, lower) Bollinger Bands."""
    mid = close.rolling(length, min_periods=length).mean()
    std = close.rolling(length, min_periods=length).std(ddof=1)
    return mid + std_dev * std, mid, mid - std_dev * std


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all standard indicators are present."""
    if "atr14" not in df.columns or "sma50" not in df.columns:
        df = add_all_indicators(df)
    return df


# ---------------------------------------------------------------------------
# S01 — Trend Pullback to 20 EMA (RSI14 turn)
# ---------------------------------------------------------------------------

def signal_s01(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Uptrend (above SMA50 & SMA200). Price touches/pierces EMA20 within
    touch_tolerance_pct%. RSI14 dipped below rsi_dip_below on the previous bar
    and has now risen (hook). Signal = True on bar i; entry at open of bar i+1.
    Stop = close_i - stop_atr_mult * ATR14_i.
    """
    df = _enrich(df)
    ema_len = int(params.get("ema_len", 20))
    rsi_len = int(params.get("rsi_len", 14))
    rsi_dip = float(params.get("rsi_dip_below", 45.0))
    tol = float(params.get("touch_tolerance_pct", 2.0)) / 100.0

    close = df["close"]
    ema = compute_ema(close, ema_len)
    rsi = compute_rsi_wilder(close, rsi_len)
    sma50 = compute_sma(close, 50)
    sma200 = compute_sma(close, 200)

    uptrend = (close > sma50) & (close > sma200)
    touch = (close >= ema * (1 - tol)) & (close <= ema * (1 + tol))
    rsi_hook = (rsi.shift(1) < rsi_dip) & (rsi > rsi.shift(1))

    return uptrend & touch & rsi_hook


# ---------------------------------------------------------------------------
# S02 — Donchian-20 Breakout + Volume
# ---------------------------------------------------------------------------

def signal_s02(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Price > 20-day Donchian high (previous 20 bars, NOT including current bar).
    Volume >= vol_multiplier * avg_vol20. Stock above SMA50.
    Signal on bar i; entry at open of i+1.
    Stop = Donchian low of same period.
    """
    df = _enrich(df)
    don_len = int(params.get("donchian_len", 20))
    vol_mult = float(params.get("vol_multiplier", 1.5))

    close = df["close"]
    high = df["high"]
    vol = df["volume"]
    avg_vol = vol.rolling(20, min_periods=20).mean()

    # Use shift(1) for Donchian to avoid look-ahead: channel built from prior bars
    don_high = high.shift(1).rolling(don_len, min_periods=don_len).max()
    don_low = df["low"].shift(1).rolling(don_len, min_periods=don_len).min()

    sma50 = compute_sma(close, 50)

    breakout = close > don_high
    vol_ok = vol >= vol_mult * avg_vol
    trend_ok = close > sma50

    return breakout & vol_ok & trend_ok


# ---------------------------------------------------------------------------
# S03 — 55-Day-High Breakout (Control)
# ---------------------------------------------------------------------------

def signal_s03(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Price breaks above the 55-day high (prior bars only). Volume >= 1.3x avg-20.
    Above SMA50 and SMA200.
    Signal on bar i; entry at open of i+1.
    Stop = 55-day low.
    """
    df = _enrich(df)
    lb = int(params.get("lookback", 55))
    vol_mult = float(params.get("vol_multiplier", 1.3))

    close = df["close"]
    high = df["high"]
    vol = df["volume"]
    avg_vol = vol.rolling(20, min_periods=20).mean()

    high55 = high.shift(1).rolling(lb, min_periods=lb).max()
    sma50 = compute_sma(close, 50)
    sma200 = compute_sma(close, 200)

    breakout = close > high55
    vol_ok = vol >= vol_mult * avg_vol
    trend_ok = (close > sma50) & (close > sma200)

    return breakout & vol_ok & trend_ok


# ---------------------------------------------------------------------------
# S04 — RSI(2) Dip in Uptrend
# ---------------------------------------------------------------------------

def signal_s04(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    RSI(2) drops below rsi_oversold (default 10) while price is above SMA200.
    Pure time exit model — no stop calculated here (stop set to NaN; engine
    treats this as time-only exit).
    Signal on bar i; entry at open of i+1.
    """
    df = _enrich(df)
    rsi_len = int(params.get("rsi_len", 2))
    oversold = float(params.get("rsi_oversold", 10.0))

    close = df["close"]
    rsi2 = compute_rsi_wilder(close, rsi_len)
    sma200 = compute_sma(close, 200)

    return (rsi2 < oversold) & (close > sma200)


# ---------------------------------------------------------------------------
# S05 — Three Down Closes in Uptrend
# ---------------------------------------------------------------------------

def signal_s05(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Three consecutive lower closes (close[i] < close[i-1] for 3 bars).
    Above SMA50 and SMA200.
    Signal on bar i; entry at open of i+1.
    Stop = low[i] - stop_atr_mult * ATR14[i].
    """
    df = _enrich(df)
    n = int(params.get("consecutive_down", 3))
    close = df["close"]
    sma50 = compute_sma(close, 50)
    sma200 = compute_sma(close, 200)

    # n consecutive down closes
    down = close < close.shift(1)
    consec_down = down.copy().astype(int)
    for k in range(1, n):
        consec_down = consec_down & (close.shift(k) < close.shift(k + 1))

    trend = (close > sma50) & (close > sma200)
    return consec_down & trend


# ---------------------------------------------------------------------------
# S06 — Bollinger Lower-Band Reclaim
# ---------------------------------------------------------------------------

def signal_s06(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Previous bar touched or breached the lower Bollinger Band (20, 2σ).
    Current bar closes back above lower band (reclaim).
    Above SMA200.
    Signal on bar i; entry at open of i+1.
    Stop = low[i] - stop_atr_mult * ATR14[i].
    """
    df = _enrich(df)
    bb_len = int(params.get("bb_len", 20))
    bb_std = float(params.get("bb_std", 2.0))

    close = df["close"]
    low = df["low"]
    sma200 = compute_sma(close, 200)
    _, _, lower = _bbands(close, bb_len, bb_std)

    touched = low.shift(1) <= lower.shift(1)   # prior bar touched lower band
    reclaim = close > lower                     # current bar above lower band
    trend = close > sma200

    return touched & reclaim & trend


# ---------------------------------------------------------------------------
# S07 — Gap-Up + Volume Pivot
# ---------------------------------------------------------------------------

def signal_s07(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Open gaps up >= min_gap_pct% above prior close.
    Volume >= vol_multiplier * avg_vol20.
    Above SMA50.
    Signal on bar i (using open vs prior close); entry at open of i+1.
    Stop = low[i-1] (prior-day low).
    """
    df = _enrich(df)
    min_gap = float(params.get("min_gap_pct", 2.0)) / 100.0
    vol_mult = float(params.get("vol_multiplier", 2.0))

    open_ = df["open"]
    close = df["close"]
    vol = df["volume"]
    avg_vol = vol.rolling(20, min_periods=20).mean()
    sma50 = compute_sma(close, 50)

    gap_up = (open_ / close.shift(1) - 1) >= min_gap
    vol_ok = vol >= vol_mult * avg_vol
    trend_ok = close > sma50

    return gap_up & vol_ok & trend_ok


# ---------------------------------------------------------------------------
# S08 — 52-Week-High Breakout with Relative Strength
# ---------------------------------------------------------------------------

def signal_s08_universe(
    bars_dict: Dict[str, pd.DataFrame],
    params: Dict[str, Any],
    target_symbol: str,
) -> pd.Series:
    """
    Returns signal series for target_symbol.
    RS percentile computed cross-sectionally across the universe for the
    63-day return on each bar date — requires all bars_dict for ranking.
    """
    lb = int(params.get("lookback_days", 252))
    rs_lb = int(params.get("rs_lookback_days", 63))
    rs_min_pct = float(params.get("rs_min_percentile", 0.70))
    vol_mult = float(params.get("vol_multiplier", 1.3))

    tgt = bars_dict.get(target_symbol)
    if tgt is None:
        return pd.Series(dtype=bool)

    tgt = _enrich(tgt).copy()
    close = tgt["close"]
    high = tgt["high"]
    vol = tgt["volume"]
    avg_vol = vol.rolling(20, min_periods=20).mean()

    high52 = high.shift(1).rolling(lb, min_periods=lb).max()
    breakout = close > high52
    vol_ok = vol >= vol_mult * avg_vol

    # Compute rs_ret for target
    ret = close.pct_change(rs_lb)

    # Cross-sectional percentile
    all_dates = set(tgt["date"].tolist()) if "date" in tgt.columns else set(tgt.index.tolist())
    # Build date -> list of universe returns for ranking
    # (simplified: use full universe if available, else just the symbol's own ret)
    date_col = tgt["date"] if "date" in tgt.columns else pd.Series(tgt.index)

    rs_rank = pd.Series(np.nan, index=tgt.index)
    for sym, sdf in bars_dict.items():
        pass  # just use simplified rank below

    # Simplified cross-sectional rank: use symbol's own 63d ret rank vs all syms
    all_ret63 = {}
    for sym, sdf in bars_dict.items():
        if "close" in sdf.columns:
            sdf2 = sdf.set_index("date") if "date" in sdf.columns else sdf
            all_ret63[sym] = sdf2["close"].pct_change(rs_lb)

    # For each row in target, compute percentile
    target_dates = tgt["date"].values if "date" in tgt.columns else tgt.index.values
    pct_arr = np.zeros(len(tgt))
    for i, d in enumerate(target_dates):
        vals = []
        for sym, s in all_ret63.items():
            # find value for date d
            if d in s.index:
                v = s.loc[d]
                if not np.isnan(v):
                    vals.append(v)
        if vals:
            tgt_val = ret.iloc[i]
            pct_arr[i] = np.sum(np.array(vals) <= tgt_val) / len(vals)
        else:
            pct_arr[i] = 0.0

    rs_percentile = pd.Series(pct_arr, index=tgt.index)
    rs_ok = rs_percentile >= rs_min_pct

    return breakout & vol_ok & rs_ok


def signal_s08(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Single-symbol version (without cross-sectional RS rank — uses ret63 > 0 proxy)."""
    df = _enrich(df)
    lb = int(params.get("lookback_days", 252))
    vol_mult = float(params.get("vol_multiplier", 1.3))

    close = df["close"]
    high = df["high"]
    vol = df["volume"]
    avg_vol = vol.rolling(20, min_periods=20).mean()

    high52 = high.shift(1).rolling(lb, min_periods=lb).max()
    breakout = close > high52
    vol_ok = vol >= vol_mult * avg_vol
    # proxy RS: positive 63d return
    ret63 = close.pct_change(63)
    rs_ok = ret63 > 0

    return breakout & vol_ok & rs_ok


# ---------------------------------------------------------------------------
# S09 — NR7 Breakout
# ---------------------------------------------------------------------------

def signal_s09(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Today's range (high - low) is the narrowest of the last nr_bars bars (NR7).
    Stock above SMA50.
    Signal on bar i; entry trigger = high[i] + entry_buffer_pct% at open of i+1.
    Stop = low[i].
    """
    df = _enrich(df)
    nr = int(params.get("nr_bars", 7))

    close = df["close"]
    high = df["high"]
    low = df["low"]
    rng = high - low
    sma50 = compute_sma(close, 50)

    min_rng = rng.rolling(nr, min_periods=nr).min()
    nr7 = rng <= min_rng
    trend = close > sma50

    return nr7 & trend


# ---------------------------------------------------------------------------
# S10 — EMA 9/21 Cross in Uptrend
# ---------------------------------------------------------------------------

def signal_s10(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    EMA9 crosses above EMA21 (bullish cross). Price above SMA200.
    Volume on crossover day >= vol_multiplier * avg_vol20.
    Signal on bar i; entry at open of i+1.
    Stop = close[i] - stop_atr_mult * ATR14[i].
    """
    df = _enrich(df)
    fast = int(params.get("ema_fast", 9))
    slow = int(params.get("ema_slow", 21))
    vol_mult = float(params.get("vol_multiplier", 1.2))

    close = df["close"]
    vol = df["volume"]
    avg_vol = vol.rolling(20, min_periods=20).mean()
    sma200 = compute_sma(close, 200)

    ema_f = compute_ema(close, fast)
    ema_s = compute_ema(close, slow)

    cross_up = (ema_f > ema_s) & (ema_f.shift(1) <= ema_s.shift(1))
    vol_ok = vol >= vol_mult * avg_vol
    trend = close > sma200

    return cross_up & vol_ok & trend


# ---------------------------------------------------------------------------
# Strategy dispatch registry
# ---------------------------------------------------------------------------

SIGNAL_FUNCTIONS = {
    "S01": signal_s01,
    "S02": signal_s02,
    "S03": signal_s03,
    "S04": signal_s04,
    "S05": signal_s05,
    "S06": signal_s06,
    "S07": signal_s07,
    "S08": signal_s08,
    "S09": signal_s09,
    "S10": signal_s10,
}


def get_signal_function(strategy_id: str):
    fn = SIGNAL_FUNCTIONS.get(strategy_id.upper())
    if fn is None:
        raise ValueError(f"Unknown strategy_id: {strategy_id}")
    return fn
