import datetime
import pandas as pd
import pytest
from app.backtest.simulator import BacktestSimulator


def test_fill_rules_execution():
    sim = BacktestSimulator(market="IN")
    slip = sim.slip_pct

    # Create synthetic daily bars
    dates = pd.date_range("2025-01-01", periods=100, freq="B").date
    df = pd.DataFrame(
        {
            "date": dates,
            "open": [100.0] * 100,
            "high": [102.0] * 100,
            "low": [98.0] * 100,
            "close": [101.0] * 100,
            "adj_close": [101.0] * 100,
            "volume": [500000.0] * 100,
        }
    )

    # Trigger a run on this data
    res = sim.run({"TEST": df})
    assert "metrics" in res
    assert "survivorship_bias_notice" in res
    assert "trades" in res

