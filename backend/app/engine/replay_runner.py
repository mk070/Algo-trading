"""
Historical Replay Runner & Multi-Strategy Comparator
Strictly Offline / Paper Simulation — No Live Broker Order Placement

Simulates:
1. Candidate 1: Market-Sector Regression-Alpha, Buffered 1–30 (INR 20,000)
2. Candidate 2: C1b Regime-Filtered 12–1 Momentum, Buffered 1–30 (INR 20,000)
3. Candidate 3: Relative-Plus-Absolute Strength (Dual Momentum), Buffered 1–30 (INR 20,000)
4. Candidate 4: Value-Based Strategy -> Reported as UNAVAILABLE (No point-in-time fundamental data)
5. Passive Benchmark: NIFTYBEES.NS Total Return ETF

Features:
- Identical historical dataset: data/research/research_snapshot_20261106.parquet
- Isolated accounting per candidate using shared DeterministicPaperBroker
- Normal-cost and 2x-cost stress scenarios
- Comprehensive metrics: Net Return, CAGR, Max Drawdown, Sharpe, Sortino, Win Rate, Profit Factor, Turnover, Costs, Slippage, Benchmark Excess, Monthly/Yearly returns
"""

import datetime
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.engine.calendars import get_expected_trading_days, is_exchange_holiday
from app.engine.paper_broker import DeterministicPaperBroker, safe_json_serialize

logger = logging.getLogger(__name__)


