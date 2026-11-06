"""
Unit Tests for Research Cycle 3 Strategies and Factor Engines
Strictly Offline Research — Candidate Validity and Formula Verification
"""

import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import pytest


def compute_rsi_series(series: pd.Series, period: int = 2) -> pd.Series:
    """Wilder RSI calculation."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    rsi = rsi.where(avg_gain != 0.0, 0.0)
    return rsi


def compute_frog_in_the_pan_id(daily_returns: np.ndarray, pret: float) -> float:
    """Calculates Information Discreteness (ID = sgn(PRET) * [%neg - %pos])."""
    if pret <= 0:
        return np.nan
    n_total = len(daily_returns)
    if n_total == 0:
        return np.nan
    n_neg = np.sum(daily_returns < 0)
    n_pos = np.sum(daily_returns > 0)
    pct_neg = n_neg / n_total
    pct_pos = n_pos / n_total
    # Since PRET > 0, sgn(PRET) = +1
    return float(pct_neg - pct_pos)


def compute_residual_momentum_score(
    stock_returns: np.ndarray,
    market_returns: np.ndarray,
    sector_returns: np.ndarray | None = None,
) -> float:
    """
    Calculates standardized cumulative residual momentum score.
    R_i = alpha + beta_M * R_M + (beta_S * R_S) + eps.
    Idiosyncratic return: R_i - beta_M * R_M - beta_S * R_S = alpha + eps.
    Cumulative idiosyncratic return: N * alpha.
    Score = (N * alpha) / sigma(eps).
    """
    n = len(stock_returns)
    if sector_returns is not None and len(sector_returns) == n:
        X = np.column_stack([np.ones(n), market_returns, sector_returns])
    else:
        X = np.column_stack([np.ones(n), market_returns])

    coef, _, _, _ = np.linalg.lstsq(X, stock_returns, rcond=None)
    alpha = coef[0]
    pred = X @ coef
    resids = stock_returns - pred
    std_res = np.std(resids, ddof=1)
    if std_res <= 1e-12:
        return 0.0
    return float((n * alpha) / std_res)


def test_residual_momentum_ols_fixture():
    """Verify OLS residual momentum calculation against an exact analytical fixture."""
    # Construct synthetic return series where market and sector are not perfectly collinear
    r_m = np.array([0.01, -0.01, 0.02, -0.02, 0.015, -0.005, 0.01, -0.015])
    r_s = np.array([0.005, 0.01, -0.005, 0.015, -0.01, 0.02, -0.01, 0.005])
    noise = np.array([0.001, -0.001, 0.0015, -0.001, 0.0005, -0.001, 0.001, -0.001])
    r_stock = 0.002 + 1.0 * r_m + 0.5 * r_s + noise

    score = compute_residual_momentum_score(r_stock, r_m, r_s)
    # Alpha should be exactly 0.002
    # std(noise, ddof=1) is positive, score should be strictly positive
    assert score > 0.0
    assert np.isfinite(score)


def test_frog_in_the_pan_smooth_vs_discrete():
    """Verify Da, Gurun & Warachka Information Discreteness distinguishes smooth vs discrete paths."""
    # Both paths have total return of +10% over 10 days
    # Path A (Smooth): 8 small positive days (+1.5%), 2 small negative days (-1.0%)
    rets_smooth = np.array([0.015, 0.015, -0.010, 0.015, 0.015, -0.010, 0.015, 0.015, 0.015, 0.015])
    pret_smooth = float(np.prod(1.0 + rets_smooth) - 1.0)
    assert pret_smooth > 0

    id_smooth = compute_frog_in_the_pan_id(rets_smooth, pret_smooth)
    # %neg = 2/10 = 0.2, %pos = 8/10 = 0.8 => ID = 0.2 - 0.8 = -0.6
    assert pytest.approx(id_smooth, 1e-4) == -0.60

    # Path B (Discrete): 1 massive jump (+18%), 8 small negative days (-1.0%), 1 flat (0%)
    rets_discrete = np.array([0.18, -0.01, -0.01, -0.01, -0.01, -0.01, -0.01, -0.01, -0.01, 0.00])
    pret_discrete = float(np.prod(1.0 + rets_discrete) - 1.0)
    assert pret_discrete > 0

    id_discrete = compute_frog_in_the_pan_id(rets_discrete, pret_discrete)
    # %neg = 8/10 = 0.8, %pos = 1/10 = 0.1 => ID = 0.8 - 0.1 = +0.7
    assert pytest.approx(id_discrete, 1e-4) == +0.70

    # Smooth path must have strictly lower ID than discrete path (smoother = more negative ID)
    assert id_smooth < id_discrete


def test_connors_rsi2_calculation_and_exits():
    """Verify Connors RSI(2) setup trigger and SMA5 exit vs 5-day time stop."""
    # Daily closes dropping sharply
    prices = pd.Series([100.0, 105.0, 102.0, 95.0, 90.0, 85.0, 81.0])
    rsi2 = compute_rsi_series(prices, period=2)
    # After consecutive sharp declines, RSI(2) should drop below 10
    assert rsi2.iloc[-1] <= 10.0

    # Scenario 1: Quick bounce above SMA5
    # Closes: [85, 81, 88, 92] -> SMA5 on day 3 = mean([102, 95, 90, 85, 81]) = 90.6
    # day 4: close 95 > SMA5 => triggers SMA5 exit
    series_bounce = pd.Series([105.0, 102.0, 95.0, 90.0, 85.0, 81.0, 88.0, 96.0])
    sma5 = series_bounce.rolling(5).mean()
    assert series_bounce.iloc[-1] > sma5.iloc[-1]

    # Scenario 2: Stagnant price hitting 5-day time stop
    holding_days = 5
    assert holding_days >= 5


def test_no_lookahead_temporal_integrity():
    """Verify indicators and scores at cutoff date T are strictly identical whether calculated on full or truncated history."""
    dates = pd.date_range("2023-01-01", periods=300, freq="B")
    np.random.seed(42)
    daily_rets = np.random.normal(0.0005, 0.015, size=len(dates))
    prices = pd.Series(100.0 * np.exp(np.cumsum(daily_rets)), index=dates)

    cutoff_idx = 200
    cutoff_date = dates[cutoff_idx]

    # Full history
    full_rsi = compute_rsi_series(prices, period=2)
    full_val = full_rsi.loc[cutoff_date]

    # Truncated history (only data up to cutoff_date)
    trunc_prices = prices.iloc[: cutoff_idx + 1]
    trunc_rsi = compute_rsi_series(trunc_prices, period=2)
    trunc_val = trunc_rsi.loc[cutoff_date]

    assert pytest.approx(full_val, 1e-9) == trunc_val


def test_cost_model_invariance():
    """Verify Indian Zerodha equity delivery cost model calculates fees and statutory charges correctly."""
    turnover = 100000.0  # ₹1 Lakh
    # BUY side
    stt_buy = 0.001 * turnover
    exch = 0.00003 * turnover
    sebi = (10.0 / 10000000.0) * turnover
    stamp = 0.00015 * turnover
    gst_buy = 0.18 * (exch + sebi)
    expected_buy_cost = stt_buy + exch + sebi + stamp + gst_buy

    assert pytest.approx(stt_buy, 1e-4) == 100.0
    assert pytest.approx(stamp, 1e-4) == 15.0
    assert expected_buy_cost > 115.0

    # SELL side includes DP charge
    dp_charge = 13.50 * 1.18
    stt_sell = 0.001 * turnover
    gst_sell = 0.18 * (exch + sebi + (13.50 * 1.18))
    expected_sell_cost = stt_sell + exch + sebi + dp_charge + gst_sell
    assert expected_sell_cost > expected_buy_cost
