import datetime
import numpy as np
import pandas as pd
import pytest

from app.engine.regime import evaluate_market_regime
from app.engine.planner import Planner


def test_regime_none_returns_unknown_and_disallows_entries():
    """Verify that when index_df is None, regime returns UNKNOWN and blocks entries (Rules 6 & 11)."""
    res = evaluate_market_regime(None, market="IN")
    assert res.status == "UNKNOWN"
    assert res.allows_entries is False
    assert res.is_bullish is False
    assert res.size_multiplier == 0.0
    assert "Insufficient index history" in res.detail


def test_regime_insufficient_bars_returns_unknown():
    """Verify that when index_df has fewer than 200 bars, regime returns UNKNOWN."""
    dates = pd.date_range("2024-01-01", periods=100)
    df = pd.DataFrame({"close": [24000.0] * 100, "date": dates}, index=dates)
    res = evaluate_market_regime(df, market="IN")
    assert res.status == "UNKNOWN"
    assert res.allows_entries is False
    assert res.size_multiplier == 0.0
    assert "100 bars < 200 required" in res.detail


def test_regime_stale_index_data_withholds_entries():
    """Verify that when index_df is stale (last bar lags reference date), regime returns UNKNOWN."""
    # Data ends on 2024-01-31
    dates = pd.date_range("2023-01-01", "2024-01-31", freq="B")
    df = pd.DataFrame({"close": [24000.0] * len(dates)}, index=dates)
    
    # Reference date is 2 weeks later: 2024-02-15
    res = evaluate_market_regime(df, market="IN", asof_date=datetime.date(2024, 2, 15))
    assert res.status == "UNKNOWN"
    assert res.allows_entries is False
    assert "Stale index data" in res.detail


def test_regime_nan_moving_average_returns_unknown():
    """Verify that NaN in computed SMA results in UNKNOWN instead of fabricated values."""
    dates = pd.date_range("2023-01-01", periods=220, freq="B")
    close_vals = [24000.0] * 220
    close_vals[-1] = np.nan  # inject NaN at latest close
    df = pd.DataFrame({"close": close_vals}, index=dates)

    res = evaluate_market_regime(df, market="IN", asof_date=dates[-1].date())
    assert res.status == "UNKNOWN"
    assert res.allows_entries is False


def test_regime_valid_220_bars_bullish():
    """Verify that valid 220 bars with price above SMA50 and SMA200 evaluates BULLISH."""
    dates = pd.date_range("2023-01-01", periods=250, freq="B")
    # Upward trend: from 20000 to 25000
    close_vals = np.linspace(20000, 25000, 250)
    df = pd.DataFrame({"close": close_vals}, index=dates)

    res = evaluate_market_regime(df, market="IN", asof_date=dates[-1].date())
    assert res.status == "BULLISH"
    assert res.allows_entries is True
    assert res.is_bullish is True
    assert res.size_multiplier == 1.0
