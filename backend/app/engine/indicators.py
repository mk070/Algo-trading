import numpy as np
import pandas as pd


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=window, min_periods=window).mean()


def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=span, adjust=False).mean()


def compute_rsi_wilder(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's Smoothed Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # First value is simple average
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    # Wilder's smoothing: alpha = 1 / window
    # ewm with alpha=1/window and adjust=False matches Wilder's exact recursion:
    # y[t] = (y[t-1]*(n-1) + x[t]) / n
    avg_gain_wilder = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss_wilder = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()

    # When loss is 0 and gain > 0, RSI is 100. When both are 0, RSI is 50.
    rs = np.where(
        avg_loss_wilder == 0,
        np.where(avg_gain_wilder == 0, 1.0, np.inf),
        avg_gain_wilder / avg_loss_wilder,
    )
    rsi_vals = 100.0 - (100.0 / (1.0 + rs))
    return pd.Series(rsi_vals, index=series.index).fillna(50.0)


def compute_atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's Smoothed Average True Range (ATR)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing with alpha = 1 / window
    atr = tr.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    return atr


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enriches daily OHLCV dataframe with all required technical indicators."""
    df = df.copy()
    if len(df) < 50:
        return df

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    df["sma50"] = compute_sma(close, 50)
    df["sma150"] = compute_sma(close, 150)
    df["sma200"] = compute_sma(close, 200)

    df["ema20"] = compute_ema(close, 20)
    df["ema50"] = compute_ema(close, 50)

    df["rsi14"] = compute_rsi_wilder(close, 14)
    df["atr14"] = compute_atr_wilder(high, low, close, 14)

    df["avg_vol20"] = vol.rolling(window=20, min_periods=20).mean()
    df["avg_vol50"] = vol.rolling(window=50, min_periods=50).mean()

    df["high252"] = high.rolling(window=252, min_periods=50).max()
    df["low252"] = low.rolling(window=252, min_periods=50).min()
    df["high55"] = high.rolling(window=55, min_periods=20).max()

    df["ret21"] = close.pct_change(21)
    df["ret63"] = close.pct_change(63)
    df["ret126"] = close.pct_change(126)

    return df
