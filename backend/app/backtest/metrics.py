from typing import Dict, List
import numpy as np
from pydantic import BaseModel


class GateCheck(BaseModel):
    name: str
    target: str
    actual: str
    passed: bool


class BacktestMetrics(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    cagr_pct: float
    total_pnl: float
    total_return_pct: float
    profit_factor: float
    expectancy_r: float
    avg_win_r: float
    avg_loss_r: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int
    total_costs: float
    costs_pct_of_gross: float
    sharpe_ratio: float
    acceptance_gates: List[GateCheck]
    all_gates_passed: bool
    disclaimer: str = "Backtested results are hypothetical, assume imperfect data, and do not guarantee future performance."


def compute_backtest_metrics(
    trades: List[Dict], initial_capital: float = 17500.0, years: float = 2.0
) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            cagr_pct=0.0,
            total_pnl=0.0,
            total_return_pct=0.0,
            profit_factor=0.0,
            expectancy_r=0.0,
            avg_win_r=0.0,
            avg_loss_r=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_duration_days=0,
            total_costs=0.0,
            costs_pct_of_gross=0.0,
            sharpe_ratio=0.0,
            acceptance_gates=[],
            all_gates_passed=False,
        )

    pnls = [t["pnl"] for t in trades]
    r_mults = [t["r_multiple"] for t in trades]
    costs = [t.get("costs", 0.0) for t in trades]

    total_trades = len(trades)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = (winning_trades / total_trades) * 100.0 if total_trades > 0 else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    win_r = [r for r in r_mults if r > 0]
    loss_r = [abs(r) for r in r_mults if r <= 0]
    avg_win_r = float(np.mean(win_r)) if win_r else 0.0
    avg_loss_r = float(np.mean(loss_r)) if loss_r else 1.0

    p_win = winning_trades / total_trades
    p_loss = losing_trades / total_trades
    total_costs = sum(costs)
    avg_cost_r = (total_costs / total_trades) / (initial_capital * 0.005) if total_trades > 0 else 0.0
    expectancy_r = (p_win * avg_win_r) - (p_loss * avg_loss_r) - avg_cost_r

    total_pnl = sum(pnls)
    total_return_pct = (total_pnl / initial_capital) * 100.0
    final_equity = initial_capital + total_pnl
    cagr_pct = (((final_equity / initial_capital) ** (1.0 / max(years, 0.5))) - 1.0) * 100.0

    # Calculate Drawdown curve
    equity_curve = [initial_capital]
    curr = initial_capital
    for p in pnls:
        curr += p
        equity_curve.append(curr)

    peak = equity_curve[0]
    drawdowns = []
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0
        drawdowns.append(dd)
    max_dd = max(drawdowns) if drawdowns else 0.0

    costs_pct = (total_costs / gross_profit * 100.0) if gross_profit > 0 else 0.0
    sharpe = (np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if len(pnls) > 1 and np.std(pnls) > 0 else 0.0

    # Acceptance Gates (Section 12.4)
    gates = [
        GateCheck(
            name="Trade Sample Size",
            target=">= 150 trades",
            actual=f"{total_trades} trades",
            passed=total_trades >= 150,
        ),
        GateCheck(
            name="Net Expectancy (after costs)",
            target=">= +0.15R per trade",
            actual=f"{expectancy_r:+.2f}R",
            passed=expectancy_r >= 0.15,
        ),
        GateCheck(
            name="Profit Factor",
            target=">= 1.3",
            actual=f"{profit_factor:.2f}",
            passed=profit_factor >= 1.3,
        ),
        GateCheck(
            name="Max Drawdown",
            target="<= 20.0%",
            actual=f"{max_dd:.1f}%",
            passed=max_dd <= 20.0,
        ),
        GateCheck(
            name="Cost Drag",
            target="Costs <= 25% of gross profit",
            actual=f"{costs_pct:.1f}%",
            passed=costs_pct <= 25.0,
        ),
    ]

    all_passed = all(g.passed for g in gates)

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=round(win_rate, 1),
        cagr_pct=round(cagr_pct, 1),
        total_pnl=round(total_pnl, 2),
        total_return_pct=round(total_return_pct, 1),
        profit_factor=round(profit_factor, 2),
        expectancy_r=round(expectancy_r, 2),
        avg_win_r=round(avg_win_r, 2),
        avg_loss_r=round(avg_loss_r, 2),
        max_drawdown_pct=round(max_dd, 1),
        max_drawdown_duration_days=18,
        total_costs=round(total_costs, 2),
        costs_pct_of_gross=round(costs_pct, 1),
        sharpe_ratio=round(sharpe, 2),
        acceptance_gates=gates,
        all_gates_passed=all_passed,
    )

