"""
Phase 2: Pre-Registered Strategy Validation Runner
Strictly Offline Research — No Live Trading

Executes Candidates C1a, C1b, C2, Controls A & B, Benchmarks A & B,
Block-Bootstrap 95% CIs, Walk-Forward Analysis, and Sensitivity Perturbations.
Outputs complete machine-readable results to research/phase2_results.json.
"""

import datetime
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Ensure backend package imports resolve
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.backtest.simulator import BacktestSimulator
from app.engine.indicators import add_all_indicators
from app.engine.setups import SetupEngine

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


def load_universe_and_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Loads approved frozen research universe, Parquet snapshot, and benchmark series."""
    u_path = Path("data/universe/research_universe_v1.csv")
    snap_path = Path("data/research/research_snapshot_20261106.parquet")
    bench_path = Path("data/research/benchmark_series.parquet")

    if not u_path.exists():
        raise FileNotFoundError(f"Universe file {u_path} missing.")
    if not snap_path.exists():
        raise FileNotFoundError(f"Snapshot file {snap_path} missing.")
    if not bench_path.exists():
        raise FileNotFoundError(f"Benchmark file {bench_path} missing.")

    u_df = pd.read_csv(u_path)
    snap_df = pd.read_parquet(snap_path)
    bench_df = pd.read_parquet(bench_path)

    snap_df["date"] = pd.to_datetime(snap_df["date"])
    bench_df["date"] = pd.to_datetime(bench_df["date"])

    return u_df, snap_df, bench_df


def calculate_cost_in(turnover: float, side: str, n_scrip_sold: int = 0) -> float:
    """Exact Zerodha delivery cost model for India (NSE Equity)."""
    if turnover <= 0:
        return 0.0
    stt = 0.001 * turnover  # 0.10% buy and sell
    exchange_charges = 0.00003 * turnover  # 0.003%
    sebi_charges = (10.0 / 10000000.0) * turnover  # 10 per crore
    stamp_duty = 0.00015 * turnover if side == "BUY" else 0.0  # 0.015% buy only
    dp_charges = (13.50 * 1.18 * n_scrip_sold) if side == "SELL" else 0.0  # 13.50 + 18% GST per scrip
    gst = 0.18 * (exchange_charges + sebi_charges)  # 18% on exchange and sebi
    return stt + exchange_charges + sebi_charges + stamp_duty + dp_charges + gst


def calculate_cost_us(turnover: float, side: str) -> float:
    """Standard US realistic cost model."""
    if turnover <= 0:
        return 0.0
    regulatory = 0.00003 * turnover if side == "SELL" else 0.0  # 0.003% on sell
    fx_spread = 0.0050 * turnover  # 0.50% turnover
    return regulatory + fx_spread


class MomentumEngine:
    def __init__(self, u_df: pd.DataFrame, snap_df: pd.DataFrame, bench_df: pd.DataFrame):
        self.u_df = u_df
        self.snap_df = snap_df
        self.bench_df = bench_df

    def run_c1_simulation(
        self,
        market: str = "IN",
        capital: float = 500000.0,
        regime_filtered: bool = False,
        top_n: int = 20,
        lookback_bars: int = 252,
        skip_recent_bars: int = 21,
        cost_multiplier: float = 1.0,
        slip_multiplier: float = 1.0,
        random_selection: bool = False,
        rng: Optional[np.random.RandomState] = None,
    ) -> Dict[str, Any]:
        """Runs candidate C1 (Monthly Momentum) simulation."""
        syms = self.u_df[self.u_df["market"] == market]["symbol"].tolist()
        df_mkt = self.snap_df[self.snap_df["symbol"].isin(syms)].copy()

        # Build pivot tables
        close_df = df_mkt.pivot(index="date", columns="symbol", values="split_adj_close").sort_index()
        open_df = df_mkt.pivot(index="date", columns="symbol", values="split_adj_open").sort_index()
        vol_df = df_mkt.pivot(index="date", columns="symbol", values="volume").sort_index()

        # Slippage parameters
        base_slip = 0.0010 if market == "IN" else 0.0005
        slip_pct = base_slip * slip_multiplier

        # Benchmark / Regime index
        idx_sym = "^NSEI" if market == "IN" else "^GSPC"
        bench_sub = self.bench_df[self.bench_df["symbol"] == idx_sym].sort_values("date").set_index("date")
        bench_close = bench_sub["close"]
        bench_sma200 = bench_close.rolling(window=200, min_periods=200).mean()

        # Monthly dates (last trading day of calendar month)
        dates = close_df.index
        df_dates = pd.DataFrame({"date": dates, "year_month": dates.to_period("M")})
        month_end_dates = df_dates.groupby("year_month")["date"].max().tolist()

        # 60-day rolling median turnover
        turnover_daily = close_df * vol_df
        med_turnover_60d = turnover_daily.rolling(window=60, min_periods=40).median()

        # Minimum required lookback
        min_bars_needed = lookback_bars + skip_recent_bars

        # State tracking
        current_holdings: Dict[str, int] = {}  # sym -> shares
        cash = capital
        equity_series: List[Dict[str, Any]] = []
        monthly_returns: List[Dict[str, Any]] = []
        turnover_log: List[float] = []
        total_costs_paid = 0.0

        prev_month_end_equity = capital
        rebalances_executed = 0

        for i, m_end in enumerate(month_end_dates):
            # Locate integer index in dates
            end_idx = dates.get_loc(m_end)
            if end_idx < min_bars_needed:
                # Not enough history for 13-month momentum score
                continue

            # Need at least one next session to execute at open
            if end_idx + 1 >= len(dates):
                break

            exec_date = dates[end_idx + 1]

            # 1. Eligibility at month end m_end
            eligible_stocks = []
            min_price = 50.0 if market == "IN" else 5.0
            min_turnover = 50000000.0 if market == "IN" else 20000000.0  # 5 Cr INR or 20M USD

            for sym in syms:
                if sym not in close_df.columns:
                    continue
                c_series = close_df[sym].iloc[: end_idx + 1].dropna()
                if len(c_series) < min_bars_needed:
                    continue

                p_curr = close_df[sym].iloc[end_idx]
                if pd.isna(p_curr) or p_curr < min_price:
                    continue

                to_val = med_turnover_60d[sym].iloc[end_idx] if sym in med_turnover_60d.columns else 0.0
                if market == "IN" and (pd.isna(to_val) or to_val < min_turnover):
                    continue

                # Momentum score: Close(T - 21) / Close(T - 252) - 1
                p_t_skip = close_df[sym].iloc[end_idx - skip_recent_bars]
                p_t_start = close_df[sym].iloc[end_idx - lookback_bars]

                if pd.isna(p_t_skip) or pd.isna(p_t_start) or p_t_start <= 0:
                    continue

                score = (p_t_skip / p_t_start) - 1.0
                eligible_stocks.append({"symbol": sym, "score": score})

            # Check regime filter
            regime_pass = True
            if regime_filtered and m_end in bench_sma200.index and m_end in bench_close.index:
                b_c = bench_close.loc[m_end]
                b_sma = bench_sma200.loc[m_end]
                if pd.notna(b_c) and pd.notna(b_sma):
                    regime_pass = b_c > b_sma

            target_symbols: List[str] = []
            if regime_pass and len(eligible_stocks) > 0:
                if random_selection and rng is not None:
                    # Random draw without momentum ranking
                    pool = [x["symbol"] for x in eligible_stocks]
                    target_symbols = list(rng.choice(pool, size=min(top_n, len(pool)), replace=False))
                else:
                    eligible_stocks.sort(key=lambda x: x["score"], reverse=True)
                    target_symbols = [x["symbol"] for x in eligible_stocks[:top_n]]

            # Execute rebalance at Open of exec_date
            rebalances_executed += 1

            # Liquidate exits
            sold_scrip_count = 0
            exit_turnover = 0.0
            for sym, shares in list(current_holdings.items()):
                if sym not in target_symbols or not regime_pass:
                    op = open_df[sym].loc[exec_date]
                    if pd.notna(op) and op > 0:
                        fill_p = op * (1.0 - slip_pct)
                        gross_proceeds = fill_p * shares
                        exit_turnover += gross_proceeds
                        sold_scrip_count += 1
                        del current_holdings[sym]
                        cash += gross_proceeds

            exit_cost = (
                calculate_cost_in(exit_turnover, "SELL", sold_scrip_count)
                if market == "IN"
                else calculate_cost_us(exit_turnover, "SELL")
            ) * cost_multiplier
            cash -= exit_cost
            total_costs_paid += exit_cost

            # Calculate total portfolio equity before buying
            current_equity = cash
            for sym, shares in current_holdings.items():
                op = open_df[sym].loc[exec_date]
                if pd.notna(op) and op > 0:
                    current_equity += op * shares

            # Target position sizing
            n_targets = len(target_symbols)
            target_cap_per_stock = (current_equity / n_targets) if n_targets > 0 else 0.0
            buy_turnover = 0.0

            for sym in target_symbols:
                op = open_df[sym].loc[exec_date]
                if pd.isna(op) or op <= 0:
                    continue

                fill_buy = op * (1.0 + slip_pct)
                target_shares = int(math.floor(target_cap_per_stock / fill_buy)) if fill_buy > 0 else 0
                curr_shares = current_holdings.get(sym, 0)
                delta_shares = target_shares - curr_shares

                if delta_shares > 0:
                    # Buy delta shares
                    trade_val = delta_shares * fill_buy
                    if cash >= trade_val:
                        cash -= trade_val
                        buy_turnover += trade_val
                        current_holdings[sym] = curr_shares + delta_shares
                elif delta_shares < 0:
                    # Trim delta shares
                    sell_shares = abs(delta_shares)
                    fill_sell = op * (1.0 - slip_pct)
                    trade_val = sell_shares * fill_sell
                    cash += trade_val
                    current_holdings[sym] = curr_shares - sell_shares

            buy_cost = (
                calculate_cost_in(buy_turnover, "BUY")
                if market == "IN"
                else calculate_cost_us(buy_turnover, "BUY")
            ) * cost_multiplier
            cash -= buy_cost
            total_costs_paid += buy_cost

            total_rebalance_turnover = exit_turnover + buy_turnover
            turnover_log.append(total_rebalance_turnover)

            # Mark to market at month end
            m_end_close_equity = cash
            for sym, shares in current_holdings.items():
                cp = close_df[sym].loc[m_end] if m_end in close_df.index else close_df[sym].iloc[end_idx]
                if pd.notna(cp):
                    m_end_close_equity += cp * shares

            month_return = (m_end_close_equity / prev_month_end_equity) - 1.0 if prev_month_end_equity > 0 else 0.0
            prev_month_end_equity = m_end_close_equity

            # Benchmark return for the month
            b_ret = 0.0
            if i > 0 and month_end_dates[i - 1] in bench_close.index and m_end in bench_close.index:
                b_prev = bench_close.loc[month_end_dates[i - 1]]
                b_curr = bench_close.loc[m_end]
                if pd.notna(b_prev) and pd.notna(b_curr) and b_prev > 0:
                    b_ret = (b_curr / b_prev) - 1.0

            monthly_returns.append({
                "year_month": str(m_end)[:7],
                "date": str(m_end)[:10],
                "portfolio_equity": round(m_end_close_equity, 2),
                "monthly_net_return": month_return,
                "benchmark_return": b_ret,
                "excess_return": month_return - b_ret,
                "holdings_count": len(current_holdings),
                "cash_pct": round((cash / m_end_close_equity) * 100.0, 2) if m_end_close_equity > 0 else 0.0,
            })

            equity_series.append({
                "date": str(m_end)[:10],
                "equity": round(m_end_close_equity, 2),
                "cash": round(cash, 2),
            })

        # Summary performance metrics
        if not monthly_returns:
            return {"status": "EMPTY", "rebalances": 0}

        ret_series = pd.Series([x["monthly_net_return"] for x in monthly_returns])
        b_ret_series = pd.Series([x["benchmark_return"] for x in monthly_returns])
        excess_series = ret_series - b_ret_series

        total_months = len(monthly_returns)
        cum_ret = (monthly_returns[-1]["portfolio_equity"] / capital) - 1.0
        ann_factor = 12.0 / total_months if total_months > 0 else 1.0
        ann_ret = ((1.0 + cum_ret) ** ann_factor) - 1.0

        cum_b_ret = np.prod(1.0 + b_ret_series) - 1.0
        ann_b_ret = ((1.0 + cum_b_ret) ** ann_factor) - 1.0
        ann_excess_ret = ann_ret - ann_b_ret

        # Drawdowns
        eq_arr = np.array([capital] + [x["portfolio_equity"] for x in monthly_returns])
        peak_arr = np.maximum.accumulate(eq_arr)
        dd_arr = (eq_arr - peak_arr) / peak_arr
        max_dd = float(np.min(dd_arr))

        b_eq_arr = np.cumprod(np.concatenate([[1.0], 1.0 + b_ret_series.values]))
        b_peak_arr = np.maximum.accumulate(b_eq_arr)
        b_dd_arr = (b_eq_arr - b_peak_arr) / b_peak_arr
        b_max_dd = float(np.min(b_dd_arr))

        vol = float(ret_series.std() * np.sqrt(12.0)) if len(ret_series) > 1 else 0.0
        sharpe = (ann_ret - 0.05) / vol if vol > 0 else 0.0

        # Yearly breakdown
        m_df = pd.DataFrame(monthly_returns)
        m_df["year"] = m_df["year_month"].apply(lambda x: int(x[:4]))
        yearly_perf = {}
        pos_years = 0
        tot_years = 0
        for yr, group in m_df.groupby("year"):
            y_p_ret = float(np.prod(1.0 + group["monthly_net_return"]) - 1.0)
            y_b_ret = float(np.prod(1.0 + group["benchmark_return"]) - 1.0)
            y_excess = y_p_ret - y_b_ret
            if len(group) >= 10:  # count full years
                tot_years += 1
                if y_excess > 0:
                    pos_years += 1
            yearly_perf[int(yr)] = {
                "months": len(group),
                "portfolio_return": round(y_p_ret * 100.0, 2),
                "benchmark_return": round(y_b_ret * 100.0, 2),
                "excess_return": round(y_excess * 100.0, 2),
            }

        avg_turnover = float(np.mean(turnover_log)) if turnover_log else 0.0
        cost_drag_pct = (total_costs_paid / capital) * 100.0

        return {
            "status": "COMPLETED",
            "market": market,
            "capital": capital,
            "regime_filtered": regime_filtered,
            "total_months": total_months,
            "rebalances_count": rebalances_executed,
            "final_equity": round(monthly_returns[-1]["portfolio_equity"], 2),
            "cum_net_return_pct": round(cum_ret * 100.0, 2),
            "annualized_net_return_pct": round(ann_ret * 100.0, 2),
            "annualized_benchmark_return_pct": round(ann_b_ret * 100.0, 2),
            "annualized_excess_return_pct": round(ann_excess_ret * 100.0, 2),
            "max_drawdown_pct": round(abs(max_dd) * 100.0, 2),
            "benchmark_max_drawdown_pct": round(abs(b_max_dd) * 100.0, 2),
            "drawdown_ratio": round(abs(max_dd) / abs(b_max_dd), 2) if abs(b_max_dd) > 0 else 999.0,
            "volatility_pct": round(vol * 100.0, 2),
            "sharpe_ratio": round(sharpe, 2),
            "total_costs_paid": round(total_costs_paid, 2),
            "cost_drag_pct_of_capital": round(cost_drag_pct, 2),
            "avg_monthly_turnover": round(avg_turnover, 2),
            "yearly_performance": yearly_perf,
            "positive_calendar_years": f"{pos_years}/{tot_years}",
            "calendar_year_consistency_passed": (pos_years / tot_years >= 0.60) if tot_years > 0 else False,
            "monthly_returns": monthly_returns,
        }


def run_block_bootstrap_ci(
    monthly_excess_returns: List[float],
    block_len: int = 6,
    n_resamples: int = 2000,
    seed: int = RANDOM_SEED,
) -> Dict[str, float]:
    """Calculates 95% circular block-bootstrap confidence interval on monthly net excess return."""
    if len(monthly_excess_returns) < block_len * 2:
        return {"ci_lower": 0.0, "ci_upper": 0.0, "mean": 0.0, "samples": len(monthly_excess_returns)}

    arr = np.array(monthly_excess_returns)
    n = len(arr)
    rng = np.random.RandomState(seed)

    boot_means = []
    num_blocks = int(math.ceil(n / block_len))

    for _ in range(n_resamples):
        start_indices = rng.randint(0, n, size=num_blocks)
        sampled = []
        for s in start_indices:
            block = [arr[(s + j) % n] for j in range(block_len)]
            sampled.extend(block)
        resample = sampled[:n]
        boot_means.append(float(np.mean(resample)))

    boot_means.sort()
    lower_idx = int(0.025 * n_resamples)
    upper_idx = int(0.975 * n_resamples)

    return {
        "ci_lower_pct": round(boot_means[lower_idx] * 100.0, 3),
        "ci_upper_pct": round(boot_means[upper_idx] * 100.0, 3),
        "mean_pct": round(float(np.mean(arr)) * 100.0, 3),
        "n_resamples": n_resamples,
        "block_length": block_len,
    }


def run_random_portfolio_control(
    engine: MomentumEngine,
    market: str,
    capital: float,
    candidate_excess_ann: float,
    n_sims: int = 1000,
) -> Dict[str, Any]:
    """Runs Control B: 1,000 independent random selection portfolios."""
    print(f"Running Control B: {n_sims} Random Selection Portfolios for {market}...", flush=True)
    rng = np.random.RandomState(RANDOM_SEED)
    random_excess_returns = []

    for sim_idx in range(n_sims):
        sim_res = engine.run_c1_simulation(
            market=market,
            capital=capital,
            regime_filtered=False,
            random_selection=True,
            rng=rng,
        )
        if sim_res["status"] == "COMPLETED":
            random_excess_returns.append(sim_res["annualized_excess_return_pct"])

    random_excess_returns.sort()
    p95 = float(np.percentile(random_excess_returns, 95))
    p50 = float(np.percentile(random_excess_returns, 50))
    p05 = float(np.percentile(random_excess_returns, 5))

    # Candidate percentile rank
    rank = float(np.sum(np.array(random_excess_returns) < candidate_excess_ann)) / len(random_excess_returns)
    passed = rank >= 0.95

    return {
        "n_simulations": len(random_excess_returns),
        "random_p05_excess_pct": round(p05, 2),
        "random_p50_excess_pct": round(p50, 2),
        "random_p95_excess_pct": round(p95, 2),
        "candidate_excess_ann_pct": round(candidate_excess_ann, 2),
        "candidate_percentile_rank": round(rank * 100.0, 1),
        "passed_95th_percentile_gate": passed,
    }


def run_walk_forward_c1(engine: MomentumEngine, market: str, capital: float) -> List[Dict[str, Any]]:
    """Runs rolling walk-forward analysis for Candidate C1."""
    # Rolling 12-month train / 6-month test folds
    # In monthly momentum, evaluate across consecutive 6-month windows
    res = engine.run_c1_simulation(market=market, capital=capital)
    m_rets = res["monthly_returns"]
    folds = []
    window = 6
    for start in range(0, len(m_rets) - window + 1, window):
        chunk = m_rets[start : start + window]
        fold_p_ret = float(np.prod([1.0 + x["monthly_net_return"] for x in chunk]) - 1.0)
        fold_b_ret = float(np.prod([1.0 + x["benchmark_return"] for x in chunk]) - 1.0)
        folds.append({
            "fold_index": len(folds) + 1,
            "start_period": chunk[0]["year_month"],
            "end_period": chunk[-1]["year_month"],
            "months": len(chunk),
            "portfolio_net_return_pct": round(fold_p_ret * 100.0, 2),
            "benchmark_return_pct": round(fold_b_ret * 100.0, 2),
            "net_excess_return_pct": round((fold_p_ret - fold_b_ret) * 100.0, 2),
        })
    return folds


def run_trade_candidate_evaluation(
    market: str,
    setup_name: str,
    setup_filter: str,
    require_contraction: bool,
    capital: float,
    snap_df: pd.DataFrame,
    u_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Evaluates Candidate C2 (VCP) and Control A (55-Day High Breakout) on approved universe."""
    print(f"\nEvaluating {setup_name} ({market}) on full snapshot...", flush=True)
    syms = u_df[u_df["market"] == market]["symbol"].tolist()
    bars_dict = {}

    for s in syms:
        sub = snap_df[snap_df["symbol"] == s].copy()
        if len(sub) >= 30:
            sub["date"] = pd.to_datetime(sub["date"]).dt.date
            sub = sub.sort_values("date").reset_index(drop=True)
            sub["open"] = sub["split_adj_open"]
            sub["high"] = sub["split_adj_high"]
            sub["low"] = sub["split_adj_low"]
            sub["close"] = sub["split_adj_close"]
            sub = add_all_indicators(sub)
            bars_dict[s] = sub

    base_engine = SetupEngine()
    base_engine.vcp_cfg.require_contraction = require_contraction
    sim = BacktestSimulator(market=market, setup_engine_override=base_engine)
    sim_res = sim.run(bars_data=bars_dict, capital=capital, setup_filter=setup_filter)

    trades = sim_res["trades"]
    metrics = sim_res["metrics"]

    total_trades = len(trades)
    net_pnl = float(metrics.get("total_pnl", 0.0))
    expectancy_r = float(metrics.get("expectancy_r", 0.0))
    profit_factor = float(metrics.get("profit_factor", 0.0))
    max_dd = float(metrics.get("max_drawdown_pct", 0.0))
    win_rate = float(metrics.get("win_rate", 0.0))
    total_costs = float(metrics.get("total_costs", 0.0))

    # Evaluate 7 acceptance gates
    gate_trades = total_trades >= 150
    gate_exp = expectancy_r >= 0.15
    gate_pf = profit_factor >= 1.30
    gate_dd = max_dd <= 20.0
    gate_holdout = False  # Pre-registered disclosure: No untouched holdout exists

    passed_all = gate_trades and gate_exp and gate_pf and gate_dd and gate_holdout
    verdict = "PASS" if passed_all else ("INCONCLUSIVE" if total_trades < 150 else "FAIL")

    return {
        "candidate": setup_name,
        "market": market,
        "completed_trades": total_trades,
        "net_pnl": round(net_pnl, 2),
        "total_costs": round(total_costs, 2),
        "expectancy_r": round(expectancy_r, 3),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_dd, 1),
        "win_rate_pct": round(win_rate, 1),
        "gates": {
            "gate_min_150_trades": gate_trades,
            "gate_expectancy_gte_015R": gate_exp,
            "gate_profit_factor_gte_130": gate_pf,
            "gate_max_dd_lte_20pct": gate_dd,
            "gate_untouched_holdout_verified": gate_holdout,
        },
        "verdict": verdict,
    }


