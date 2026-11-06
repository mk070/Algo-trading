"""
Research Cycle 3: Independent Swing Strategy Testing Runner
Strictly Offline Research — No Live Trading

Simulates:
1. Comparator C1b India (Standard 12-1 Momentum, No Buffer & Buffered)
2. Candidate 1: Residual Momentum (Blitz, Huij & Martens, 2011, No Buffer & Buffered)
3. Candidate 2: Frog-in-the-Pan Momentum (Da, Gurun & Warachka, 2014, No Buffer & Buffered)
4. Candidate 3: Connors RSI(2) Mean Reversion (Trade-Level Daily Swing, Research & Practical Scale)
5. Control B: 1,000 Random Selection Matched Portfolios
6. 95% Circular Block-Bootstrap Confidence Intervals

Saves:
- research/next_cycle/strategy_comparison.json
- research/next_cycle/run_manifest.json
- research/next_cycle/trades/*.csv
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


def json_serializer(obj: Any) -> Any:
    """Safe serializer for numpy and date objects."""
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (datetime.date, datetime.datetime, pd.Timestamp)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def calculate_cost_in(turnover: float, side: str, n_scrip_sold: int = 0) -> float:
    """Exact Zerodha Indian equity delivery cost model (NSE)."""
    if turnover <= 0:
        return 0.0
    stt = 0.001 * turnover  # 0.10% buy and sell
    exchange_charges = 0.00003 * turnover  # 0.003%
    sebi_charges = (10.0 / 10000000.0) * turnover  # INR 10 per crore
    stamp_duty = 0.00015 * turnover if side == "BUY" else 0.0  # 0.015% buy only
    dp_charges = (13.50 * 1.18 * n_scrip_sold) if side == "SELL" else 0.0  # INR 15.93 per sold scrip
    gst = 0.18 * (exchange_charges + sebi_charges + (dp_charges if side == "SELL" else 0.0))
    return float(stt + exchange_charges + sebi_charges + stamp_duty + dp_charges + gst)


def compute_rsi_series(series: pd.Series, period: int = 2) -> pd.Series:
    """Wilder RSI calculation."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    rsi = rsi.where(avg_gain != 0.0, 0.0)
    return rsi


