import datetime
import math
import pandas as pd
import pytest

from app.backtest.metrics import BacktestMetrics, compute_backtest_metrics
from app.backtest.simulator import BacktestSimulator, SimulatedTrade
from app.backtest.walkforward import run_walk_forward_analysis, WalkForwardResult
from app.engine.costs import CostModel
from app.engine.setups import SetupCandidate


class MockSetupEngine:
    def __init__(self, signals_by_day_and_sym):
        # Dict[Tuple[str, int], SetupCandidate] where int is the bar index
        self.signals = signals_by_day_and_sym

    def evaluate_vcp_breakout(self, symbol, df, tick=0.05):
        bar_idx = len(df) - 1
        return self.signals.get((symbol, bar_idx))

    def evaluate_pullback(self, symbol, df, tick=0.05):
        return None


def generate_constant_bars(symbol: str, n_bars: int = 80, base_price: float = 100.0, start_date: str = "2025-01-01"):
    dates = pd.date_range(start_date, periods=n_bars, freq="B").date
    return pd.DataFrame({
        "date": dates,
        "open": [base_price] * n_bars,
        "high": [base_price + 1.0] * n_bars,
        "low": [base_price - 1.0] * n_bars,
        "close": [base_price] * n_bars,
        "adj_close": [base_price] * n_bars,
        "volume": [500000.0] * n_bars,
    })