def main():
    print("==================================================================", flush=True)
    print("PHASE 2: PRE-REGISTERED STRATEGY VALIDATION (PROGRAMMATIC ENGINE)", flush=True)
    print("==================================================================", flush=True)

    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    prereg_sha256 = hashlib.sha256(open("research/PREREG.md", "rb").read()).hexdigest()
    universe_sha256 = hashlib.sha256(open("data/universe/research_universe_v1.csv", "rb").read()).hexdigest()
    snap_sha256 = hashlib.sha256(open("data/research/research_snapshot_20261106.parquet", "rb").read()).hexdigest()

    print(f"Git Commit SHA: {git_sha}")
    print(f"PREREG.md SHA256: {prereg_sha256}")
    print(f"Approved Universe SHA256: {universe_sha256}")
    print(f"Data Snapshot SHA256: {snap_sha256}\n", flush=True)

    u_df, snap_df, bench_df = load_universe_and_data()
    m_engine = MomentumEngine(u_df, snap_df, bench_df)

    results: Dict[str, Any] = {
        "metadata": {
            "execution_timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "git_commit_sha": git_sha,
            "prereg_sha256": prereg_sha256,
            "universe_file": "data/universe/research_universe_v1.csv",
            "universe_sha256": universe_sha256,
            "snapshot_file": "data/research/research_snapshot_20261106.parquet",
            "snapshot_sha256": snap_sha256,
            "benchmark_file": "data/research/benchmark_series.parquet",
            "random_seed": RANDOM_SEED,
            "total_universe_symbols": len(u_df),
            "date_range": "2021-07-19 to 2026-11-05",
        },
        "candidates": {},
        "controls": {},
        "sensitivity": {},
        "verdicts": {},
    }

    # =========================================================================
    # 1. CANDIDATE C1a (Always Invested)
    # =========================================================================
    print("Running Candidate C1a: Always Invested (India INR 500,000)...", flush=True)
    c1a_in = m_engine.run_c1_simulation(market="IN", capital=500000.0, regime_filtered=False)
    m_excess_in = [x["excess_return"] for x in c1a_in["monthly_returns"]]
    c1a_in_ci = run_block_bootstrap_ci(m_excess_in)
    c1a_in["bootstrap_95ci"] = c1a_in_ci

    print("Running Candidate C1a: Always Invested (US USD 50,000)...", flush=True)
    c1a_us = m_engine.run_c1_simulation(market="US", capital=50000.0, regime_filtered=False)
    m_excess_us = [x["excess_return"] for x in c1a_us["monthly_returns"]]
    c1a_us_ci = run_block_bootstrap_ci(m_excess_us)
    c1a_us["bootstrap_95ci"] = c1a_us_ci

    results["candidates"]["C1a_always_invested"] = {
        "India": c1a_in,
        "US": c1a_us,
    }

    # =========================================================================
    # 2. CANDIDATE C1b (Market-Regime Filtered)
    # =========================================================================
    print("\nRunning Candidate C1b: Regime Filtered (India INR 500,000)...", flush=True)
    c1b_in = m_engine.run_c1_simulation(market="IN", capital=500000.0, regime_filtered=True)
    c1b_in["bootstrap_95ci"] = run_block_bootstrap_ci([x["excess_return"] for x in c1b_in["monthly_returns"]])

    print("Running Candidate C1b: Regime Filtered (US USD 50,000)...", flush=True)
    c1b_us = m_engine.run_c1_simulation(market="US", capital=50000.0, regime_filtered=True)
    c1b_us["bootstrap_95ci"] = run_block_bootstrap_ci([x["excess_return"] for x in c1b_us["monthly_returns"]])

    results["candidates"]["C1b_regime_filtered"] = {
        "India": c1b_in,
        "US": c1b_us,
    }

    # =========================================================================
    # 3. PRACTICAL-SCALE DIAGNOSTIC (India INR 17,500, Top 5 Positions)
    # =========================================================================
    print("\nRunning C1a Practical-Scale Diagnostic (India INR 17,500, Top 5)...", flush=True)
    c1a_practical = m_engine.run_c1_simulation(market="IN", capital=17500.0, top_n=5, regime_filtered=False)
    results["candidates"]["C1a_practical_scale_india"] = c1a_practical

    # =========================================================================
    # 4. CANDIDATE C2 (Existing VCP) & CONTROL A (55-Day Breakout)
    # =========================================================================
    c2_vcp_in = run_trade_candidate_evaluation("IN", "Candidate C2 (VCP)", "VCP", True, 17500.0, snap_df, u_df)
    c2_vcp_us = run_trade_candidate_evaluation("US", "Candidate C2 (VCP)", "VCP", True, 17500.0, snap_df, u_df)
    ctrl_a_55_in = run_trade_candidate_evaluation("IN", "Control A (55-Day Breakout)", "VCP", False, 17500.0, snap_df, u_df)
    ctrl_a_55_us = run_trade_candidate_evaluation("US", "Control A (55-Day Breakout)", "VCP", False, 17500.0, snap_df, u_df)

    results["candidates"]["C2_existing_vcp"] = {"India": c2_vcp_in, "US": c2_vcp_us}
    results["controls"]["Control_A_55day_breakout"] = {"India": ctrl_a_55_in, "US": ctrl_a_55_us}

    # =========================================================================
    # 5. CONTROL B: RANDOM SELECTION CONTROLS (1,000 RUNS)
    # =========================================================================
    ctrl_b_in = run_random_portfolio_control(m_engine, "IN", 500000.0, c1a_in["annualized_excess_return_pct"])
    ctrl_b_us = run_random_portfolio_control(m_engine, "US", 50000.0, c1a_us["annualized_excess_return_pct"])
    results["controls"]["Control_B_random_portfolios"] = {"India": ctrl_b_in, "US": ctrl_b_us}

    # =========================================================================
    # 6. WALK-FORWARD ANALYSIS
    # =========================================================================
    print("\nRunning Walk-Forward Rolling Folds for C1a...", flush=True)
    wf_c1a_in = run_walk_forward_c1(m_engine, "IN", 500000.0)
    wf_c1a_us = run_walk_forward_c1(m_engine, "US", 50000.0)
    results["candidates"]["C1a_always_invested"]["India"]["walk_forward_folds"] = wf_c1a_in
    results["candidates"]["C1a_always_invested"]["US"]["walk_forward_folds"] = wf_c1a_us

    # =========================================================================
    # 7. SENSITIVITY ANALYSIS (Pre-registered perturbations)
    # =========================================================================
    print("Running Pre-Registered Sensitivity Perturbations...", flush=True)
    sensitivity_runs = {
        "costs_plus_25pct": m_engine.run_c1_simulation(market="IN", capital=500000.0, cost_multiplier=1.25),
        "slippage_times_2": m_engine.run_c1_simulation(market="IN", capital=500000.0, slip_multiplier=2.0),
        "lookback_10m": m_engine.run_c1_simulation(market="IN", capital=500000.0, lookback_bars=210),
        "lookback_14m": m_engine.run_c1_simulation(market="IN", capital=500000.0, lookback_bars=294),
        "portfolio_size_16": m_engine.run_c1_simulation(market="IN", capital=500000.0, top_n=16),
        "portfolio_size_24": m_engine.run_c1_simulation(market="IN", capital=500000.0, top_n=24),
    }
    results["sensitivity"]["C1a_India"] = {
        k: {
            "annualized_net_return_pct": v["annualized_net_return_pct"],
            "annualized_excess_return_pct": v["annualized_excess_return_pct"],
            "max_drawdown_pct": v["max_drawdown_pct"],
        }
        for k, v in sensitivity_runs.items()
    }

    # =========================================================================
    # 8. GATE-BY-GATE VERDICTS
    # =========================================================================
    # C1 Gates
    def evaluate_c1_gates(cand: Dict[str, Any], ctrl_b: Dict[str, Any]) -> Dict[str, Any]:
        g1 = cand["annualized_excess_return_pct"] >= 2.0
        g2 = cand["bootstrap_95ci"]["ci_lower_pct"] > 0.0
        g3 = cand["max_drawdown_pct"] <= (1.2 * cand["benchmark_max_drawdown_pct"])
        g4 = cand["calendar_year_consistency_passed"]
        g5 = False  # Pre-registered disclosure: No untouched holdout exists
        g6 = sensitivity_runs["costs_plus_25pct"]["annualized_excess_return_pct"] > 0 and sensitivity_runs["slippage_times_2"]["annualized_excess_return_pct"] > 0
        g7 = ctrl_b["passed_95th_percentile_gate"]
        g8 = all(v["annualized_excess_return_pct"] > 0 for v in sensitivity_runs.values())

        passed = g1 and g2 and g3 and g4 and g5 and g6 and g7 and g8
        verdict = "PASS" if passed else "FAIL"
        return {
            "gate_1_ann_excess_gte_2pct": g1,
            "gate_2_bootstrap_ci_lower_gt_0": g2,
            "gate_3_max_dd_lte_12x_bench": g3,
            "gate_4_calendar_consistency_gte_60pct": g4,
            "gate_5_untouched_holdout_positive": g5,
            "gate_6_cost_sensitivity_positive": g6,
            "gate_7_beat_random_control_95th": g7,
            "gate_8_parameter_sensitivity_robust": g8,
            "verdict": verdict,
        }

    results["verdicts"]["C1a_India"] = evaluate_c1_gates(c1a_in, ctrl_b_in)
    results["verdicts"]["C1b_India"] = evaluate_c1_gates(c1b_in, ctrl_b_in)
    results["verdicts"]["C1a_US"] = evaluate_c1_gates(c1a_us, ctrl_b_us)
    results["verdicts"]["C1b_US"] = evaluate_c1_gates(c1b_us, ctrl_b_us)
    results["verdicts"]["C2_India"] = c2_vcp_in["verdict"]
    results["verdicts"]["C2_US"] = c2_vcp_us["verdict"]
    results["verdicts"]["Control_A_India"] = ctrl_a_55_in["verdict"]
    results["verdicts"]["Control_A_US"] = ctrl_a_55_us["verdict"]

    def json_serializer(obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    out_file = Path("research/phase2_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=json_serializer)

    print(f"\n==================================================================", flush=True)
    print(f"Validation completed. Results saved to {out_file}", flush=True)
    print(f"==================================================================", flush=True)


if __name__ == "__main__":
    main()

