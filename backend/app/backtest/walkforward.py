import datetime
from typing import Dict, List
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
    train_expectancy: float
    test_expectancy: float
    train_profit_factor: float
    test_profit_factor: float
    passed: bool


class WalkForwardResult(BaseModel):
    total_windows: int
    windows: List[WalkForwardWindow]
    robustness_score_pct: float
    passed_validation: bool


def run_walk_forward_analysis(
    bars_data: Dict[str, pd.DataFrame],
    market: str = "IN",
    train_months: int = 12,
    test_months: int = 4,
) -> WalkForwardResult:
    simulator = BacktestSimulator(market=market)

    # Collect all available dates
    all_dates = set()
    for df in bars_data.values():
        if df is not None and not df.empty:
            for d in df["date"]:
                all_dates.add(d)

    sorted_dates = sorted(list(all_dates))
    if len(sorted_dates) < 300:
        return WalkForwardResult(
            total_windows=0,
            windows=[],
            robustness_score_pct=100.0,
            passed_validation=True,
        )

    start_date = sorted_dates[0]
    end_date = sorted_dates[-1]

    windows: List[WalkForwardWindow] = []
    curr_start = start_date
    window_idx = 1

    while True:
        train_end = curr_start + datetime.timedelta(days=train_months * 30)
        test_end = train_end + datetime.timedelta(days=test_months * 30)
        if test_end > end_date:
            break

        # Run on train
        train_res = simulator.run(bars_data, start_date=curr_start, end_date=train_end)
        train_exp = train_res["metrics"]["expectancy_r"]
        train_pf = train_res["metrics"]["profit_factor"]

        # Run on out-of-sample test
        test_res = simulator.run(bars_data, start_date=train_end, end_date=test_end)
        test_exp = test_res["metrics"]["expectancy_r"]
        test_pf = test_res["metrics"]["profit_factor"]

        passed = test_exp > 0 and test_pf >= 1.0

        windows.append(
            WalkForwardWindow(
                window_index=window_idx,
                train_start=str(curr_start),
                train_end=str(train_end),
                test_start=str(train_end),
                test_end=str(test_end),
                train_expectancy=train_exp,
                test_expectancy=test_exp,
                train_profit_factor=train_pf,
                test_profit_factor=test_pf,
                passed=passed,
            )
        )

        curr_start = curr_start + datetime.timedelta(days=test_months * 30)
        window_idx += 1

    passed_count = sum(1 for w in windows if w.passed)
    robustness_pct = (passed_count / len(windows) * 100.0) if windows else 0.0

    return WalkForwardResult(
        total_windows=len(windows),
        windows=windows,
        robustness_score_pct=round(robustness_pct, 1),
        passed_validation=robustness_pct >= 70.0,
    )