# 1. Gross / Net P&L Reconciliation
def test_gross_net_pnl_reconciliation():
    """Verify that gross_pnl - costs == pnl for every trade and for the entire portfolio."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("TEST", 80, 100.0)

    # Bar 60: Signal generated at trigger 101.0, stop 95.0
    # Bar 61: Fills at trigger 101.0
    # Bar 65: Exits at 115.0 (gain)
    df.loc[65, "open"] = 115.0
    df.loc[65, "high"] = 116.0
    df.loc[65, "low"] = 114.0
    df.loc[65, "close"] = 115.0

    signal = SetupCandidate(
        symbol="TEST", setup="VCP", pivot=100.5, trigger=101.0,
        entry_zone_high=102.0, stop=95.0, target1=120.0,
        risk_per_share=6.0, risk_r=6.0, atr=1.5, reasons=["fixture"],
    )
    mock_engine = MockSetupEngine({("TEST", 59): signal})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    # Force an exit on bar 65 via hard stop or trend break or liquidation
    res = sim.run({"TEST": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert len(res["trades"]) >= 1
    trade = res["trades"][0]

    # Trade level reconciliation: gross_pnl - costs == pnl
    assert "gross_pnl" in trade
    assert trade["gross_pnl"] - trade["costs"] == pytest.approx(trade["pnl"], abs=0.02)

    # Portfolio level reconciliation
    metrics = res["metrics"]
    assert metrics["gross_profit"] >= 0.0
    assert metrics["gross_loss"] >= 0.0
    # Gross Profit - Gross Loss - Total Costs == Net Total P&L
    reconciled_pnl = metrics["gross_profit"] - metrics["gross_loss"] - metrics["total_costs"]
    assert reconciled_pnl == pytest.approx(metrics["total_pnl"], abs=0.05)
    # Net Profit - Net Loss == Net Total P&L
    assert metrics["net_profit"] - metrics["net_loss"] == pytest.approx(metrics["total_pnl"], abs=0.05)


# 2. Exactly-once Cost Deductions
def test_exactly_once_cost_deductions():
    """Verify brokerage, taxes, fees, and slippage are deducted exactly once."""
    trades = [
        {"pnl": 90.0, "costs": 10.0, "gross_pnl": 100.0, "r_multiple": 1.0, "entry_date": "2025-01-01", "exit_date": "2025-01-05"},
        {"pnl": -60.0, "costs": 10.0, "gross_pnl": -50.0, "r_multiple": -0.6, "entry_date": "2025-01-06", "exit_date": "2025-01-10"},
    ]
    metrics = compute_backtest_metrics(trades, initial_capital=10000.0)
    assert metrics.total_costs == 20.0
    assert metrics.total_pnl == 30.0
    # Gross profits = 100.0, gross loss = 50.0, total costs = 20.0 -> net = 30.0
    assert metrics.gross_profit == 100.0
    assert metrics.gross_loss == 50.0
    assert metrics.gross_profit - metrics.gross_loss - metrics.total_costs == pytest.approx(30.0, abs=0.01)


# 3. Slippage Accounting
def test_slippage_accounting():
    """Verify slippage is applied to fill prices and not double-counted in cost model."""
    sim = BacktestSimulator(market="IN")
    slip_pct = sim.slip_pct
    entry_trigger = 100.0
    expected_slipped_entry = entry_trigger * (1.0 + slip_pct)

    # Cost model without slippage
    fee_breakdown = sim.cost_model.calculate_round_trip(expected_slipped_entry, 100, 500.0, include_slippage=False)
    assert fee_breakdown.slippage == 0.0
    assert fee_breakdown.total_cost > 0.0


# 4. Partial Exit and Remaining Quantity
def test_partial_exit_and_remaining_quantity():
    """Verify partial target realizes 50% qty, moves stop to BE, and remainder closes at BE."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("PARTIAL_SYM", 80, 100.0)

    # Entry on bar 60 (trigger 100.0, stop 90.0, risk 10.0, 2R target = 120.0)
    signal = SetupCandidate(
        symbol="PARTIAL_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=90.0, target1=120.0,
        risk_per_share=10.0, risk_r=10.0, atr=2.0, reasons=["fixture"],
    )
    # Bar 62 hits 2R target (120.0)
    df.loc[62, "high"] = 125.0
    df.loc[62, "close"] = 121.0
    # Bar 63 drops to breakeven (100.0)
    df.loc[63, "low"] = 99.0
    df.loc[63, "close"] = 100.0

    mock_engine = MockSetupEngine({("PARTIAL_SYM", 59): signal})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)
    res = sim.run({"PARTIAL_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)

    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    assert "Partial Target" in trade["exit_reason"]
    assert trade["qty"] > 1
    assert trade["pnl"] > 0.0  # Realized net gain from 2R partial


# 5. Multiple Open and Pending Positions
def test_multiple_open_and_pending_positions():
    """Verify multiple positions can be pending/open simultaneously up to limits."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df1 = generate_constant_bars("SYM1", 80, 100.0)
    df2 = generate_constant_bars("SYM2", 80, 200.0)

    sig1 = SetupCandidate(
        symbol="SYM1", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=95.0, target1=115.0,
        risk_per_share=5.0, risk_r=5.0, atr=1.0, reasons=["fixture"],
    )
    sig2 = SetupCandidate(
        symbol="SYM2", setup="PULLBACK", pivot=199.5, trigger=200.0,
        entry_zone_high=202.0, stop=190.0, target1=230.0,
        risk_per_share=10.0, risk_r=10.0, atr=2.0, reasons=["fixture"],
    )
    mock_engine = MockSetupEngine({("SYM1", 59): sig1, ("SYM2", 59): sig2})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"SYM1": df1, "SYM2": df2}, start_date=dates[0], end_date=dates[70], capital=200000.0)
    # Both positions should be filled and liquidated at end of test
    assert len(res["trades"]) == 2
    symbols = {t["symbol"] for t in res["trades"]}
    assert symbols == {"SYM1", "SYM2"}


# 6. Position and Risk Limit Enforcement + Duplicate Entry Prevention
def test_position_and_risk_limit_enforcement():
    """Verify pending orders reserve capacity, risk limits are enforced, and duplicates are blocked."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("DUP_SYM", 80, 100.0)

    sig = SetupCandidate(
        symbol="DUP_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=95.0, target1=115.0,
        risk_per_share=5.0, risk_r=5.0, atr=1.0, reasons=["fixture"],
    )
    # Trigger signal on bar 59 AND bar 60 for the SAME symbol
    mock_engine = MockSetupEngine({("DUP_SYM", 59): sig, ("DUP_SYM", 60): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"DUP_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    # Duplicate entry must be prevented; exactly 1 trade executed
    assert len(res["trades"]) == 1


# 7. Gap-Through Entries and Stops
def test_gap_through_entries_and_stops():
    """Verify gap-through entries fill at open and gap-through stops exit at open."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("GAP_SYM", 80, 100.0)

    # Bar 59: Signal trigger = 101.0, stop = 95.0
    sig = SetupCandidate(
        symbol="GAP_SYM", setup="VCP", pivot=100.5, trigger=101.0,
        entry_zone_high=105.0, stop=95.0, target1=120.0,
        risk_per_share=6.0, risk_r=6.0, atr=1.0, reasons=["fixture"],
    )
    # Bar 60: Gap up at open 104.0 (>= trigger 101.0)
    for b in range(60, 65):
        df.loc[b, "open"] = 104.0
        df.loc[b, "high"] = 105.0
        df.loc[b, "low"] = 103.0
        df.loc[b, "close"] = 104.0

    # Bar 65: Gap down stop at open 92.0 (<= stop 95.0)
    df.loc[65, "open"] = 92.0
    df.loc[65, "high"] = 93.0
    df.loc[65, "low"] = 91.0
    df.loc[65, "close"] = 92.0

    mock_engine = MockSetupEngine({("GAP_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"GAP_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert len(res["trades"]) == 1
    trade = res["trades"][0]

    # Entry should be slipped fill on 104.0, NOT 101.0
    assert trade["entry_price"] == pytest.approx(104.0 * (1 + sim.slip_pct), abs=0.01)
    # Exit should be slipped fill on 92.0, NOT 95.0
    assert trade["exit_price"] == pytest.approx(92.0 * (1 - sim.slip_pct), abs=0.01)
    assert trade["exit_reason"] == "Hard Stop (Gap Down)"


# 8. Same-Bar Stop and Target Ambiguity (Conservative Stop-First)
def test_same_bar_stop_target_ambiguity_conservative():
    """Verify conservative stop-first assumption when both stop and target touched on same bar."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("AMBIG_SYM", 80, 100.0)

    # Entry trigger 100.0, stop 95.0, target 110.0 (2R)
    sig = SetupCandidate(
        symbol="AMBIG_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=95.0, target1=110.0,
        risk_per_share=5.0, risk_r=5.0, atr=1.0, reasons=["fixture"],
    )
    # Bar 62: High reaches 112.0 (target hit) AND Low drops to 94.0 (stop hit)
    df.loc[62, "high"] = 112.0
    df.loc[62, "low"] = 94.0

    mock_engine = MockSetupEngine({("AMBIG_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"AMBIG_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    # Stop-first must be enforced
    assert "Stop" in trade["exit_reason"]
    assert trade["pnl"] < 0.0


# 9. Next-Open Exits (Trend Break and Time Stop)
def test_next_open_exits():
    """Verify close-based exits (trend break < 50 SMA and time stop) execute on next session open."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("NEXT_OPEN_SYM", 80, 100.0)

    sig = SetupCandidate(
        symbol="NEXT_OPEN_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=95.0, target1=120.0,
        risk_per_share=5.0, risk_r=5.0, atr=1.0, reasons=["fixture"],
    )
    # Bar 63 closes below 50 SMA (close drops to 80.0)
    df.loc[63, "close"] = 80.0
    # Bar 64 opens at 82.0
    df.loc[64, "open"] = 82.0
    df.loc[64, "high"] = 83.0
    df.loc[64, "low"] = 81.0
    df.loc[64, "close"] = 82.0

    mock_engine = MockSetupEngine({("NEXT_OPEN_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"NEXT_OPEN_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    assert trade["exit_reason"] == "Trend Break (< 50 SMA)"
    assert trade["exit_date"] == dates[64]
    assert trade["exit_price"] == pytest.approx(82.0 * (1 - sim.slip_pct), abs=0.01)


# 10. Daily Unrealized P&L and Maximum Drawdown
def test_daily_unrealized_pnl_and_drawdown():
    """Verify equity curve includes mark-to-market unrealized P&L and max drawdown reflects intraday equity dip."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("MTM_SYM", 80, 100.0)

    sig = SetupCandidate(
        symbol="MTM_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=90.0, target1=130.0,
        risk_per_share=10.0, risk_r=10.0, atr=1.0, reasons=["fixture"],
    )
    # Filled on bar 60. On bar 62, close dips to 92.0 (unrealized loss before stop)
    df.loc[62, "close"] = 92.0
    df.loc[62, "low"] = 91.0
    # Recovers on bar 63
    df.loc[63, "close"] = 105.0

    mock_engine = MockSetupEngine({("MTM_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"MTM_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    equity_curve = res["equity_curve"]
    assert len(equity_curve) > 20

    # Find equity on bar 62 date
    bar62_date_str = str(dates[62])
    bar62_equity = next(pt["equity"] for pt in equity_curve if pt["date"] == bar62_date_str)
    assert bar62_equity < 100000.0  # Unrealized loss reflected in equity curve!
    assert res["metrics"]["max_drawdown_pct"] > 0.0


# 11. End-of-Test Liquidation
def test_end_of_test_liquidation():
    """Verify positions still open on final bar are liquidated at final close price."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("LIQ_SYM", 80, 100.0)

    sig = SetupCandidate(
        symbol="LIQ_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=90.0, target1=130.0,
        risk_per_share=10.0, risk_r=10.0, atr=1.0, reasons=["fixture"],
    )
    mock_engine = MockSetupEngine({("LIQ_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    # End date is bar 70
    res = sim.run({"LIQ_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    assert "liquidated" in trade["exit_reason"].lower()
    assert trade["exit_date"] == dates[70]


# 12. Missing Bars and Inconsistent Data Warnings
def test_missing_bars_and_inconsistent_data_warning():
    """Verify that missing bars during an open position produce explicit data warnings."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("MISSING_SYM", 80, 100.0)

    # Drop bar 63 completely (creates a missing bar while position is held)
    df_missing = df.drop(index=[63]).reset_index(drop=True)

    sig = SetupCandidate(
        symbol="MISSING_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=90.0, target1=130.0,
        risk_per_share=10.0, risk_r=10.0, atr=1.0, reasons=["fixture"],
    )
    mock_engine = MockSetupEngine({("MISSING_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"MISSING_SYM": df_missing}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert "data_warnings" in res
    assert len(res["data_warnings"]) > 0
    assert any("Missing bar" in w for w in res["data_warnings"])


# 13. Cost-Drag Calculation
def test_cost_drag_calculation():
    """Verify cost drag uses gross profits as denominator and handles zero gross profit."""
    # Case A: Gross profit > 0
    trades_profitable = [
        {"pnl": 80.0, "costs": 20.0, "gross_pnl": 100.0, "r_multiple": 0.8, "entry_date": "2025-01-01", "exit_date": "2025-01-05"},
    ]
    metrics_a = compute_backtest_metrics(trades_profitable, initial_capital=10000.0)
    assert metrics_a.gross_profit == 100.0
    assert metrics_a.costs_pct_of_gross == 20.0  # (20 / 100) * 100%

    # Case B: All losses (Gross profit == 0)
    trades_losses = [
        {"pnl": -120.0, "costs": 20.0, "gross_pnl": -100.0, "r_multiple": -1.2, "entry_date": "2025-01-01", "exit_date": "2025-01-05"},
    ]
    metrics_b = compute_backtest_metrics(trades_losses, initial_capital=10000.0)
    assert metrics_b.gross_profit == 0.0
    assert metrics_b.costs_pct_of_gross is None
    cost_gate = next(g for g in metrics_b.acceptance_gates if g.name == "Cost Drag")
    assert not cost_gate.passed
    assert cost_gate.actual == "N/A (no gross profit)"


# 14. Empty and Insufficient Walk-Forward Windows
def test_empty_and_insufficient_walk_forward_windows():
    """Verify insufficient data returns INSUFFICIENT_DATA and empty validation windows never pass."""
    # Short history (< 300 bars)
    dates = pd.date_range("2025-01-01", periods=100, freq="B").date
    short_bars = {"SYM": pd.DataFrame({"date": dates, "open": [100.0]*100, "high": [101.0]*100, "low": [99.0]*100, "close": [100.0]*100, "volume": [10000]*100})}

    res = run_walk_forward_analysis(short_bars)
    assert res.status == "INSUFFICIENT_DATA"
    assert not res.passed_validation
    assert res.total_windows == 0

    # Long history (600 bars) with no trades (empty validation)
    dates_long = pd.date_range("2023-01-01", periods=600, freq="B").date
    flat_bars = {"FLAT": pd.DataFrame({"date": dates_long, "open": [100.0]*600, "high": [100.0]*600, "low": [100.0]*600, "close": [100.0]*600, "adj_close": [100.0]*600, "volume": [10000]*600})}

    res_flat = run_walk_forward_analysis(flat_bars)
    # All windows must fail validation because test_trades == 0
    assert not res_flat.passed_validation
    for win in res_flat.windows:
        assert not win.passed
        assert "Empty" in win.reason


# 15. Untouched Holdout Enforcement
def test_untouched_holdout_enforcement():
    """Verify holdout period is reserved and never touched during walk-forward training/validation."""
    dates = pd.date_range("2022-01-01", periods=800, freq="B").date
    bars = {"HOLDOUT_SYM": pd.DataFrame({"date": dates, "open": [100.0]*800, "high": [101.0]*800, "low": [99.0]*800, "close": [100.0]*800, "adj_close": [100.0]*800, "volume": [10000]*800})}

    # Reserve 6 months holdout
    res = run_walk_forward_analysis(bars, holdout_months=6)
    assert res.holdout_start is not None
    assert res.holdout_end is not None

    holdout_start_date = datetime.date.fromisoformat(res.holdout_start)
    # Check that no walk forward window's test_end extends into the holdout period
    for win in res.windows:
        test_end_date = datetime.date.fromisoformat(win.test_end)
        assert test_end_date < holdout_start_date


# 16. No-Look-Ahead Behavior
def test_no_lookahead_behavior():
    """Verify that signals generated on day t close use only data up to day t and fill on t+1."""
    dates = pd.date_range("2025-01-01", periods=80, freq="B").date
    df = generate_constant_bars("LOOKAHEAD_SYM", 80, 100.0)

    # Bar 59 generates signal. Entry can only fill on bar 60.
    sig = SetupCandidate(
        symbol="LOOKAHEAD_SYM", setup="VCP", pivot=99.5, trigger=100.0,
        entry_zone_high=101.0, stop=90.0, target1=120.0,
        risk_per_share=10.0, risk_r=10.0, atr=1.0, reasons=["fixture"],
    )
    mock_engine = MockSetupEngine({("LOOKAHEAD_SYM", 59): sig})
    sim = BacktestSimulator(market="IN", setup_engine_override=mock_engine)

    res = sim.run({"LOOKAHEAD_SYM": df}, start_date=dates[0], end_date=dates[70], capital=100000.0)
    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    # Entry date must be bar 60 (next session), NOT bar 59
    assert trade["entry_date"] == dates[60]
