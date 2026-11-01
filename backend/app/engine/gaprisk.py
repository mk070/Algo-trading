import numpy as np
import pandas as pd


def compute_gap95(df: pd.DataFrame, window: int = 250) -> float:
    """Computes the 95th-percentile adverse overnight gap down over the lookback window."""
    if df is None or len(df) < 10:
        return 0.02  # default 2% gap risk assumption

    recent_df = df.iloc[-window:]
    prev_close = recent_df["close"].shift(1)
    open_p = recent_df["open"]

    # Adverse overnight gap for longs = gap down: (prev_close - open) / prev_close
    adverse_gap = (prev_close - open_p) / prev_close
    down_gaps = adverse_gap[adverse_gap > 0].dropna()

    if len(down_gaps) == 0:
        return 0.015

    gap95 = float(np.percentile(down_gaps, 95))
    return max(0.01, min(gap95, 0.15))  # clamp between 1% and 15%


def calculate_effective_risk_per_share(
    entry: float, stop: float, gap95: float
) -> float:
    """Blends structural stop risk with historical 95th-percentile overnight gap risk."""
    nominal_risk = entry - stop
    gap_risk = entry * gap95 * 0.5 + nominal_risk * 0.5
    return max(nominal_risk, gap_risk)

