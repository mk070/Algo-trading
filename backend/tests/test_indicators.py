import numpy as np
import pandas as pd
import pytest
from app.engine.indicators import (
    compute_atr_wilder,
    compute_ema,
    compute_rsi_wilder,
    compute_sma,
)


def test_sma_calculation():
    s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    sma3 = compute_sma(s, 3)
    assert pd.isna(sma3.iloc[0])
    assert pd.isna(sma3.iloc[1])
    assert sma3.iloc[2] == 20.0
    assert sma3.iloc[3] == 30.0
    assert sma3.iloc[4] == 40.0


def test_ema_calculation():
    s = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    ema = compute_ema(s, 3)
    # alpha = 2 / (3 + 1) = 0.5
    # ema[0] = 10
    # ema[1] = 0.5*11 + 0.5*10 = 10.5
    # ema[2] = 0.5*12 + 0.5*10.5 = 11.25
    assert ema.iloc[0] == 10.0
    assert ema.iloc[1] == 10.5
    assert ema.iloc[2] == 11.25


def test_rsi_bounds():
    # Steadily rising series should yield high RSI (> 70)
    rising = pd.Series([100.0 + i * 2.0 for i in range(30)])
    rsi_rising = compute_rsi_wilder(rising, 14)
    assert rsi_rising.iloc[-1] > 70.0

    # Steadily falling series should yield low RSI (< 30)
    falling = pd.Series([200.0 - i * 2.0 for i in range(30)])
    rsi_falling = compute_rsi_wilder(falling, 14)
    assert rsi_falling.iloc[-1] < 30.0


def test_atr_wilder():
    high = pd.Series([105.0, 106.0, 107.0, 108.0] * 5)
    low = pd.Series([95.0, 96.0, 97.0, 98.0] * 5)
    close = pd.Series([100.0, 101.0, 102.0, 103.0] * 5)

    atr = compute_atr_wilder(high, low, close, 14)
    assert not atr.isna().all()
    # TR is approx 10 per day, so smoothed ATR should hover around 10
    assert 9.0 <= atr.iloc[-1] <= 11.0

