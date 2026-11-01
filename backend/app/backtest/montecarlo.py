import random
from typing import Dict, List
import numpy as np
from pydantic import BaseModel


class MonteCarloResult(BaseModel):
    iterations: int
    median_ending_equity: float
    pct_5th_ending_equity: float
    pct_95th_ending_equity: float
    median_max_drawdown_pct: float
    worst_case_max_drawdown_pct: float
    risk_of_ruin_pct: float  # probability of drawing down > 30%


def run_monte_carlo(
    trades: List[Dict], initial_capital: float = 17500.0, iterations: int = 1000
) -> MonteCarloResult:
    if not trades or len(trades) < 5:
        return MonteCarloResult(
            iterations=iterations,
            median_ending_equity=initial_capital,
            pct_5th_ending_equity=initial_capital,
            pct_95th_ending_equity=initial_capital,
            median_max_drawdown_pct=0.0,
            worst_case_max_drawdown_pct=0.0,
            risk_of_ruin_pct=0.0,
        )

    pnls = [t["pnl"] for t in trades]
    ending_equities = []
    max_drawdowns = []
    ruin_count = 0

    for _ in range(iterations):
        shuffled = random.sample(pnls, len(pnls))
        equity = initial_capital
        peak = equity
        max_dd = 0.0

        for p in shuffled:
            equity += p
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

        ending_equities.append(equity)
        max_drawdowns.append(max_dd)
        if max_dd >= 30.0:
            ruin_count += 1

    return MonteCarloResult(
        iterations=iterations,
        median_ending_equity=round(float(np.median(ending_equities)), 2),
        pct_5th_ending_equity=round(float(np.percentile(ending_equities, 5)), 2),
        pct_95th_ending_equity=round(float(np.percentile(ending_equities, 95)), 2),
        median_max_drawdown_pct=round(float(np.median(max_drawdowns)), 1),
        worst_case_max_drawdown_pct=round(float(np.max(max_drawdowns)), 1),
        risk_of_ruin_pct=round((ruin_count / iterations) * 100.0, 1),
    )

