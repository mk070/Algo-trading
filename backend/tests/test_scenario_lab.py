import datetime
import numpy as np
import pandas as pd
import pytest

from app.backtest.scenario_lab import ScenarioLabEngine, wilson_score_interval


def make_synthetic_history(start_date: datetime.date, num_bars: int = 150) -> pd.DataFrame:
    dates = [start_date + datetime.timedelta(days=i) for i in range(num_bars)]
    np.random.seed(123)
    prices = [100.0]
    for _ in range(num_bars - 1):
        prices.append(prices[-1] * (1.0 + np.random.normal(0.001, 0.015)))

    rows = []
    for d, p in zip(dates, prices):
        rows.append(
            {
                "date": d,
                "open": p * 0.995,
                "high": p * 1.015,
                "low": p * 0.99,
                "close": p,
                "volume": 100000.0 + np.random.uniform(0, 50000),
                "atr": p * 0.025,
            }
        )
    return pd.DataFrame(rows)


def test_wilson_score_interval():
    # 50 successes out of 100 at 95% confidence should yield approximately [40.4%, 59.6%]
    lower, upper = wilson_score_interval(50, 100)
    assert lower >= 40.0 and lower <= 41.0
    assert upper >= 59.0 and upper <= 60.0

    # Boundary test: 0 successes
    l0, u0 = wilson_score_interval(0, 50)
    assert l0 == 0.0
    assert u0 > 0.0 and u0 <= 7.5


def test_strict_anti_leakage_no_future_data():
    """Rule (a): Every analogue and its entire evaluation window MUST strictly end on or before asof_date."""
    engine = ScenarioLabEngine(min_analogues=2, default_simulations=500)
    asof = datetime.date(2026, 4, 1)

    # DataFrame with 200 bars spanning before and after asof
    full_df = make_synthetic_history(datetime.date(2025, 6, 1), num_bars=250)

    # Introduce a prominent breakout AFTER asof (e.g. at 2026-05-15)
    future_date = datetime.date(2026, 5, 15)
    future_mask = full_df["date"] == future_date
    if any(future_mask):
        idx = full_df[future_mask].index[0]
        full_df.loc[idx, "high"] = full_df.loc[idx, "close"] * 1.5

    res = engine.evaluate(
        symbol="TEST",
        df=full_df,
        trigger=120.0,
        stop=114.0,
        asof=asof,
        all_historical_dfs={"TEST": full_df},
        n_simulations=200,
        seed=42,
    )

    # Check observed analogues
    if res.observed.status == "OK":
        assert res.observed.date_range is not None
        latest_analogue_date = datetime.date.fromisoformat(res.observed.date_range[1])
        # The analogue start date must be at least 20 trading sessions before asof
        assert latest_analogue_date <= (asof - datetime.timedelta(days=20))


def test_sample_size_guard_shows_insufficient_sample():
    """Rule (b): Fewer than min_analogues events MUST show INSUFFICIENT SAMPLE, not percentages."""
    engine = ScenarioLabEngine(min_analogues=25, default_simulations=500)
    asof = datetime.date(2026, 4, 1)
    df = make_synthetic_history(datetime.date(2025, 10, 1), num_bars=80)

    res = engine.evaluate(
        symbol="SPARSE",
        df=df,
        trigger=100.0,
        stop=95.0,
        asof=asof,
        all_historical_dfs={"SPARSE": df},
        n_simulations=200,
    )

    assert res.observed.status == "INSUFFICIENT SAMPLE"
    assert res.observed.sample_size_n < 25
    # Percentages in observed horizons should be omitted / empty
    assert len(res.observed.horizons) == 0
    assert "INSUFFICIENT SAMPLE" in res.observed.note


def test_separate_observed_and_simulated_outputs_with_sample_sizes():
    """Rule (c): 10,000 simulations are NOT 10,000 observations.
    Always show both numbers clearly separated.
    """
    engine = ScenarioLabEngine(min_analogues=1, default_simulations=1000)
    asof = datetime.date(2026, 4, 1)
    df = make_synthetic_history(datetime.date(2025, 1, 1), num_bars=200)

    res = engine.evaluate(
        symbol="DUAL",
        df=df,
        trigger=110.0,
        stop=104.0,
        asof=asof,
        all_historical_dfs={"DUAL": df},
        n_simulations=1000,
        seed=101,
    )

    # Observed sample size (N) vs Simulated runs (M)
    assert res.observed.sample_size_n >= 0
    assert res.simulated.simulation_runs_m == 1000
    assert res.simulated.simulation_runs_m != res.observed.sample_size_n

    # Simulations must have distributions across horizons
    assert "5d" in res.simulated.horizons
    assert "10d" in res.simulated.horizons
    assert "20d" in res.simulated.horizons
    assert res.simulated.horizons["10d"].first_passage_1r_pct is not None
    assert res.simulated.horizons["10d"].stop_first_pct is not None


def test_reproducible_simulation_seeds():
    engine = ScenarioLabEngine(default_simulations=500)
    asof = datetime.date(2026, 4, 1)
    df = make_synthetic_history(datetime.date(2025, 5, 1), num_bars=120)

    res1 = engine.evaluate("SEEDTEST", df, trigger=105.0, stop=100.0, asof=asof, n_simulations=500, seed=777)
    # Clear cache to verify reproducibility
    engine._cache.clear()
    res2 = engine.evaluate("SEEDTEST", df, trigger=105.0, stop=100.0, asof=asof, n_simulations=500, seed=777)

    assert res1.simulated.horizons["10d"].first_passage_1r_pct == res2.simulated.horizons["10d"].first_passage_1r_pct
    assert res1.simulated.horizons["10d"].stop_first_pct == res2.simulated.horizons["10d"].stop_first_pct
    assert res1.simulated.drawdown_distribution["median"] == res2.simulated.drawdown_distribution["median"]


def test_limitations_disclaimer_rule():
    """Rule (d): Results must never claim to be predictions or probability of profit."""
    engine = ScenarioLabEngine(default_simulations=200)
    asof = datetime.date(2026, 4, 1)
    df = make_synthetic_history(datetime.date(2025, 5, 1), num_bars=120)

    res = engine.evaluate("DISCLAIMER", df, trigger=100.0, stop=95.0, asof=asof, n_simulations=200)
    assert "LIMITATIONS DISCLAIMER" in res.limitations_disclaimer
    assert "probability of profit" in res.limitations_disclaimer.lower() or "probabilities" in res.limitations_disclaimer.lower()

