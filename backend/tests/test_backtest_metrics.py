from app.backtest.metrics import compute_backtest_metrics
from app.backtest.walkforward import run_walk_forward_analysis
import pandas as pd


def test_expectancy_uses_net_r_once_and_net_profit_factor_is_labeled_by_calculation():
    result = compute_backtest_metrics(
        [{"pnl": 90.0, "costs": 10.0, "r_multiple": 0.9, "entry_date": "2026-01-01", "exit_date": "2026-01-02"}],
        initial_capital=10000,
        years=1,
    )
    assert result.expectancy_r == 0.9
    assert result.profit_factor == 99.0
    assert result.costs_pct_of_gross == 10.0


def test_cost_drag_fails_when_there_is_no_gross_profit():
    result = compute_backtest_metrics(
        [{"pnl": -110.0, "costs": 10.0, "r_multiple": -1.1, "entry_date": "2026-01-01", "exit_date": "2026-01-02"}],
        initial_capital=10000,
        years=1,
    )
    cost_gate = next(gate for gate in result.acceptance_gates if gate.name == "Cost Drag")
    assert result.costs_pct_of_gross is None
    assert not cost_gate.passed
    assert cost_gate.actual == "N/A (no gross profit)"


def test_drawdown_duration_is_derived_from_trade_dates_not_a_constant():
    result = compute_backtest_metrics(
        [
            {"pnl": -10.0, "costs": 0.0, "r_multiple": -0.1, "entry_date": "2026-01-01", "exit_date": "2026-01-02"},
            {"pnl": -10.0, "costs": 0.0, "r_multiple": -0.1, "entry_date": "2026-01-03", "exit_date": "2026-01-10"},
            {"pnl": 30.0, "costs": 0.0, "r_multiple": 0.3, "entry_date": "2026-01-11", "exit_date": "2026-01-20"},
        ],
        initial_capital=10000,
        years=1,
    )
    assert result.max_drawdown_duration_days == 19


def test_walk_forward_with_insufficient_history_does_not_pass_automatically():
    dates = pd.date_range("2025-01-01", periods=100, freq="B").date
    bars = {"TEST": pd.DataFrame({"date": dates, "close": range(100)})}
    result = run_walk_forward_analysis(bars)
    assert result.total_windows == 0
    assert result.robustness_score_pct == 0.0
    assert not result.passed_validation
