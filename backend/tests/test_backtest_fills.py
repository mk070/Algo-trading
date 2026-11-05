import datetime
import pandas as pd
import pytest
from app.backtest.simulator import BacktestSimulator
from app.engine.costs import CostModel
from app.engine.setups import SetupCandidate


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


def test_simulator_charges_slippage_once_and_liquidates_using_actual_fill_prices():
    class SingleFixtureSignal:
        def evaluate_vcp_breakout(self, symbol, df, tick=0.05):
            if len(df) != 60:
                return None
            return SetupCandidate(
                symbol=symbol, setup="VCP", pivot=100.0, trigger=100.5,
                entry_zone_high=101.0, stop=95.0, target1=120.0,
                risk_per_share=5.5, risk_r=5.5, atr=1.0, reasons=["fixture"],
            )

        def evaluate_pullback(self, symbol, df, tick=0.05):
            return None

    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    opens = [100.0] * 80
    highs = [101.0] * 80
    lows = [99.0] * 80
    closes = [100.0] * 80
    # Signal on bar 60, next session fills at the trigger; later the stop gaps.
    opens[65], highs[65], lows[65], closes[65] = 94.0, 96.0, 93.0, 94.0
    frame = pd.DataFrame({
        "date": dates, "open": opens, "high": highs, "low": lows,
        "close": closes, "adj_close": closes, "volume": [500000.0] * 80,
    })
    sim = BacktestSimulator("IN", setup_engine_override=SingleFixtureSignal())
    result = sim.run({"FIXTURE": frame}, start_date=dates[0], end_date=dates[-1], capital=100000.0, setup_filter="VCP")
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["entry_price"] == pytest.approx(100.5 * (1 + sim.slip_pct), abs=0.01)
    assert trade["exit_price"] == pytest.approx(94.0 * (1 - sim.slip_pct), abs=0.01)
    fee_only = CostModel("IN").calculate_round_trip(
        trade["entry_price"], trade["qty"],
        (trade["entry_price"] - 95.0) * trade["qty"], include_slippage=False,
    )
    gross_after_slipped_fills = (trade["exit_price"] - trade["entry_price"]) * trade["qty"]
    assert trade["pnl"] == pytest.approx(gross_after_slipped_fills - fee_only.total_cost, abs=0.02)
    actual_slippage = (trade["entry_price"] - 100.5) * trade["qty"] + (94.0 - trade["exit_price"]) * trade["qty"]
    assert trade["costs"] == pytest.approx(fee_only.total_cost + actual_slippage, abs=0.02)


def test_close_detected_trend_break_fills_at_next_session_open():
    class SingleFixtureSignal:
        def evaluate_vcp_breakout(self, symbol, df, tick=0.05):
            if len(df) != 60:
                return None
            return SetupCandidate(
                symbol=symbol, setup="VCP", pivot=100.0, trigger=100.5,
                entry_zone_high=101.0, stop=95.0, target1=120.0,
                risk_per_share=5.5, risk_r=5.5, atr=1.0, reasons=["fixture"],
            )

        def evaluate_pullback(self, symbol, df, tick=0.05):
            return None

    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    opens = [100.0] * 80
    highs = [101.0] * 80
    lows = [99.0] * 80
    closes = [100.0] * 80
    closes[60] = 99.0  # trend break is known only after this bar closes
    opens[61], highs[61], lows[61], closes[61] = 103.0, 104.0, 102.0, 103.0
    frame = pd.DataFrame({
        "date": dates, "open": opens, "high": highs, "low": lows,
        "close": closes, "adj_close": closes, "volume": [500000.0] * 80,
    })
    sim = BacktestSimulator("IN", setup_engine_override=SingleFixtureSignal())
    result = sim.run({"FIXTURE": frame}, start_date=dates[0], end_date=dates[-1], capital=100000.0, setup_filter="VCP")
    trade = result["trades"][0]
    assert trade["exit_reason"] == "Trend Break (< 50 SMA)"
    assert trade["exit_date"] == dates[61]
    assert trade["exit_price"] == pytest.approx(103.0 * (1 - sim.slip_pct), abs=0.01)


def test_configured_partial_target_is_realized_and_aggregated_with_remainder():
    class SingleFixtureSignal:
        def evaluate_vcp_breakout(self, symbol, df, tick=0.05):
            if len(df) != 60:
                return None
            return SetupCandidate(
                symbol=symbol, setup="VCP", pivot=100.0, trigger=100.5,
                entry_zone_high=101.0, stop=95.0, target1=120.0,
                risk_per_share=5.5, risk_r=5.5, atr=1.0, reasons=["fixture"],
            )

        def evaluate_pullback(self, symbol, df, tick=0.05):
            return None

    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    opens = [100.0] * 80
    highs = [101.0] * 80
    lows = [99.0] * 80
    closes = [100.0] * 80
    highs[62], lows[62], closes[62] = 113.0, 103.0, 110.0  # 2R partial target
    opens[63], highs[63], lows[63], closes[63] = 100.0, 101.0, 99.0, 100.0  # remainder hits breakeven stop
    frame = pd.DataFrame({
        "date": dates, "open": opens, "high": highs, "low": lows,
        "close": closes, "adj_close": closes, "volume": [500000.0] * 80,
    })
    sim = BacktestSimulator("IN", setup_engine_override=SingleFixtureSignal())
    result = sim.run({"FIXTURE": frame}, start_date=dates[0], end_date=dates[-1], capital=100000.0, setup_filter="VCP")
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert "Partial Target" in trade["exit_reason"]
    assert trade["qty"] > 1
    assert trade["pnl"] > 0
    assert trade["exit_date"] == dates[63]

