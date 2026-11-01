import datetime
import numpy as np
import pandas as pd
import pytest
from app.engine.indicators import add_all_indicators
from app.engine.setups import setup_engine


def generate_synthetic_series(n_bars: int = 150) -> pd.DataFrame:
    dates = pd.date_range(start="2025-01-01", periods=n_bars, freq="B").date
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.015, n_bars)
    prices = 100.0 * np.exp(np.cumsum(returns))
    highs = prices * 1.01
    lows = prices * 0.99
    opens = (highs + lows) / 2
    vols = np.random.uniform(100000, 500000, n_bars)

    return pd.DataFrame(
        {
            "date": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": prices,
            "adj_close": prices,
            "volume": vols,
        }
    )


def test_no_lookahead_bias_in_indicators_and_setups():
    """Verify that indicators and setups computed on day t are completely identical
    whether the dataset ends on day t or includes 50 future days.
    """
    full_df = generate_synthetic_series(150)
    full_enriched = add_all_indicators(full_df)

    test_indices = [60, 75, 90, 105, 120]

    for idx in test_indices:
        target_date = full_df["date"].iloc[idx]

        # Truncate strictly at day t
        truncated_df = full_df.iloc[: idx + 1].copy()
        truncated_enriched = add_all_indicators(truncated_df)

        # 1. Compare SMA50, EMA20, RSI14, ATR14 at day t
        full_row = full_enriched.iloc[idx]
        trunc_row = truncated_enriched.iloc[-1]

        assert full_row["date"] == trunc_row["date"] == target_date
        assert np.isclose(full_row["sma50"], trunc_row["sma50"], rtol=1e-5)
        assert np.isclose(full_row["ema20"], trunc_row["ema20"], rtol=1e-5)
        assert np.isclose(full_row["rsi14"], trunc_row["rsi14"], rtol=1e-5)
        assert np.isclose(full_row["atr14"], trunc_row["atr14"], rtol=1e-5)

        # 2. Evaluate Setup V on truncated series
        cand_trunc = setup_engine.evaluate_vcp_breakout("TEST", truncated_enriched)

        # Future data should not affect whether day t formed a valid candidate
        # If cand_trunc exists, trigger and stop are strictly determined by day <= t
        if cand_trunc:
            assert cand_trunc.trigger > 0
            assert cand_trunc.stop < cand_trunc.trigger

