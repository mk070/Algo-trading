import datetime
from typing import Dict, List, Optional
import pandas as pd
from pydantic import BaseModel

from app.backtest.metrics import BacktestMetrics, compute_backtest_metrics
from app.backtest.simulator import BacktestSimulator


class WalkForwardWindow(BaseModel):
    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_trades: int = 0
    test_trades: int = 0
    train_expectancy: float
    test_expectancy: float
    train_profit_factor: float
    test_profit_factor: float
    passed: bool
    reason: Optional[str] = None


class WalkForwardResult(BaseModel):
    status: str = "COMPLETED"  # "INSUFFICIENT_DATA", "PASSED", "FAILED"
    total_windows: int
    windows: List[WalkForwardWindow]
    robustness_score_pct: float
    passed_validation: bool
    trials_recorded: int = 1
    holdout_start: Optional[str] = None
    holdout_end: Optional[str] = None
    message: Optional[str] = None


def run_walk_forward_analysis(
    bars_data: Dict[str, pd.DataFrame],
    market: str = "IN",
    train_months: int = 12,
    test_months: int = 4,
    holdout_months: int = 0,
    trials_count: int = 1,
    setup_filter: str = "ALL",
    setup_engine_override: Optional[object] = None,
    capital: Optional[float] = None,
) -> WalkForwardResult:
    simulator = BacktestSimulator(market=market, setup_engine_override=setup_engine_override)

    # Collect all available dates
    all_dates = set()
    for df in bars_data.values():
        if df is not None and not df.empty:
            for d in df["date"]:
                all_dates.add(d)

    sorted_dates = sorted(list(all_dates))
    if len(sorted_dates) < 300:
        return WalkForwardResult(
            status="INSUFFICIENT_DATA",
            total_windows=0,
            windows=[],
            robustness_score_pct=0.0,
            passed_validation=False,
            trials_recorded=trials_count,
            message="Insufficient historical bars for walk-forward analysis (minimum 300 bars required).",
        )

    start_date = sorted_dates[0]
    total_end_date = sorted_dates[-1]

    # Reserve untouched holdout period if requested
    holdout_start_date = None
    if holdout_months > 0:
        holdout_start_date = total_end_date - datetime.timedelta(days=holdout_months * 30)
        usable_end_date = holdout_start_date - datetime.timedelta(days=1)
    else:
        usable_end_date = total_end_date

    windows: List[WalkForwardWindow] = []
    curr_start = start_date
    window_idx = 1

    while True:
        train_end = curr_start + datetime.timedelta(days=train_months * 30)
        test_start = train_end + datetime.timedelta(days=1)
        test_end = train_end + datetime.timedelta(days=test_months * 30)
        if test_end > usable_end_date:
            break

        # Run on train
        train_res = simulator.run(bars_data, start_date=curr_start, end_date=train_end, setup_filter=setup_filter, capital=capital)
        train_trades = len(train_res["trades"])
        train_exp = train_res["metrics"]["expectancy_r"]
        train_pf = train_res["metrics"]["profit_factor"]

        # Run on out-of-sample test
        test_res = simulator.run(bars_data, start_date=test_start, end_date=test_end, setup_filter=setup_filter, capital=capital)
        test_trades = len(test_res["trades"])
        test_exp = test_res["metrics"]["expectancy_r"]
        test_pf = test_res["metrics"]["profit_factor"]

        # Empty validation windows must NEVER pass
        if test_trades == 0:
            passed = False
            reason = "Empty validation window (0 trades executed)"
        elif test_exp <= 0 or test_pf < 1.0:
            passed = False
            reason = f"Failed expectancy ({test_exp:.2f}R <= 0) or profit factor ({test_pf:.2f} < 1.0)"
        else:
            passed = True
            reason = "Passed out-of-sample criteria"

        windows.append(
            WalkForwardWindow(
                window_index=window_idx,
                train_start=str(curr_start),
                train_end=str(train_end),
                test_start=str(test_start),
                test_end=str(test_end),
                train_trades=train_trades,
                test_trades=test_trades,
                train_expectancy=train_exp,
                test_expectancy=test_exp,
                train_profit_factor=train_pf,
                test_profit_factor=test_pf,
                passed=passed,
                reason=reason,
            )
        )

        curr_start = curr_start + datetime.timedelta(days=test_months * 30)
        window_idx += 1

    if not windows:
        return WalkForwardResult(
            status="INSUFFICIENT_DATA",
            total_windows=0,
            windows=[],
            robustness_score_pct=0.0,
            passed_validation=False,
            trials_recorded=trials_count,
            holdout_start=str(holdout_start_date) if holdout_start_date else None,
            holdout_end=str(total_end_date) if holdout_start_date else None,
            message="No complete walk-forward windows fit into the available date range.",
        )

    passed_count = sum(1 for w in windows if w.passed)
    robustness_pct = (passed_count / len(windows) * 100.0) if windows else 0.0
    passed_validation = bool(windows) and robustness_pct >= 70.0

    return WalkForwardResult(
        status="PASSED" if passed_validation else "FAILED",
        total_windows=len(windows),
        windows=windows,
        robustness_score_pct=round(robustness_pct, 1),
        passed_validation=passed_validation,
        trials_recorded=trials_count,
        holdout_start=str(holdout_start_date) if holdout_start_date else None,
        holdout_end=str(total_end_date) if holdout_start_date else None,
    )