def compute_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """True Range and ATR."""
    high = df["split_adj_high"]
    low = df["split_adj_low"]
    close = df["split_adj_close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


class Cycle3ResearchEngine:
    def __init__(self):
        u_path = Path("data/universe/research_universe_v1.csv")
        snap_path = Path("data/research/research_snapshot_20261106.parquet")
        bench_path = Path("data/research/benchmark_series.parquet")

        self.u_df = pd.read_csv(u_path)
        self.snap_df = pd.read_parquet(snap_path)
        self.bench_df = pd.read_parquet(bench_path)

        self.snap_df["date"] = pd.to_datetime(self.snap_df["date"])
        self.bench_df["date"] = pd.to_datetime(self.bench_df["date"])

        # Filter India universe
        self.in_syms = self.u_df[self.u_df["market"] == "IN"]["symbol"].tolist()
        self.in_snap = self.snap_df[self.snap_df["symbol"].isin(self.in_syms)].copy()

        self.sector_map = dict(zip(self.u_df["symbol"], self.u_df["sector"]))
        sectors = set(self.sector_map.values())
        self.sector_to_syms = {sec: [s for s in self.in_syms if self.sector_map[s] == sec] for sec in sectors}

        # Pivot tables
        self.close_df = self.in_snap.pivot(index="date", columns="symbol", values="split_adj_close").sort_index()
        self.open_df = self.in_snap.pivot(index="date", columns="symbol", values="split_adj_open").sort_index()
        self.vol_df = self.in_snap.pivot(index="date", columns="symbol", values="volume").sort_index()
        self.returns_df = self.close_df.pct_change()

        # Benchmark series (clean non-NaN regime series matching Phase 2)
        nsei_raw = self.bench_df[self.bench_df["symbol"] == "^NSEI"].sort_values("date").set_index("date")["close"].dropna()
        nsei_sma200_raw = nsei_raw.rolling(200, min_periods=200).mean()
        self.nsei_close = nsei_raw.reindex(self.close_df.index).ffill()
        self.nsei_returns = self.nsei_close.pct_change()
        self.nsei_sma200 = nsei_sma200_raw.reindex(self.close_df.index).ffill()

        niftybees = self.bench_df[self.bench_df["symbol"] == "NIFTYBEES.NS"].sort_values("date").set_index("date")["close"].dropna()
        self.niftybees_close = niftybees.reindex(self.close_df.index).ffill()

        # Dates & Turnover
        self.dates = self.close_df.index
        df_dates = pd.DataFrame({"date": self.dates, "year_month": self.dates.to_period("M")})
        self.month_end_dates = df_dates.groupby("year_month")["date"].max().tolist()

        turnover_daily = self.close_df * self.vol_df
        self.med_turnover_60d = turnover_daily.rolling(window=60, min_periods=40).median()

        # Precompute valid rebalance month ends (min lookback 273 sessions)
        self.valid_rebalance_dates = [
            m for m in self.month_end_dates
            if self.dates.get_loc(m) >= 273 and self.dates.get_loc(m) + 1 < len(self.dates)
        ]

    def run_portfolio_strategy(
        self,
        strategy_name: str,
        capital: float = 500000.0,
        buffered: bool = False,
        random_selection: bool = False,
        rng: Optional[np.random.RandomState] = None,
    ) -> Dict[str, Any]:
        """
        Runs a monthly rebalanced portfolio strategy (C1b, Cand 1 Residual Momentum, Cand 2 FITP).
        Supports buffer retention band (1-30).
        """
        slip_pct = 0.0010  # 0.10% adverse fill
        top_n = 20
        buffer_band = 30 if buffered else 20

        current_holdings: Dict[str, int] = {}  # symbol -> shares
        cash = capital
        total_costs_paid = 0.0

        monthly_records: List[Dict[str, Any]] = []
        trade_ledger: List[Dict[str, Any]] = []
        turnover_list: List[float] = []

        prev_equity = capital
        rebalances_count = 0

        for m_end in self.valid_rebalance_dates:
            end_idx = self.dates.get_loc(m_end)
            exec_date = self.dates[end_idx + 1]

            # 1. Eligibility at month end
            eligible_pool = []
            start_12m = end_idx - 252
            stop_1m = end_idx - 21

            # Market regime
            regime_pass = True
            b_c = self.nsei_close.loc[m_end]
            b_sma = self.nsei_sma200.loc[m_end]
            if pd.notna(b_c) and pd.notna(b_sma):
                regime_pass = bool(b_c > b_sma)

            rm_win = self.nsei_returns.iloc[start_12m : stop_1m + 1].values

            for sym in self.in_syms:
                if sym not in self.close_df.columns:
                    continue
                p_curr = self.close_df[sym].iloc[end_idx]
                if pd.isna(p_curr) or p_curr < 50.0:
                    continue
                to_val = self.med_turnover_60d[sym].iloc[end_idx] if sym in self.med_turnover_60d.columns else 0.0
                if pd.isna(to_val) or to_val < 50000000.0:
                    continue

                p_start = self.close_df[sym].iloc[start_12m]
                p_stop = self.close_df[sym].iloc[stop_1m]
                if pd.isna(p_start) or pd.isna(p_stop) or p_start <= 0:
                    continue

                pret = (p_stop / p_start) - 1.0

                if random_selection:
                    eligible_pool.append({"symbol": sym, "score": 0.0, "pret": pret})
                    continue

                if strategy_name == "C1b_BASELINE":
                    # Conventional 12-1 momentum
                    score = pret
                    eligible_pool.append({"symbol": sym, "score": score, "pret": pret})

                elif strategy_name == "CAND1_RESIDUAL_MOMENTUM":
                    # Blitz, Huij & Martens residual momentum
                    y = self.returns_df[sym].iloc[start_12m : stop_1m + 1].values
                    if np.isnan(y).any() or np.isnan(rm_win).any():
                        continue
                    sec = self.sector_map[sym]
                    other_syms = [s for s in self.sector_to_syms[sec] if s != sym]
                    if other_syms:
                        rs_win = self.returns_df[other_syms].iloc[start_12m : stop_1m + 1].mean(axis=1).values
                        X = np.column_stack([np.ones_like(y), rm_win, rs_win])
                    else:
                        X = np.column_stack([np.ones_like(y), rm_win])

                    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
                    alpha = coef[0]
                    resids = y - (X @ coef)
                    std_res = np.std(resids, ddof=1)
                    if std_res > 1e-8:
                        score = (len(y) * alpha) / std_res
                        eligible_pool.append({"symbol": sym, "score": score, "pret": pret, "alpha": alpha, "std_res": std_res})

                elif strategy_name == "CAND2_FROG_IN_THE_PAN":
                    # Da, Gurun & Warachka Information Discreteness
                    if pret <= 0:
                        continue  # positive momentum cohort only
                    daily_rets = self.returns_df[sym].iloc[start_12m : stop_1m + 1].dropna().values
                    n_tot = len(daily_rets)
                    if n_tot == 0:
                        continue
                    n_neg = np.sum(daily_rets < 0)
                    n_pos = np.sum(daily_rets > 0)
                    pct_neg = n_neg / n_tot
                    pct_pos = n_pos / n_tot
                    id_val = pct_neg - pct_pos
                    # Lower ID = smoother = higher rank. We score as -id_val so higher score is better
                    eligible_pool.append({"symbol": sym, "score": -id_val, "id": id_val, "pret": pret, "pct_pos": pct_pos, "pct_neg": pct_neg})

            # Sort eligible stocks
            ranked_syms: List[str] = []
            if len(eligible_pool) > 0:
                if random_selection and rng is not None:
                    # Control B: random selection without momentum score
                    pool = [x["symbol"] for x in eligible_pool]
                    ranked_syms = list(rng.choice(pool, size=len(pool), replace=False))
                else:
                    eligible_pool.sort(key=lambda x: x["score"], reverse=True)
                    ranked_syms = [x["symbol"] for x in eligible_pool]

            # Determine target portfolio
            target_symbols: List[str] = []
            if regime_pass and len(ranked_syms) > 0:
                if not buffered:
                    target_symbols = ranked_syms[:top_n]
                else:
                    # Turnover buffer logic:
                    # Retain current holdings if they remain in top buffer_band (rank <= 30)
                    retained = [s for s in current_holdings.keys() if s in ranked_syms and ranked_syms.index(s) < buffer_band]
                    target_symbols = list(retained)
                    # Fill remaining slots from top-ranked candidates not yet held
                    for s in ranked_syms:
                        if len(target_symbols) >= top_n:
                            break
                        if s not in target_symbols:
                            target_symbols.append(s)

            # Rebalance execution at Open of exec_date
            rebalances_count += 1

            # Liquidate exits
            sold_scrip_count = 0
            exit_turnover = 0.0
            for sym, shares in list(current_holdings.items()):
                if sym not in target_symbols or not regime_pass:
                    op = self.open_df[sym].loc[exec_date]
                    if pd.notna(op) and op > 0:
                        fill_p = op * (1.0 - slip_pct)
                        gross_proceeds = fill_p * shares
                        exit_turnover += gross_proceeds
                        sold_scrip_count += 1
                        trade_cost = calculate_cost_in(gross_proceeds, "SELL", n_scrip_sold=1)
                        total_costs_paid += trade_cost
                        cash += (gross_proceeds - trade_cost)
                        del current_holdings[sym]

                        trade_ledger.append({
                            "rebalance_date": str(m_end.date()),
                            "exec_date": str(exec_date.date()),
                            "symbol": sym,
                            "action": "SELL_EXIT",
                            "shares": shares,
                            "fill_price": round(fill_p, 2),
                            "turnover": round(gross_proceeds, 2),
                            "cost": round(trade_cost, 2),
                            "regime_pass": regime_pass,
                        })

            # Calculate total portfolio equity before buying
            current_equity = cash
            for sym, shares in current_holdings.items():
                op = self.open_df[sym].loc[exec_date]
                if pd.notna(op) and op > 0:
                    current_equity += op * shares

            # Target position sizing
            n_targets = len(target_symbols)
            target_cap_per_stock = (current_equity / n_targets) if n_targets > 0 else 0.0
            rebalance_turnover = exit_turnover

            for sym in target_symbols:
                op = self.open_df[sym].loc[exec_date]
                if pd.isna(op) or op <= 0:
                    continue
                fill_buy = op * (1.0 + slip_pct)
                target_shares = int(math.floor(target_cap_per_stock / fill_buy)) if fill_buy > 0 else 0
                curr_shares = current_holdings.get(sym, 0)
                delta_shares = target_shares - curr_shares

                if delta_shares > 0:
                    trade_val = delta_shares * fill_buy
                    trade_cost = calculate_cost_in(trade_val, "BUY")
                    if cash >= (trade_val + trade_cost):
                        cash -= (trade_val + trade_cost)
                        total_costs_paid += trade_cost
                        rebalance_turnover += trade_val
                        current_holdings[sym] = curr_shares + delta_shares
                        trade_ledger.append({
                            "rebalance_date": str(m_end.date()),
                            "exec_date": str(exec_date.date()),
                            "symbol": sym,
                            "action": "BUY_ENTER" if curr_shares == 0 else "BUY_ADD",
                            "shares": delta_shares,
                            "fill_price": round(fill_buy, 2),
                            "turnover": round(trade_val, 2),
                            "cost": round(trade_cost, 2),
                            "regime_pass": regime_pass,
                        })
                elif delta_shares < 0:
                    sell_shares = abs(delta_shares)
                    fill_sell = op * (1.0 - slip_pct)
                    trade_val = sell_shares * fill_sell
                    trade_cost = calculate_cost_in(trade_val, "SELL", n_scrip_sold=0)  # partial trim, no separate DP
                    cash += (trade_val - trade_cost)
                    total_costs_paid += trade_cost
                    rebalance_turnover += trade_val
                    current_holdings[sym] = curr_shares - sell_shares
                    trade_ledger.append({
                        "rebalance_date": str(m_end.date()),
                        "exec_date": str(exec_date.date()),
                        "symbol": sym,
                        "action": "SELL_TRIM",
                        "shares": sell_shares,
                        "fill_price": round(fill_sell, 2),
                        "turnover": round(trade_val, 2),
                        "cost": round(trade_cost, 2),
                        "regime_pass": regime_pass,
                    })

            # Calculate month-end portfolio equity
            month_end_equity = cash
            for sym, shares in current_holdings.items():
                p_c = self.close_df[sym].loc[m_end]
                if pd.notna(p_c) and p_c > 0:
                    month_end_equity += p_c * shares

            # Benchmark performance over same month
            b_start = self.niftybees_close.loc[self.valid_rebalance_dates[0]]
            b_curr = self.niftybees_close.loc[m_end]

            m_net_ret = (month_end_equity / prev_equity) - 1.0 if prev_equity > 0 else 0.0

            # Monthly benchmark return
            if len(monthly_records) == 0:
                b_prev = self.niftybees_close.loc[self.valid_rebalance_dates[0]]
            else:
                prev_m_end = self.valid_rebalance_dates[len(monthly_records) - 1]
                b_prev = self.niftybees_close.loc[prev_m_end]

            m_b_ret = (b_curr / b_prev) - 1.0 if pd.notna(b_prev) and b_prev > 0 else 0.0
            m_excess_ret = m_net_ret - m_b_ret

            turnover_pct = (rebalance_turnover / prev_equity) * 100.0 if prev_equity > 0 else 0.0
            turnover_list.append(turnover_pct)

            monthly_records.append({
                "date": str(m_end.date()),
                "year_month": str(m_end.to_period("M")),
                "portfolio_equity": round(month_end_equity, 2),
                "monthly_net_return": round(m_net_ret, 6),
                "benchmark_close": round(b_curr, 2) if pd.notna(b_curr) else 0.0,
                "benchmark_return": round(m_b_ret, 6),
                "monthly_excess_return": round(m_excess_ret, 6),
                "regime_pass": regime_pass,
                "active_holdings_count": len(current_holdings),
                "turnover_pct": round(turnover_pct, 2),
            })

            prev_equity = month_end_equity

        # Aggregate Metrics
        total_months = len(monthly_records)
        years = total_months / 12.0
        final_equity = monthly_records[-1]["portfolio_equity"]
        cum_ret = (final_equity / capital) - 1.0
        ann_ret = ((final_equity / capital) ** (1.0 / years)) - 1.0 if years > 0 else 0.0

        b_first = monthly_records[0]["benchmark_close"]
        b_last = monthly_records[-1]["benchmark_close"]
        b_cum_ret = (b_last / b_first) - 1.0 if b_first > 0 else 0.0
        ann_b_ret = ((1.0 + b_cum_ret) ** (1.0 / years)) - 1.0 if years > 0 else 0.0

        ann_excess_ret = ann_ret - ann_b_ret

        # Drawdown calculation
        eq_series = np.array([r["portfolio_equity"] for r in monthly_records])
        peaks = np.maximum.accumulate(eq_series)
        drawdowns = (eq_series - peaks) / peaks
        max_dd = float(np.min(drawdowns))

        # Benchmark drawdown
        b_series = np.array([r["benchmark_close"] for r in monthly_records])
        b_peaks = np.maximum.accumulate(b_series)
        b_drawdowns = (b_series - b_peaks) / b_peaks
        b_max_dd = float(np.min(b_drawdowns))

        # Volatility, Sharpe, Sortino
        net_rets = np.array([r["monthly_net_return"] for r in monthly_records])
        excess_rets = np.array([r["monthly_excess_return"] for r in monthly_records])
        vol_ann = float(np.std(net_rets, ddof=1) * np.sqrt(12)) if len(net_rets) > 1 else 0.0
        sharpe = (ann_ret / vol_ann) if vol_ann > 0 else 0.0

        neg_rets = net_rets[net_rets < 0]
        downside_vol = float(np.std(neg_rets, ddof=1) * np.sqrt(12)) if len(neg_rets) > 1 else 0.0
        sortino = (ann_ret / downside_vol) if downside_vol > 0 else 0.0

        avg_turnover = float(np.mean(turnover_list)) if turnover_list else 0.0
        cost_drag_pct = (total_costs_paid / capital) * 100.0

        # Yearly breakdown
        df_m = pd.DataFrame(monthly_records)
        df_m["year"] = pd.to_datetime(df_m["date"]).dt.year
        yearly_perf = {}
        pos_years = 0
        tot_years = 0
        for yr, group in df_m.groupby("year"):
            yr_p_ret = float(np.prod(1.0 + group["monthly_net_return"]) - 1.0)
            yr_b_ret = float(np.prod(1.0 + group["benchmark_return"]) - 1.0)
            yr_excess = yr_p_ret - yr_b_ret
            tot_years += 1
            if yr_excess > 0:
                pos_years += 1
            yearly_perf[str(yr)] = {
                "portfolio_net_return_pct": round(yr_p_ret * 100.0, 2),
                "benchmark_return_pct": round(yr_b_ret * 100.0, 2),
                "excess_return_pct": round(yr_excess * 100.0, 2),
                "months": len(group),
            }

        # Sector attribution of executed buys
        df_trades = pd.DataFrame(trade_ledger)
        sector_attribution = {}
        if not df_trades.empty and "symbol" in df_trades.columns:
            buys = df_trades[df_trades["action"].str.contains("BUY")].copy()
            if not buys.empty:
                buys["sector"] = buys["symbol"].map(self.sector_map)
                sector_counts = buys["sector"].value_counts()
                sector_turnover = buys.groupby("sector")["turnover"].sum()
                for sec in sector_counts.index:
                    sector_attribution[sec] = {
                        "buys_count": int(sector_counts[sec]),
                        "turnover_inr": round(float(sector_turnover[sec]), 2),
                        "pct_of_total_buying": round(float(sector_turnover[sec] / buys["turnover"].sum()) * 100.0, 1),
                    }

        # Regime performance breakdown
        bull_months = df_m[df_m["regime_pass"] == True]
        bear_months = df_m[df_m["regime_pass"] == False]

        bull_net_ann = float((np.prod(1.0 + bull_months["monthly_net_return"]) ** (12.0 / len(bull_months)) - 1.0) * 100.0) if len(bull_months) > 0 else 0.0
        bull_b_ann = float((np.prod(1.0 + bull_months["benchmark_return"]) ** (12.0 / len(bull_months)) - 1.0) * 100.0) if len(bull_months) > 0 else 0.0
        bear_net_tot = float((np.prod(1.0 + bear_months["monthly_net_return"]) - 1.0) * 100.0) if len(bear_months) > 0 else 0.0
        bear_b_tot = float((np.prod(1.0 + bear_months["benchmark_return"]) - 1.0) * 100.0) if len(bear_months) > 0 else 0.0

        regime_breakdown = {
            "bull_regime": {
                "months": len(bull_months),
                "annualized_net_return_pct": round(bull_net_ann, 2),
                "annualized_benchmark_return_pct": round(bull_b_ann, 2),
            },
            "bear_regime": {
                "months": len(bear_months),
                "total_return_pct": round(bear_net_tot, 2),
                "benchmark_total_return_pct": round(bear_b_tot, 2),
            },
        }

        return {
            "strategy": strategy_name,
            "buffered": buffered,
            "capital": capital,
            "total_months": total_months,
            "rebalances_count": rebalances_count,
            "final_equity": round(final_equity, 2),
            "cum_net_return_pct": round(cum_ret * 100.0, 2),
            "annualized_net_return_pct": round(ann_ret * 100.0, 2),
            "annualized_benchmark_return_pct": round(ann_b_ret * 100.0, 2),
            "annualized_excess_return_pct": round(ann_excess_ret * 100.0, 2),
            "max_drawdown_pct": round(abs(max_dd) * 100.0, 2),
            "benchmark_max_drawdown_pct": round(abs(b_max_dd) * 100.0, 2),
            "drawdown_ratio": round(abs(max_dd) / abs(b_max_dd), 2) if abs(b_max_dd) > 0 else 999.0,
            "volatility_pct": round(vol_ann * 100.0, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "total_costs_paid": round(total_costs_paid, 2),
            "cost_drag_pct_of_capital": round(cost_drag_pct, 2),
            "avg_monthly_turnover_pct": round(avg_turnover, 2),
            "positive_calendar_years": f"{pos_years}/{tot_years}",
            "yearly_performance": yearly_perf,
            "regime_breakdown": regime_breakdown,
            "sector_attribution": sector_attribution,
            "monthly_records": monthly_records,
            "trade_ledger": trade_ledger,
        }

    def run_candidate3_simulation(self, capital: float = 500000.0) -> Dict[str, Any]:
        """
        Runs Candidate 3: Connors RSI(2) Daily Mean Reversion Strategy.
        - Long-only, eligible equities (price >= 50, 60d median turnover >= 5 Cr)
        - Close > SMA200
        - RSI(2) <= 10.0
        - Enter next session Open (with 0.10% adverse slippage + costs)
        - Exit next session Open after Close > SMA5 OR after 5 completed sessions elapsed (with 0.10% adverse slippage + costs)
        - Max 10 positions (10% allocation per slot), whole shares only
        - Deterministic priority: lowest RSI(2) ascending
        """
        slip_pct = 0.0010
        max_positions = 10
        slot_fraction = 1.0 / max_positions

        # Precompute indicators for all symbols
        sym_indicators = {}
        for sym in self.in_syms:
            df = self.in_snap[self.in_snap["symbol"] == sym].sort_values("date").copy()
            if len(df) < 220:
                continue
            df["split_adj_open"] = df["split_adj_open"].astype(float)
            df["split_adj_high"] = df["split_adj_high"].astype(float)
            df["split_adj_low"] = df["split_adj_low"].astype(float)
            df["split_adj_close"] = df["split_adj_close"].astype(float)
            df["volume"] = df["volume"].astype(float)

            df["sma200"] = df["split_adj_close"].rolling(200, min_periods=200).mean()
            df["sma5"] = df["split_adj_close"].rolling(5, min_periods=5).mean()
            df["rsi2"] = compute_rsi_series(df["split_adj_close"], period=2)
            df["atr14"] = compute_atr_series(df, period=14)
            df["turnover_daily"] = df["split_adj_close"] * df["volume"]
            df["med_to_60d"] = df["turnover_daily"].rolling(60, min_periods=40).median()
            df = df.set_index("date")
            sym_indicators[sym] = df

        # State tracking
        cash = capital
        # active_positions: sym -> dict
        active_positions: Dict[str, Dict[str, Any]] = {}
        completed_trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []
        total_costs_paid = 0.0

        # Start evaluation once SMA200 is available (skip first 205 trading sessions)
        eval_dates = self.dates[205:]

        # Pending orders for next session open
        pending_buys: List[Dict[str, Any]] = []
        pending_exits: List[Dict[str, Any]] = []

        for day_idx, current_date in enumerate(eval_dates):
            # 1. Execute Pending Exits at Open
            for exit_req in pending_exits:
                sym = exit_req["symbol"]
                pos = active_positions.get(sym)
                if not pos:
                    continue
                df_sym = sym_indicators[sym]
                if current_date not in df_sym.index:
                    continue
                op = df_sym.loc[current_date, "split_adj_open"]
                if pd.isna(op) or op <= 0:
                    continue

                exit_fill = op * (1.0 - slip_pct)
                shares = pos["shares"]
                gross_proceeds = exit_fill * shares
                cost = calculate_cost_in(gross_proceeds, "SELL", n_scrip_sold=1)
                total_costs_paid += cost
                net_proceeds = gross_proceeds - cost
                cash += net_proceeds

                gross_pnl = gross_proceeds - (pos["entry_price"] * shares)
                net_pnl = gross_pnl - pos["entry_cost"] - cost
                pnl_pct = (net_pnl / (pos["entry_price"] * shares)) * 100.0
                initial_risk = pos["atr_entry"] * shares
                r_multiple = (net_pnl / initial_risk) if initial_risk > 0 else 0.0

                completed_trades.append({
                    "symbol": sym,
                    "entry_date": str(pos["entry_date"].date()),
                    "entry_price": round(pos["entry_price"], 2),
                    "exit_date": str(current_date.date()),
                    "exit_price": round(exit_fill, 2),
                    "exit_reason": exit_req["reason"],
                    "shares": shares,
                    "holding_days": pos["holding_days"],
                    "entry_cost": round(pos["entry_cost"], 2),
                    "exit_cost": round(cost, 2),
                    "total_costs": round(pos["entry_cost"] + cost, 2),
                    "gross_pnl": round(gross_pnl, 2),
                    "net_pnl": round(net_pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "atr_entry": round(pos["atr_entry"], 2),
                    "r_multiple": round(r_multiple, 2),
                    "sector": self.sector_map.get(sym, "Unknown"),
                })
                del active_positions[sym]

            pending_exits = []

            # 2. Execute Pending Buys at Open
            # Sort pending buys by lowest RSI(2) ascending
            pending_buys.sort(key=lambda x: x["rsi2"])

            for buy_req in pending_buys:
                sym = buy_req["symbol"]
                if sym in active_positions:
                    continue
                if len(active_positions) >= max_positions:
                    break

                df_sym = sym_indicators[sym]
                if current_date not in df_sym.index:
                    continue
                op = df_sym.loc[current_date, "split_adj_open"]
                if pd.isna(op) or op <= 0:
                    continue

                # Portfolio equity at open
                est_equity = cash
                for p_sym, p_pos in active_positions.items():
                    p_df = sym_indicators[p_sym]
                    if current_date in p_df.index:
                        p_op = p_df.loc[current_date, "split_adj_open"]
                        est_equity += (p_op if pd.notna(p_op) else p_pos["entry_price"]) * p_pos["shares"]

                target_alloc = est_equity * slot_fraction
                fill_buy = op * (1.0 + slip_pct)
                target_shares = int(math.floor(target_alloc / fill_buy)) if fill_buy > 0 else 0
                if target_shares <= 0:
                    continue

                trade_val = target_shares * fill_buy
                buy_cost = calculate_cost_in(trade_val, "BUY")
                if cash >= (trade_val + buy_cost):
                    cash -= (trade_val + buy_cost)
                    total_costs_paid += buy_cost
                    active_positions[sym] = {
                        "symbol": sym,
                        "entry_date": current_date,
                        "entry_price": fill_buy,
                        "shares": target_shares,
                        "entry_cost": buy_cost,
                        "atr_entry": buy_req["atr"],
                        "holding_days": 0,
                    }

            pending_buys = []

            # 3. Mark to Market Portfolio Equity at Close of current_date
            daily_equity = cash
            for sym, pos in list(active_positions.items()):
                pos["holding_days"] += 1
                df_sym = sym_indicators[sym]
                if current_date in df_sym.index:
                    cl = df_sym.loc[current_date, "split_adj_close"]
                    daily_equity += (cl if pd.notna(cl) else pos["entry_price"]) * pos["shares"]

            equity_curve.append({
                "date": str(current_date.date()),
                "equity": round(daily_equity, 2),
                "cash": round(cash, 2),
                "active_positions": len(active_positions),
            })

            # 4. Check Exits and Entry Signals on Completed Daily Bar (at Close)
            # A. Check Exits for active positions
            for sym, pos in list(active_positions.items()):
                df_sym = sym_indicators[sym]
                if current_date not in df_sym.index:
                    continue
                cl = df_sym.loc[current_date, "split_adj_close"]
                sma5 = df_sym.loc[current_date, "sma5"]

                if pd.notna(cl) and pd.notna(sma5) and cl > sma5:
                    pending_exits.append({"symbol": sym, "reason": "SMA5_EXIT"})
                elif pos["holding_days"] >= 5:
                    pending_exits.append({"symbol": sym, "reason": "TIME_STOP"})

            # B. Check Entry Setups for tomorrow's open
            exiting_syms = {x["symbol"] for x in pending_exits}
            for sym in self.in_syms:
                if sym in active_positions and sym not in exiting_syms:
                    continue
                df_sym = sym_indicators.get(sym)
                if df_sym is None or current_date not in df_sym.index:
                    continue

                cl = df_sym.loc[current_date, "split_adj_close"]
                sma200 = df_sym.loc[current_date, "sma200"]
                rsi2 = df_sym.loc[current_date, "rsi2"]
                to_val = df_sym.loc[current_date, "med_to_60d"]

                if pd.isna(cl) or pd.isna(sma200) or pd.isna(rsi2) or pd.isna(to_val):
                    continue

                if cl < 50.0 or to_val < 50000000.0:
                    continue

                if cl > sma200 and rsi2 <= 10.0:
                    atr = df_sym.loc[current_date, "atr14"]
                    pending_buys.append({
                        "symbol": sym,
                        "rsi2": float(rsi2),
                        "atr": float(atr) if pd.notna(atr) else (0.02 * cl),
                    })

        # Calculate Candidate 3 Performance Metrics
        total_trades = len(completed_trades)
        gross_wins = [t for t in completed_trades if t["gross_pnl"] > 0]
        wins = [t for t in completed_trades if t["net_pnl"] > 0]
        losses = [t for t in completed_trades if t["net_pnl"] < 0]
        ties = [t for t in completed_trades if t["net_pnl"] == 0]

        gross_win_rate = (len(gross_wins) / total_trades * 100.0) if total_trades > 0 else 0.0
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
        gross_profit = sum(t["gross_pnl"] for t in completed_trades if t["gross_pnl"] > 0)
        gross_loss = abs(sum(t["gross_pnl"] for t in completed_trades if t["gross_pnl"] < 0))
        net_profit = sum(t["net_pnl"] for t in wins)
        net_loss = abs(sum(t["net_pnl"] for t in losses))

        profit_factor = (net_profit / net_loss) if net_loss > 0 else 999.0
        gross_profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        total_net_pnl = sum(t["net_pnl"] for t in completed_trades)
        currency_expectancy = (total_net_pnl / total_trades) if total_trades > 0 else 0.0

        r_multiples = [t["r_multiple"] for t in completed_trades]
        expectancy_r = float(np.mean(r_multiples)) if r_multiples else 0.0

        pnl_pcts = [t["pnl_pct"] for t in completed_trades]
        avg_trade_pct = float(np.mean(pnl_pcts)) if pnl_pcts else 0.0
        avg_win_pct = float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0
        avg_loss_pct = float(np.mean([t["pnl_pct"] for t in losses])) if losses else 0.0

        holding_days_list = [t["holding_days"] for t in completed_trades]
        avg_holding_days = float(np.mean(holding_days_list)) if holding_days_list else 0.0

        # Equity metrics
        eq_arr = np.array([e["equity"] for e in equity_curve])
        peaks = np.maximum.accumulate(eq_arr)
        dds = (eq_arr - peaks) / peaks
        max_dd = float(np.min(dds)) if len(dds) > 0 else 0.0

        final_equity = equity_curve[-1]["equity"] if equity_curve else capital
        cum_ret = (final_equity / capital) - 1.0
        years = len(equity_curve) / 252.0
        ann_ret = ((final_equity / capital) ** (1.0 / years)) - 1.0 if years > 0 else 0.0

        # Benchmark return over same daily period
        start_date = eval_dates[0]
        end_date = eval_dates[-1]
        b_sub = self.niftybees_close.loc[start_date:end_date].dropna()
        b_cum = (b_sub.iloc[-1] / b_sub.iloc[0]) - 1.0 if len(b_sub) > 1 else 0.0
        ann_b_ret = ((1.0 + b_cum) ** (1.0 / years)) - 1.0 if years > 0 else 0.0
        ann_excess_ret = ann_ret - ann_b_ret

        # Top 5 winners contribution
        sorted_by_pnl = sorted(completed_trades, key=lambda x: x["net_pnl"], reverse=True)
        top5_profit = sum(t["net_pnl"] for t in sorted_by_pnl[:5])
        top5_contrib_pct = (top5_profit / net_profit * 100.0) if net_profit > 0 else 0.0

        # Yearly breakdown of trades
        df_tr = pd.DataFrame(completed_trades)
        yearly_trades = {}
        if not df_tr.empty:
            df_tr["year"] = pd.to_datetime(df_tr["exit_date"]).dt.year
            for yr, group in df_tr.groupby("year"):
                yr_wins = group[group["net_pnl"] > 0]
                yr_net = group["net_pnl"].sum()
                yearly_trades[str(yr)] = {
                    "total_trades": len(group),
                    "win_rate_pct": round(len(yr_wins) / len(group) * 100.0, 1),
                    "net_pnl": round(float(yr_net), 2),
                    "profit_factor": round(float(group[group["net_pnl"] > 0]["net_pnl"].sum() / abs(group[group["net_pnl"] < 0]["net_pnl"].sum())), 2) if abs(group[group["net_pnl"] < 0]["net_pnl"].sum()) > 0 else 999.0,
                }

        # Sector attribution
        sector_attribution = {}
        if not df_tr.empty:
            for sec, group in df_tr.groupby("sector"):
                sector_attribution[sec] = {
                    "trades": len(group),
                    "win_rate_pct": round(len(group[group["net_pnl"] > 0]) / len(group) * 100.0, 1),
                    "net_pnl": round(float(group["net_pnl"].sum()), 2),
                }

        # Exit reasons breakdown
        exit_reasons = {}
        if not df_tr.empty:
            for r, group in df_tr.groupby("exit_reason"):
                exit_reasons[r] = {
                    "count": len(group),
                    "pct": round(len(group) / len(df_tr) * 100.0, 1),
                    "win_rate_pct": round(len(group[group["net_pnl"] > 0]) / len(group) * 100.0, 1),
                    "avg_holding_days": round(float(group["holding_days"].mean()), 1),
                }

        cost_drag_pct = (total_costs_paid / capital) * 100.0

        return {
            "strategy": "CAND3_CONNORS_RSI2",
            "capital": capital,
            "total_trades": total_trades,
            "gross_winning_trades": len(gross_wins),
            "gross_win_rate_pct": round(gross_win_rate, 2),
            "net_winning_trades": len(wins),
            "net_win_rate_pct": round(win_rate, 2),
            "currency_expectancy_inr": round(currency_expectancy, 2),
            "expectancy_r_unvalidated": round(expectancy_r, 3),
            "profit_factor": round(profit_factor, 2),
            "gross_profit_factor": round(gross_profit_factor, 2),
            "avg_trade_pct": round(avg_trade_pct, 2),
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "avg_holding_days": round(avg_holding_days, 1),
            "final_equity": round(final_equity, 2),
            "cum_net_return_pct": round(cum_ret * 100.0, 2),
            "annualized_net_return_pct": round(ann_ret * 100.0, 2),
            "annualized_benchmark_return_pct": round(ann_b_ret * 100.0, 2),
            "annualized_excess_return_pct": round(ann_excess_ret * 100.0, 2),
            "max_drawdown_pct": round(abs(max_dd) * 100.0, 2),
            "total_costs_paid": round(total_costs_paid, 2),
            "cost_drag_pct_of_capital": round(cost_drag_pct, 2),
            "top5_winners_contribution_pct": round(top5_contrib_pct, 1),
            "exit_reasons_breakdown": exit_reasons,
            "yearly_performance": yearly_trades,
            "sector_attribution": sector_attribution,
            "completed_trades": completed_trades,
            "equity_curve": equity_curve,
        }


def run_block_bootstrap_ci(
    monthly_excess_returns: List[float],
    block_len: int = 6,
    n_resamples: int = 2000,
    seed: int = RANDOM_SEED,
) -> Dict[str, Any]:
    """Calculates 95% circular block-bootstrap confidence interval on monthly net excess return."""
    if len(monthly_excess_returns) < block_len * 2:
        return {"ci_lower_pct": 0.0, "ci_upper_pct": 0.0, "mean_pct": 0.0, "samples": len(monthly_excess_returns)}

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

    ci_lower = boot_means[lower_idx] * 100.0
    ci_upper = boot_means[upper_idx] * 100.0
    mean_val = float(np.mean(arr)) * 100.0

    return {
        "ci_lower_pct": round(ci_lower, 3),
        "ci_upper_pct": round(ci_upper, 3),
        "mean_pct": round(mean_val, 3),
        "n_resamples": n_resamples,
        "block_length": block_len,
        "strictly_positive_ci": bool(ci_lower > 0.0),
    }


def run_random_portfolio_control(
    engine: Cycle3ResearchEngine,
    candidate_excess_ann: float,
    capital: float = 500000.0,
    n_sims: int = 1000,
) -> Dict[str, Any]:
    """Runs Control B: 1,000 independent random selection matched portfolios."""
    print(f"Running Control B: {n_sims} Random Selection Portfolios...", flush=True)
    rng = np.random.RandomState(RANDOM_SEED)
    random_excess_returns = []

    for _ in range(n_sims):
        sim_res = engine.run_portfolio_strategy(
            strategy_name="C1b_BASELINE",
            capital=capital,
            buffered=False,
            random_selection=True,
            rng=rng,
        )
        random_excess_returns.append(sim_res["annualized_excess_return_pct"])

    random_excess_returns.sort()
    p95 = float(np.percentile(random_excess_returns, 95))
    p50 = float(np.percentile(random_excess_returns, 50))
    p05 = float(np.percentile(random_excess_returns, 5))

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


def main():
    start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print("==================================================================", flush=True)
    print("RESEARCH CYCLE 3: INDEPENDENT SWING STRATEGY TESTING", flush=True)
    print("Strictly Offline Research — Pre-Registered Protocol", flush=True)
    print("==================================================================", flush=True)

    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    prereg_sha256 = hashlib.sha256(open("research/next_cycle/PREREG.md", "rb").read()).hexdigest()
    universe_sha256 = hashlib.sha256(open("data/universe/research_universe_v1.csv", "rb").read()).hexdigest()
    snap_sha256 = hashlib.sha256(open("data/research/research_snapshot_20261106.parquet", "rb").read()).hexdigest()
    bench_sha256 = hashlib.sha256(open("data/research/benchmark_series.parquet", "rb").read()).hexdigest()

    print(f"Git HEAD Commit: {git_sha}", flush=True)
    print(f"PREREG.md SHA256: {prereg_sha256}", flush=True)
    print(f"Universe SHA256: {universe_sha256}", flush=True)

    engine = Cycle3ResearchEngine()

    results: Dict[str, Any] = {
        "execution_meta": {
            "timestamp": start_time,
            "git_commit": git_sha,
            "prereg_sha256": prereg_sha256,
            "universe_sha256": universe_sha256,
            "snapshot_sha256": snap_sha256,
            "benchmark_sha256": bench_sha256,
            "random_seed": RANDOM_SEED,
            "market": "IN",
            "benchmark": "NIFTYBEES.NS",
            "regime_index": "^NSEI",
        },
        "strategies": {},
        "controls": {},
        "bootstrap_ci": {},
        "scale_comparison_17500": {},
    }

    # 1. Baseline Comparator C1b India (No Buffer & Buffered)
    print("\n--- Running Baseline Comparator: C1b India (INR 500k) ---", flush=True)
    c1b_raw = engine.run_portfolio_strategy("C1b_BASELINE", capital=500000.0, buffered=False)
    c1b_buf = engine.run_portfolio_strategy("C1b_BASELINE", capital=500000.0, buffered=True)
    c1b_raw_17k = engine.run_portfolio_strategy("C1b_BASELINE", capital=17500.0, buffered=False)

    # 2. Candidate 1: Residual Momentum (No Buffer & Buffered)
    print("\n--- Running Candidate 1: Residual Momentum (Blitz et al., 2011) ---", flush=True)
    c1_raw = engine.run_portfolio_strategy("CAND1_RESIDUAL_MOMENTUM", capital=500000.0, buffered=False)
    c1_buf = engine.run_portfolio_strategy("CAND1_RESIDUAL_MOMENTUM", capital=500000.0, buffered=True)
    c1_raw_17k = engine.run_portfolio_strategy("CAND1_RESIDUAL_MOMENTUM", capital=17500.0, buffered=False)

    # 3. Candidate 2: Frog-in-the-Pan Momentum (No Buffer & Buffered)
    print("\n--- Running Candidate 2: Frog-in-the-Pan (Da et al., 2014) ---", flush=True)
    c2_raw = engine.run_portfolio_strategy("CAND2_FROG_IN_THE_PAN", capital=500000.0, buffered=False)
    c2_buf = engine.run_portfolio_strategy("CAND2_FROG_IN_THE_PAN", capital=500000.0, buffered=True)
    c2_raw_17k = engine.run_portfolio_strategy("CAND2_FROG_IN_THE_PAN", capital=17500.0, buffered=False)

    # 4. Candidate 3: Connors RSI(2) Mean Reversion (INR 500k and INR 17.5k)
    print("\n--- Running Candidate 3: Connors RSI(2) Daily Swing (INR 500k & INR 17.5k) ---", flush=True)
    c3_500k = engine.run_candidate3_simulation(capital=500000.0)
    c3_17k = engine.run_candidate3_simulation(capital=17500.0)

    # 5. Bootstrap Confidence Intervals on Monthly Net Excess Returns
    print("\n--- Computing 95% Circular Block-Bootstrap Confidence Intervals ---", flush=True)
    boot_c1b = run_block_bootstrap_ci([r["monthly_excess_return"] for r in c1b_raw["monthly_records"]])
    boot_c1b_buf = run_block_bootstrap_ci([r["monthly_excess_return"] for r in c1b_buf["monthly_records"]])
    boot_c1 = run_block_bootstrap_ci([r["monthly_excess_return"] for r in c1_raw["monthly_records"]])
    boot_c1_buf = run_block_bootstrap_ci([r["monthly_excess_return"] for r in c1_buf["monthly_records"]])
    boot_c2 = run_block_bootstrap_ci([r["monthly_excess_return"] for r in c2_raw["monthly_records"]])
    boot_c2_buf = run_block_bootstrap_ci([r["monthly_excess_return"] for r in c2_buf["monthly_records"]])

    # 6. Control B: 1,000 Random Selection Matched Portfolios
    print("\n--- Running Control B: Random Selection Matched Portfolios ---", flush=True)
    ctrl_b = run_random_portfolio_control(engine, candidate_excess_ann=c1_raw["annualized_excess_return_pct"])

    # Save Trade Ledgers to CSV
    trades_dir = Path("research/next_cycle/trades")
    trades_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(c1b_raw["trade_ledger"]).to_csv(trades_dir / "c1b_comparator_trades.csv", index=False)
    pd.DataFrame(c1b_buf["trade_ledger"]).to_csv(trades_dir / "c1b_comparator_buffered_trades.csv", index=False)
    pd.DataFrame(c1_raw["trade_ledger"]).to_csv(trades_dir / "cand1_residual_momentum_trades.csv", index=False)
    pd.DataFrame(c1_buf["trade_ledger"]).to_csv(trades_dir / "cand1_residual_momentum_buffered_trades.csv", index=False)
    pd.DataFrame(c2_raw["trade_ledger"]).to_csv(trades_dir / "cand2_frog_in_the_pan_trades.csv", index=False)
    pd.DataFrame(c2_buf["trade_ledger"]).to_csv(trades_dir / "cand2_frog_in_the_pan_buffered_trades.csv", index=False)
    pd.DataFrame(c3_500k["completed_trades"]).to_csv(trades_dir / "cand3_connors_rsi2_trades.csv", index=False)
    pd.DataFrame(c3_17k["completed_trades"]).to_csv(trades_dir / "cand3_connors_rsi2_practical17k_trades.csv", index=False)
    print(f"Saved all trade ledgers to {trades_dir}/", flush=True)

    # Strip huge lists from main comparison JSON to keep it readable, but keep summaries
    def strip_records(res: Dict[str, Any]) -> Dict[str, Any]:
        cp = dict(res)
        cp.pop("monthly_records", None)
        cp.pop("trade_ledger", None)
        cp.pop("completed_trades", None)
        cp.pop("equity_curve", None)
        return cp

    results["strategies"]["C1b_Baseline_NoBuffer"] = strip_records(c1b_raw)
    results["strategies"]["C1b_Baseline_Buffered"] = strip_records(c1b_buf)
    results["strategies"]["Cand1_Residual_Momentum_NoBuffer"] = strip_records(c1_raw)
    results["strategies"]["Cand1_Residual_Momentum_Buffered"] = strip_records(c1_buf)
    results["strategies"]["Cand2_Frog_in_the_Pan_NoBuffer"] = strip_records(c2_raw)
    results["strategies"]["Cand2_Frog_in_the_Pan_Buffered"] = strip_records(c2_buf)
    results["strategies"]["Cand3_Connors_RSI2_Research500k"] = strip_records(c3_500k)
    results["strategies"]["Cand3_Connors_RSI2_Practical17k"] = strip_records(c3_17k)

    results["bootstrap_ci"]["C1b_Baseline_NoBuffer"] = boot_c1b
    results["bootstrap_ci"]["C1b_Baseline_Buffered"] = boot_c1b_buf
    results["bootstrap_ci"]["Cand1_Residual_Momentum_NoBuffer"] = boot_c1
    results["bootstrap_ci"]["Cand1_Residual_Momentum_Buffered"] = boot_c1_buf
    results["bootstrap_ci"]["Cand2_Frog_in_the_Pan_NoBuffer"] = boot_c2
    results["bootstrap_ci"]["Cand2_Frog_in_the_Pan_Buffered"] = boot_c2_buf

    results["controls"]["Candidate1_MarketSector_Random_Control_B"] = ctrl_b
    results["controls"]["Candidate2_FrogInThePan_Random_Control"] = {
        "status": "NOT RUN / NOT DEMONSTRATED",
        "reason": "Independent matched random cohort control was not executed for Candidate 2"
    }
    results["controls"]["Candidate3_Connors_RSI2_Random_Control"] = {
        "status": "NOT RUN / NOT DEMONSTRATED",
        "reason": "Independent matched random trade control was not executed for Candidate 3"
    }
    results["strategies"]["Blitz_Huij_Martens_2011_Published_Residual_Momentum"] = {
        "status": "NOT IMPLEMENTED",
        "reason": "Absence of historical Indian SMB and HML Fama-French factors, historical balance sheet book-to-market data, and pre-2021 history in frozen snapshot"
    }

    results["scale_comparison_17500"] = {
        "C1b_Baseline": {
            "capital_500k_ann_ret_pct": c1b_raw["annualized_net_return_pct"],
            "capital_17k_ann_ret_pct": c1b_raw_17k["annualized_net_return_pct"],
            "capital_500k_cost_drag_pct": c1b_raw["cost_drag_pct_of_capital"],
            "capital_17k_cost_drag_pct": c1b_raw_17k["cost_drag_pct_of_capital"],
            "drag_differential_pct": round(c1b_raw_17k["cost_drag_pct_of_capital"] - c1b_raw["cost_drag_pct_of_capital"], 2),
        },
        "Cand1_Residual_Momentum": {
            "capital_500k_ann_ret_pct": c1_raw["annualized_net_return_pct"],
            "capital_17k_ann_ret_pct": c1_raw_17k["annualized_net_return_pct"],
            "capital_500k_cost_drag_pct": c1_raw["cost_drag_pct_of_capital"],
            "capital_17k_cost_drag_pct": c1_raw_17k["cost_drag_pct_of_capital"],
            "drag_differential_pct": round(c1_raw_17k["cost_drag_pct_of_capital"] - c1_raw["cost_drag_pct_of_capital"], 2),
        },
        "Cand2_Frog_in_the_Pan": {
            "capital_500k_ann_ret_pct": c2_raw["annualized_net_return_pct"],
            "capital_17k_ann_ret_pct": c2_raw_17k["annualized_net_return_pct"],
            "capital_500k_cost_drag_pct": c2_raw["cost_drag_pct_of_capital"],
            "capital_17k_cost_drag_pct": c2_raw_17k["cost_drag_pct_of_capital"],
            "drag_differential_pct": round(c2_raw_17k["cost_drag_pct_of_capital"] - c2_raw["cost_drag_pct_of_capital"], 2),
        },
        "Cand3_Connors_RSI2": {
            "capital_500k_ann_ret_pct": c3_500k["annualized_net_return_pct"],
            "capital_17k_ann_ret_pct": c3_17k["annualized_net_return_pct"],
            "capital_500k_cost_drag_pct": c3_500k["cost_drag_pct_of_capital"],
            "capital_17k_cost_drag_pct": c3_17k["cost_drag_pct_of_capital"],
            "drag_differential_pct": round(c3_17k["cost_drag_pct_of_capital"] - c3_500k["cost_drag_pct_of_capital"], 2),
        },
    }

    # Save JSON results
    json_path = Path("research/next_cycle/strategy_comparison.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=json_serializer)
    print(f"Saved machine-readable results to {json_path}", flush=True)

    # Save Run Manifest
    end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest = {
        "manifest_version": "1.0",
        "cycle": "Research Cycle 3 — Independent Swing Strategy Testing",
        "created_at": end_time,
        "execution_start": start_time,
        "execution_end": end_time,
        "git_commit": git_sha,
        "files_and_hashes": {
            "research/next_cycle/PREREG.md": prereg_sha256,
            "data/universe/research_universe_v1.csv": universe_sha256,
            "data/research/research_snapshot_20261106.parquet": snap_sha256,
            "data/research/benchmark_series.parquet": bench_sha256,
            "research/next_cycle/strategy_comparison.json": hashlib.sha256(open(json_path, "rb").read()).hexdigest(),
        },
        "cost_model": {
            "brokerage": "0.0 INR flat delivery",
            "stt_buy_pct": 0.10,
            "stt_sell_pct": 0.10,
            "exchange_charges_pct": 0.003,
            "sebi_charges_per_crore_inr": 10.0,
            "stamp_duty_buy_pct": 0.015,
            "dp_charges_per_sold_scrip_inr": 15.93,
            "gst_pct": 18.0,
            "slippage_pct": 0.10,
        },
        "capital_evaluations": {
            "research_capital_inr": 500000.0,
            "practical_scale_inr": 17500.0,
        },
        "verdict_protocol": "Exploratory historical screening — no untouched holdout exists.",
    }

    manifest_path = Path("research/next_cycle/run_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=json_serializer)
    print(f"Saved run manifest to {manifest_path}", flush=True)

    print("\n==================================================================", flush=True)
    print("CYCLE 3 EXECUTION COMPLETE", flush=True)
    print("==================================================================", flush=True)


if __name__ == "__main__":
    main()
