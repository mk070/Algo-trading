import datetime
from typing import Dict, List, Optional
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
    costs_pct_of_gross: Optional[float]
    sharpe_ratio: float
    acceptance_gates: List[GateCheck]
    all_gates_passed: bool
    disclaimer: str = "Backtested results are hypothetical, assume imperfect data, and do not guarantee future performance."


def compute_backtest_metrics(
    trades: List[Dict], initial_capital: float = 17500.0, years: float = 2.0,
    equity_curve: Optional[List[Dict]] = None,
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
            costs_pct_of_gross=None,
            sharpe_ratio=0.0,
            acceptance_gates=[
                GateCheck(name="Trade Sample Size", target=">= 150 trades", actual="0 trades", passed=False),
                GateCheck(name="Net Expectancy (after costs)", target=">= +0.15R per trade", actual="N/A (no trades)", passed=False),
                GateCheck(name="Profit Factor", target=">= 1.3", actual="N/A (no trades)", passed=False),
                GateCheck(name="Max Drawdown", target="<= 20.0%", actual="0.0% (no closed trades)", passed=True),
                GateCheck(name="Cost Drag", target="Costs <= 25% of gross profit before costs", actual="N/A (no gross profit)", passed=False),
            ],
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

    # P&L and R multiples in SimulatedTrade are net of costs. Keep PF net as
    # well; gross profit before fees is calculated separately for cost drag.
    net_profit = sum(wins)
    net_loss = abs(sum(losses))
    profit_factor = (net_profit / net_loss) if net_loss > 0 else (99.0 if net_profit > 0 else 0.0)

    win_r = [r for r in r_mults if r > 0]
    loss_r = [abs(r) for r in r_mults if r <= 0]
    avg_win_r = float(np.mean(win_r)) if win_r else 0.0
    avg_loss_r = float(np.mean(loss_r)) if loss_r else 1.0

    total_costs = sum(costs)
    # r_multiple is already net of the full round-trip cost in the simulator.
    # Subtracting avg_cost_r again understated expectancy by one cost charge.
    expectancy_r = float(np.mean(r_mults)) if r_mults else 0.0

    total_pnl = sum(pnls)
    total_return_pct = (total_pnl / initial_capital) * 100.0
    final_equity = initial_capital + total_pnl
    cagr_pct = (((final_equity / initial_capital) ** (1.0 / max(years, 0.5))) - 1.0) * 100.0

    # Use daily marked-to-market equity when supplied; otherwise retain a
    # closed-trade fallback for standalone metric callers and fixtures.
    trade_equity_curve = [initial_capital]
    curr = initial_capital
    ordered_trades = sorted(trades, key=lambda t: str(t.get("exit_date", "")))
    for t in ordered_trades:
        p = float(t["pnl"])
        curr += p
        trade_equity_curve.append(curr)

    use_daily_curve = bool(equity_curve)
    drawdown_values = [float(point["equity"]) for point in equity_curve] if use_daily_curve else trade_equity_curve
    peak = drawdown_values[0]
    drawdowns = []
    for eq in drawdown_values:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0
        drawdowns.append(dd)
    max_dd = max(drawdowns) if drawdowns else 0.0

    def as_date(value):
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        try:
            return datetime.date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    first_day = as_date(equity_curve[0].get("date")) if use_daily_curve else (as_date(ordered_trades[0].get("entry_date")) if ordered_trades else None)
    peak_date = first_day
    current_equity = initial_capital
    peak_equity = initial_capital
    max_dd_duration_days = 0
    underwater_since = None
    last_trade_day = first_day
    if use_daily_curve:
        dd_points = equity_curve
    else:
        fallback_equity = initial_capital
        dd_points = []
        for trade in ordered_trades:
            fallback_equity += float(trade["pnl"])
            dd_points.append({"date": trade.get("exit_date"), "equity": fallback_equity})
    for point in dd_points:
        current_equity = float(point["equity"])
        day = as_date(point.get("date"))
        if day is None:
            continue
        last_trade_day = day
        if current_equity >= peak_equity:
            if underwater_since is not None:
                max_dd_duration_days = max(max_dd_duration_days, (day - underwater_since).days)
                underwater_since = None
            peak_equity = current_equity
            peak_date = day
        elif peak_date is not None:
            if underwater_since is None:
                underwater_since = peak_date
            max_dd_duration_days = max(max_dd_duration_days, (day - underwater_since).days)
    if underwater_since is not None and last_trade_day is not None:
        max_dd_duration_days = max(max_dd_duration_days, (last_trade_day - underwater_since).days)

    gross_profit_before_costs = sum(max(float(t["pnl"]) + float(t.get("costs", 0.0)), 0.0) for t in trades)
    costs_pct = (total_costs / gross_profit_before_costs * 100.0) if gross_profit_before_costs > 0 else None
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
            actual=f"{max_dd:.1f}%" if use_daily_curve else f"{max_dd:.1f}% (closed trades)",
            passed=max_dd <= 20.0,
        ),
        GateCheck(
            name="Cost Drag",
            target="Costs <= 25% of gross profit before costs",
            actual=f"{costs_pct:.1f}%" if costs_pct is not None else "N/A (no gross profit)",
            passed=costs_pct is not None and costs_pct <= 25.0,
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
        max_drawdown_duration_days=max_dd_duration_days,
        total_costs=round(total_costs, 2),
        costs_pct_of_gross=round(costs_pct, 1) if costs_pct is not None else None,
        sharpe_ratio=round(sharpe, 2),
        acceptance_gates=gates,
        all_gates_passed=all_passed,
    )

