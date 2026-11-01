import datetime
import numpy as np
import pandas as pd
import pytest
from app.engine.indicators import add_all_indicators
from app.engine.pipeline import decision_pipeline


def make_clean_breakout_df(n_bars: int = 70) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=n_bars, freq="B").date
    np.random.seed(123)
    # Strong uptrend: 100 to 180
    trend = np.linspace(100, 180, n_bars)
    # Add a tight base consolidation in the last 20 bars
    base_pivot = 180.0
    for i in range(n_bars - 20, n_bars):
        trend[i] = base_pivot - (180 - i) * 0.15

    close = pd.Series(trend)
    high = close * 1.008
    low = close * 0.992
    open_p = (high + low) / 2
    vol = pd.Series([200000.0] * n_bars)
    # Dry up volume in base
    vol.iloc[-10:] = 120000.0

    df = pd.DataFrame(
        {
            "date": dates,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "adj_close": close,
            "volume": vol,
        }
    )
    return add_all_indicators(df)


def test_earnings_tomorrow_blocks_clean_breakout():
    """Acceptance Test: A clean breakout with earnings scheduled tomorrow MUST be BLOCKED
    by the News/Event Analyst stage with the exact reason.
    """
    df = make_clean_breakout_df(70)
    asof = df["date"].iloc[-1]
    earnings_tomorrow = asof + datetime.timedelta(days=1)

    decision = decision_pipeline.evaluate(
        symbol="RELIANCE",
        df=df,
        market="IN",
        asof=asof,
        mode="LIVE",
        earnings_date=earnings_tomorrow,
        capital_override=100000.0,  # ample capital
    )

    assert decision.final_decision == "BLOCK"

    # Find the News/Event Analyst stage
    news_stage = next(s for s in decision.stages if s.stage_name == "News/Event Analyst")
    assert news_stage.status == "BLOCK"

    # Verify exact rejection reason mentions earnings blackout
    assert any("blackout" in r.lower() for r in news_stage.rejection_reasons)
    assert any("blackout" in r.lower() for r in decision.all_rejection_reasons)


def test_identical_decisions_across_live_paper_backtest_modes():
    """Acceptance Test: Identical inputs MUST give identical decisions across
    LIVE, PAPER, and BACKTEST modes.
    """
    df = make_clean_breakout_df(70)
    asof = df["date"].iloc[-1]

    d_live = decision_pipeline.evaluate(
        symbol="TCS", df=df, market="IN", asof=asof, mode="LIVE", capital_override=100000.0
    )
    d_paper = decision_pipeline.evaluate(
        symbol="TCS", df=df, market="IN", asof=asof, mode="PAPER", capital_override=100000.0
    )
    d_backtest = decision_pipeline.evaluate(
        symbol="TCS", df=df, market="IN", asof=asof, mode="BACKTEST", capital_override=100000.0
    )

    assert d_live.final_decision == d_paper.final_decision == d_backtest.final_decision
    assert d_live.trigger == d_paper.trigger == d_backtest.trigger
    assert d_live.stop == d_paper.stop == d_backtest.stop
    assert d_live.qty == d_paper.qty == d_backtest.qty
    assert d_live.config_hash == d_paper.config_hash == d_backtest.config_hash
    assert len(d_live.stages) == len(d_paper.stages) == len(d_backtest.stages)