def compute_performance_metrics(
    daily_snapshots: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    initial_capital: float = 20000.0,
    risk_free_rate: float = 0.06,
) -> Dict[str, Any]:
    """Computes comprehensive quantitative performance and risk metrics."""
    if not daily_snapshots:
        return {
            "net_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
            "total_costs": 0.0,
            "total_slippage": 0.0,
            "avg_exposure_pct": 0.0,
            "monthly_returns": {},
            "yearly_returns": {},
        }

    df = pd.DataFrame(daily_snapshots)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    start_eq = initial_capital
    end_eq = float(df["total_equity"].iloc[-1])
    net_return_pct = ((end_eq / start_eq) - 1.0) * 100.0

    # CAGR calculation
    n_days = (df["date"].iloc[-1] - df["date"].iloc[0]).days
    n_years = n_days / 365.25 if n_days > 0 else 1.0
    cagr_pct = (((end_eq / start_eq) ** (1.0 / n_years)) - 1.0) * 100.0 if n_years > 0.1 and end_eq > 0 else net_return_pct

    # Max Drawdown
    peak = df["total_equity"].cummax()
    dd_series = (df["total_equity"] - peak) / peak * 100.0
    max_dd_pct = float(dd_series.min())

    # Daily returns & Sharpe / Sortino
    daily_rets = df["total_equity"].pct_change().dropna()
    rf_daily = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
    excess_rets = daily_rets - rf_daily

    if len(daily_rets) > 5 and daily_rets.std() > 1e-8:
        sharpe = float((excess_rets.mean() / daily_rets.std()) * math.sqrt(252))
        downside_rets = daily_rets[daily_rets < 0]
        downside_std = downside_rets.std() if len(downside_rets) > 1 else daily_rets.std()
        sortino = float((excess_rets.mean() / (downside_std if downside_std > 1e-8 else 1e-8)) * math.sqrt(252))
    else:
        sharpe = 0.0
        sortino = 0.0

    # Trade stats
    closed_trades = [t for t in trades if t.get("side") == "SELL"]
    n_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.get("realized_pnl", 0.0) > 0]
    losses = [t for t in closed_trades if t.get("realized_pnl", 0.0) < 0]

    win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
    gross_gains = sum(t.get("realized_pnl", 0.0) for t in wins)
    gross_losses = abs(sum(t.get("realized_pnl", 0.0) for t in losses))
    profit_factor = (gross_gains / gross_losses) if gross_losses > 0 else (99.0 if gross_gains > 0 else 0.0)

    total_costs = float(df["cumulative_costs"].iloc[-1]) if "cumulative_costs" in df.columns else 0.0
    total_slippage = float(df["cumulative_slippage"].iloc[-1]) if "cumulative_slippage" in df.columns else 0.0
    avg_exposure_pct = float(((df["total_equity"] - df["cash"]) / df["total_equity"] * 100.0).mean())

    # Monthly & Yearly returns
    df["year"] = df["date"].dt.year
    df["year_month"] = df["date"].dt.strftime("%Y-%m")

    monthly_returns = {}
    for ym, group in df.groupby("year_month"):
        m_start = float(group["total_equity"].iloc[0])
        m_end = float(group["total_equity"].iloc[-1])
        monthly_returns[ym] = round(((m_end / m_start) - 1.0) * 100.0, 2)

    yearly_returns = {}
    for yr, group in df.groupby("year"):
        y_start = float(group["total_equity"].iloc[0])
        y_end = float(group["total_equity"].iloc[-1])
        yearly_returns[str(yr)] = round(((y_end / y_start) - 1.0) * 100.0, 2)

    return {
        "net_return_pct": round(net_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "max_drawdown_pct": round(abs(max_dd_pct), 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "total_trades": n_trades,
        "total_costs": round(total_costs, 2),
        "cost_pct_of_capital": round((total_costs / initial_capital) * 100.0, 2),
        "total_slippage": round(total_slippage, 2),
        "avg_exposure_pct": round(avg_exposure_pct, 1),
        "monthly_returns": monthly_returns,
        "yearly_returns": yearly_returns,
    }


class HistoricalReplayRunner:
    """
    Executes historical replay across the frozen research snapshot for all 4 candidate strategies.
    """

    def __init__(
        self,
        snapshot_path: str = "data/research/research_snapshot_20261106.parquet",
        benchmark_path: str = "data/research/benchmark_series.parquet",
        universe_path: str = "data/universe/research_universe_v1.csv",
        output_dir: str = "research/cycle4/replay_state",
        initial_capital: float = 20000.0,
    ):
        self.snapshot_path = Path(snapshot_path)
        self.benchmark_path = Path(benchmark_path)
        self.universe_path = Path(universe_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.initial_capital = initial_capital

        if not self.snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot missing: {self.snapshot_path}")
        if not self.benchmark_path.exists():
            raise FileNotFoundError(f"Benchmark missing: {self.benchmark_path}")

        self.u_df = pd.read_csv(self.universe_path)
        self.in_u = self.u_df[self.u_df["market"] == "IN"].copy()
        self.symbols = self.in_u["symbol"].tolist()
        self.sector_map = dict(zip(self.in_u["symbol"], self.in_u["sector"]))
        sectors = set(self.sector_map.values())
        self.sector_to_syms = {sec: [s for s in self.symbols if self.sector_map[s] == sec] for sec in sectors}

    def load_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        logger.info("Loading frozen research snapshot and benchmark data...")
        snap_df = pd.read_parquet(self.snapshot_path)
        snap_df["date"] = pd.to_datetime(snap_df["date"])
        in_snap = snap_df[snap_df["symbol"].isin(self.symbols)].copy()

        close_pivot = in_snap.pivot(index="date", columns="symbol", values="split_adj_close").sort_index().ffill()
        open_pivot = in_snap.pivot(index="date", columns="symbol", values="split_adj_open").sort_index().ffill()
        vol_pivot = in_snap.pivot(index="date", columns="symbol", values="volume").sort_index().fillna(0)

        # Benchmark
        bench_df = pd.read_parquet(self.benchmark_path)
        bench_df["date"] = pd.to_datetime(bench_df["date"])
        nsei_series = bench_df[bench_df["symbol"] == "^NSEI"].sort_values("date").set_index("date")["close"].ffill()
        niftybees_series = bench_df[bench_df["symbol"] == "NIFTYBEES.NS"].sort_values("date").set_index("date")["close"].ffill()

        # Reindex index series to match snapshot dates
        common_dates = close_pivot.index
        nsei_series = nsei_series.reindex(common_dates).ffill()
        niftybees_series = niftybees_series.reindex(common_dates).ffill()

        returns_pivot = close_pivot.pct_change()
        return close_pivot, open_pivot, vol_pivot, returns_pivot, nsei_series, niftybees_series

    def evaluate_regime(self, nsei_series: pd.Series, end_idx: int) -> Tuple[bool, float, float, str]:
        sub = nsei_series.iloc[: end_idx + 1].dropna()
        if len(sub) < 200:
            return False, 0.0, 0.0, "INSUFFICIENT_HISTORY (<200 bars) -> 100% CASH"

        sma200 = float(sub.rolling(200, min_periods=200).mean().iloc[-1])
        latest_close = float(sub.iloc[-1])

        if np.isnan(sma200) or np.isnan(latest_close):
            return False, latest_close, sma200, "NAN_REGIME_OBSERVATION -> 100% CASH"

        is_bull = bool(latest_close > sma200)
        status = "BULL_REGIME (Close > SMA200)" if is_bull else "BEAR_REGIME (Close <= SMA200) -> 100% CASH"
        return is_bull, latest_close, sma200, status

    def score_candidate1_reg_alpha(
        self,
        close_df: pd.DataFrame,
        returns_df: pd.DataFrame,
        nsei_returns: pd.Series,
        med_to_60d: pd.Series,
        end_idx: int,
    ) -> List[Dict[str, Any]]:
        """Candidate 1: Market-Sector Regression-Alpha standardized score."""
        lookback = 252
        skip = 21
        if end_idx < lookback:
            return []

        start_idx = end_idx - lookback
        stop_idx = end_idx - skip
        rm_win = nsei_returns.iloc[start_idx : stop_idx + 1].values

        scores = []
        for sym in self.symbols:
            if sym not in close_df.columns:
                continue

            p_curr = close_df[sym].iloc[end_idx]
            if pd.isna(p_curr) or p_curr < 50.0:
                continue

            to_val = med_to_60d[sym] if sym in med_to_60d else 0.0
            if pd.isna(to_val) or to_val < 50000000.0:
                continue

            y = returns_df[sym].iloc[start_idx : stop_idx + 1].values
            if np.isnan(y).any() or np.isnan(rm_win).any():
                continue

            sec = self.sector_map[sym]
            other_syms = [s for s in self.sector_to_syms[sec] if s != sym and s in returns_df.columns]
            if other_syms:
                rs_win = returns_df[other_syms].iloc[start_idx : stop_idx + 1].mean(axis=1).values
                X = np.column_stack([np.ones_like(y), rm_win, rs_win])
            else:
                X = np.column_stack([np.ones_like(y), rm_win])

            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            alpha = float(coef[0])
            resids = y - (X @ coef)
            std_res = float(np.std(resids, ddof=1))

            if std_res > 1e-8:
                score = float((len(y) * alpha) / std_res)
                scores.append({"symbol": sym, "score": score})

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores

    def score_candidate2_c1b_momentum(
        self,
        close_df: pd.DataFrame,
        med_to_60d: pd.Series,
        end_idx: int,
    ) -> List[Dict[str, Any]]:
        """Candidate 2: C1b Baseline 12-1 momentum."""
        lookback = 252
        skip = 21
        if end_idx < lookback:
            return []

        start_idx = end_idx - lookback
        stop_idx = end_idx - skip

        scores = []
        for sym in self.symbols:
            if sym not in close_df.columns:
                continue

            p_curr = close_df[sym].iloc[end_idx]
            if pd.isna(p_curr) or p_curr < 50.0:
                continue

            to_val = med_to_60d[sym] if sym in med_to_60d else 0.0
            if pd.isna(to_val) or to_val < 50000000.0:
                continue

            p_start = close_df[sym].iloc[start_idx]
            p_stop = close_df[sym].iloc[stop_idx]
            if pd.isna(p_start) or pd.isna(p_stop) or p_start <= 0:
                continue

            score = float((p_stop / p_start) - 1.0)
            scores.append({"symbol": sym, "score": score})

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores

    def score_candidate3_dual_momentum(
        self,
        close_df: pd.DataFrame,
        med_to_60d: pd.Series,
        end_idx: int,
    ) -> List[Dict[str, Any]]:
        """
        Candidate 3: Relative-Plus-Absolute Strength (Dual Momentum).
        - Absolute Strength: Asset Close > 200 SMA AND 12-1 Return > 0
        - Relative Strength: Ranked by 12-1 Relative Momentum among absolute-passing scrips.
        """
        lookback = 252
        skip = 21
        if end_idx < lookback:
            return []

        start_idx = end_idx - lookback
        stop_idx = end_idx - skip

        scores = []
        for sym in self.symbols:
            if sym not in close_df.columns:
                continue

            p_curr = close_df[sym].iloc[end_idx]
            if pd.isna(p_curr) or p_curr < 50.0:
                continue

            to_val = med_to_60d[sym] if sym in med_to_60d else 0.0
            if pd.isna(to_val) or to_val < 50000000.0:
                continue

            sub_series = close_df[sym].iloc[: end_idx + 1]
            if len(sub_series) < 200:
                continue

            sma200 = float(sub_series.rolling(200, min_periods=200).mean().iloc[-1])
            p_start = close_df[sym].iloc[start_idx]
            p_stop = close_df[sym].iloc[stop_idx]
            if pd.isna(p_start) or pd.isna(p_stop) or p_start <= 0 or pd.isna(sma200):
                continue

            ret_12_1 = float((p_stop / p_start) - 1.0)

            # Absolute strength filter: Asset Return > 0 AND Price > 200 SMA
            if ret_12_1 <= 0.0 or p_curr <= sma200:
                continue

            scores.append({"symbol": sym, "score": ret_12_1})

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores

    def apply_retention_buffer(
        self,
        current_holdings: Dict[str, Any],
        ranked_candidates: List[Dict[str, Any]],
        regime_pass: bool,
        top_n: int = 20,
        buffer_band: int = 30,
    ) -> List[str]:
        if not regime_pass or not ranked_candidates:
            return []

        ranked_syms = [x["symbol"] for x in ranked_candidates]
        retained = [s for s in current_holdings.keys() if s in ranked_syms and ranked_syms.index(s) < buffer_band]
        target = list(retained)
        for s in ranked_syms:
            if len(target) >= top_n:
                break
            if s not in target:
                target.append(s)
        return target

    def run_replay(self, stress_multiplier: float = 1.0) -> Dict[str, Any]:
        """Runs historical replay simulation for all strategies."""
        prefix = "stress_" if stress_multiplier > 1.0 else "normal_"
        scenario_name = "2x Cost Stress Scenario" if stress_multiplier > 1.0 else "Normal Cost Base Scenario"
        logger.info(f"Starting Historical Replay ({scenario_name})...")

        close_df, open_df, vol_df, returns_df, nsei_series, niftybees_series = self.load_data()
        nsei_returns = nsei_series.pct_change()
        dates = close_df.index
        n_dates = len(dates)

        # Broker instances
        broker_dir = self.output_dir / f"broker_{prefix}run"
        broker = DeterministicPaperBroker(
            base_dir=str(broker_dir),
            slippage_pct=0.0010 * stress_multiplier,
            cost_stress_multiplier=stress_multiplier,
            max_positions=20,
            min_price=50.0,
            min_median_turnover_60d=50000000.0,
            max_volume_participation_pct=0.01,
        )

        acc_cand1 = broker.get_or_create_account(
            f"{prefix}cand1_reg_alpha_buf30",
            "Candidate 1: Market-Sector Regression-Alpha (Buf 1–30)",
            self.initial_capital,
        )
        acc_cand2 = broker.get_or_create_account(
            f"{prefix}cand2_c1b_buf30",
            "Candidate 2: C1b Baseline Momentum (Buf 1–30)",
            self.initial_capital,
        )
        acc_cand3 = broker.get_or_create_account(
            f"{prefix}cand3_dual_momentum_buf30",
            "Candidate 3: Relative-Plus-Absolute Strength (Buf 1–30)",
            self.initial_capital,
        )

        pending_rebalance: Dict[str, List[str]] = {
            "cand1": [],
            "cand2": [],
            "cand3": [],
        }
        signal_dates: Dict[str, str] = {
            "cand1": "",
            "cand2": "",
            "cand3": "",
        }

        # Daily simulation loop: start after 252 bars lookback
        start_bar = 252
        logger.info(f"Iterating {n_dates - start_bar} sessions from {dates[start_bar].date()} to {dates[-1].date()}...")

        for idx in range(start_bar, n_dates):
            cur_dt = dates[idx]
            date_str = str(cur_dt.date())

            # 1. Execute queued rebalance at Open
            today_opens = open_df.iloc[idx].to_dict()
            today_vols = vol_df.iloc[idx].to_dict()

            # 60d median turnover up to yesterday
            to_win = (close_df.iloc[max(0, idx - 60) : idx] * vol_df.iloc[max(0, idx - 60) : idx]).median()
            med_to_dict = to_win.to_dict()

            is_bull, nsei_close, nsei_sma200, regime_status = self.evaluate_regime(nsei_series, idx)

            if pending_rebalance["cand1"]:
                broker.execute_target_portfolio(
                    acc_cand1,
                    target_symbols=pending_rebalance["cand1"],
                    open_prices=today_opens,
                    exec_date=date_str,
                    signal_date=signal_dates["cand1"],
                    regime_pass=is_bull,
                    daily_volumes=today_vols,
                    median_turnovers_60d=med_to_dict,
                )
                pending_rebalance["cand1"] = []

            if pending_rebalance["cand2"]:
                broker.execute_target_portfolio(
                    acc_cand2,
                    target_symbols=pending_rebalance["cand2"],
                    open_prices=today_opens,
                    exec_date=date_str,
                    signal_date=signal_dates["cand2"],
                    regime_pass=is_bull,
                    daily_volumes=today_vols,
                    median_turnovers_60d=med_to_dict,
                )
                pending_rebalance["cand2"] = []

            if pending_rebalance["cand3"]:
                broker.execute_target_portfolio(
                    acc_cand3,
                    target_symbols=pending_rebalance["cand3"],
                    open_prices=today_opens,
                    exec_date=date_str,
                    signal_date=signal_dates["cand3"],
                    regime_pass=is_bull,
                    daily_volumes=today_vols,
                    median_turnovers_60d=med_to_dict,
                )
                pending_rebalance["cand3"] = []

            # 2. Check if Month-End to generate signals at Close
            is_month_end = False
            if idx < n_dates - 1:
                next_dt = dates[idx + 1]
                if next_dt.month != cur_dt.month:
                    is_month_end = True
            elif idx == n_dates - 1:
                is_month_end = True

            if is_month_end:
                scores1 = self.score_candidate1_reg_alpha(close_df, returns_df, nsei_returns, to_win, idx)
                scores2 = self.score_candidate2_c1b_momentum(close_df, to_win, idx)
                scores3 = self.score_candidate3_dual_momentum(close_df, to_win, idx)

                pending_rebalance["cand1"] = self.apply_retention_buffer(acc_cand1.holdings, scores1, is_bull)
                pending_rebalance["cand2"] = self.apply_retention_buffer(acc_cand2.holdings, scores2, is_bull)
                pending_rebalance["cand3"] = self.apply_retention_buffer(acc_cand3.holdings, scores3, is_bull)

                signal_dates["cand1"] = date_str
                signal_dates["cand2"] = date_str
                signal_dates["cand3"] = date_str

            # 3. Mark to market at Close
            today_closes = close_df.iloc[idx].to_dict()
            cur_niftybees = float(niftybees_series.iloc[idx]) if not pd.isna(niftybees_series.iloc[idx]) else 0.0
            prev_niftybees = float(niftybees_series.iloc[idx - 1]) if idx > 0 and not pd.isna(niftybees_series.iloc[idx - 1]) else cur_niftybees

            broker.mark_to_market_session(
                acc_cand1,
                close_prices=today_closes,
                session_date=date_str,
                benchmark_close=cur_niftybees,
                prev_benchmark_close=prev_niftybees,
                regime_status=regime_status,
            )
            broker.mark_to_market_session(
                acc_cand2,
                close_prices=today_closes,
                session_date=date_str,
                benchmark_close=cur_niftybees,
                prev_benchmark_close=prev_niftybees,
                regime_status=regime_status,
            )
            broker.mark_to_market_session(
                acc_cand3,
                close_prices=today_closes,
                session_date=date_str,
                benchmark_close=cur_niftybees,
                prev_benchmark_close=prev_niftybees,
                regime_status=regime_status,
            )

        # Benchmark passive return calculation over the same period
        b_start = float(niftybees_series.iloc[start_bar])
        b_end = float(niftybees_series.iloc[-1])
        b_cum_ret = ((b_end / b_start) - 1.0) * 100.0 if b_start > 0 else 0.0
        n_years = (dates[-1] - dates[start_bar]).days / 365.25
        b_cagr = (((b_end / b_start) ** (1.0 / n_years)) - 1.0) * 100.0 if n_years > 0.1 and b_end > 0 else b_cum_ret

        b_sub = niftybees_series.iloc[start_bar:]
        b_peak = b_sub.cummax()
        b_max_dd = float(((b_sub - b_peak) / b_peak * 100.0).min())

        # Compile metrics
        m1 = compute_performance_metrics(acc_cand1.daily_snapshots, acc_cand1.trades_journal, self.initial_capital)
        m2 = compute_performance_metrics(acc_cand2.daily_snapshots, acc_cand2.trades_journal, self.initial_capital)
        m3 = compute_performance_metrics(acc_cand3.daily_snapshots, acc_cand3.trades_journal, self.initial_capital)

        # Excess returns over benchmark
        m1["excess_vs_benchmark_pct"] = round(m1["cagr_pct"] - b_cagr, 2)
        m2["excess_vs_benchmark_pct"] = round(m2["cagr_pct"] - b_cagr, 2)
        m3["excess_vs_benchmark_pct"] = round(m3["cagr_pct"] - b_cagr, 2)

        # Excess returns over control (Candidate 2)
        m1["excess_vs_control_pct"] = round(m1["cagr_pct"] - m2["cagr_pct"], 2)
        m3["excess_vs_control_pct"] = round(m3["cagr_pct"] - m2["cagr_pct"], 2)

        result = {
            "scenario": scenario_name,
            "stress_multiplier": stress_multiplier,
            "evaluation_start_date": str(dates[start_bar].date()),
            "evaluation_end_date": str(dates[-1].date()),
            "sessions_count": len(dates) - start_bar,
            "simulated_capital_per_strategy": self.initial_capital,
            "benchmark": {
                "name": "NIFTYBEES.NS Total Return ETF",
                "net_return_pct": round(b_cum_ret, 2),
                "cagr_pct": round(b_cagr, 2),
                "max_drawdown_pct": round(abs(b_max_dd), 2),
            },
            "candidate1": {
                "name": "Market-Sector Regression-Alpha (Buf 1–30)",
                "status": "ACTIVE",
                "final_equity": round(acc_cand1.total_equity, 2),
                "metrics": m1,
                "latest_holdings_count": len(acc_cand1.holdings),
            },
            "candidate2": {
                "name": "C1b Regime-Filtered Momentum (Buf 1–30)",
                "status": "ACTIVE",
                "final_equity": round(acc_cand2.total_equity, 2),
                "metrics": m2,
                "latest_holdings_count": len(acc_cand2.holdings),
            },
            "candidate3": {
                "name": "Relative-Plus-Absolute Strength Dual Momentum (Buf 1–30)",
                "status": "ACTIVE",
                "final_equity": round(acc_cand3.total_equity, 2),
                "metrics": m3,
                "latest_holdings_count": len(acc_cand3.holdings),
            },
            "candidate4": {
                "name": "Value-Based Strategy",
                "status": "UNAVAILABLE",
                "reason": "No trustworthy point-in-time fundamental data (balance sheets/quarterly P&L) available in frozen repository.",
                "final_equity": self.initial_capital,
                "metrics": {
                    "net_return_pct": 0.0,
                    "cagr_pct": 0.0,
                    "max_drawdown_pct": 0.0,
                    "total_trades": 0,
                },
                "latest_holdings_count": 0,
            },
        }

        # Cache replay results
        out_file = self.output_dir / f"replay_{prefix}results.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=safe_json_serialize)

        logger.info(f"Replay completed ({scenario_name}). Saved to {out_file}")
        return result

