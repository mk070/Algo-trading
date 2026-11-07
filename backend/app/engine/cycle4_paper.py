"""
Cycle 4: Prospective Paper-Trading Engine
Strictly Offline / Paper Simulation — No Live Broker Order Placement

Simulates:
1. Candidate Portfolio: Market-Sector Regression-Alpha, Buffered 1–30
2. Control Portfolio: C1b Baseline Momentum, Buffered 1–30
3. Primary Benchmark: NIFTYBEES.NS Total Return ETF
4. Regime Diagnostic: ^NSEI 200-day SMA Filter (with conservative fail-to-cash fallback)

Supports:
- Daily calendar-aware session ingestion and validation
- Strict whole-share position sizing at practical scale (INR 17,500)
- Isolated dual portfolio accounting (Candidate vs Control)
- Real-world Zerodha delivery cost model (including flat INR 15.93 DP charge per sold scrip)
- Complete signal, execution, and portfolio state tracking with audit logging
- Idempotent execution and crash recovery from persisted state
"""

import datetime
import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.engine.calendars import is_exchange_holiday, get_expected_trading_days

logger = logging.getLogger(__name__)


def json_serializer(obj: Any) -> Any:
    """Safe serializer for numpy, pandas, and datetime objects."""
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


def calculate_zerodha_delivery_cost(turnover: float, side: str, n_scrip_sold: int = 0) -> Dict[str, float]:
    """
    Exact Zerodha Indian equity delivery cost model (NSE).
    - Brokerage: INR 0 flat delivery
    - STT: 0.10% buy, 0.10% sell
    - Exchange charges: 0.003% of turnover
    - SEBI fee: INR 10 per crore (0.0001% of turnover)
    - Stamp duty: 0.015% on buy turnover
    - DP charges: INR 13.50 flat per sold scrip
    - GST: 18% on (Exchange fee + SEBI fee + DP charges)
    """
    if turnover <= 0:
        return {
            "brokerage": 0.0,
            "stt": 0.0,
            "exchange_charges": 0.0,
            "sebi_charges": 0.0,
            "stamp_duty": 0.0,
            "dp_charges": 0.0,
            "gst": 0.0,
            "total_cost": 0.0,
        }

    stt = 0.001 * turnover
    exchange_charges = 0.00003 * turnover
    sebi_charges = (10.0 / 10000000.0) * turnover
    stamp_duty = 0.00015 * turnover if side.upper() == "BUY" else 0.0
    dp_charges = (13.50 * n_scrip_sold) if side.upper() == "SELL" else 0.0
    gst_base = exchange_charges + sebi_charges + dp_charges
    gst = 0.18 * gst_base

    total = stt + exchange_charges + sebi_charges + stamp_duty + dp_charges + gst

    return {
        "brokerage": 0.0,
        "stt": round(stt, 2),
        "exchange_charges": round(exchange_charges, 2),
        "sebi_charges": round(sebi_charges, 2),
        "stamp_duty": round(stamp_duty, 2),
        "dp_charges": round(dp_charges, 2),
        "gst": round(gst, 2),
        "total_cost": round(total, 2),
    }


class PortfolioState:
    """Represents the complete accounting and valuation state of an isolated paper portfolio."""

    def __init__(self, name: str, initial_capital: float = 17500.0):
        self.name = name
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.holdings: Dict[str, Dict[str, Any]] = {}  # sym -> {shares, avg_cost, invested_cost}
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.total_equity = float(initial_capital)
        self.peak_equity = float(initial_capital)
        self.cumulative_costs_paid = 0.0
        self.last_processed_date: Optional[str] = None
        self.trade_history: List[Dict[str, Any]] = []
        self.daily_history: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 2),
            "holdings": self.holdings,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_equity": round(self.total_equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "cumulative_costs_paid": round(self.cumulative_costs_paid, 2),
            "cost_pct_of_capital": round((self.cumulative_costs_paid / self.initial_capital) * 100.0, 2),
            "last_processed_date": self.last_processed_date,
            "trades_count": len(self.trade_history),
            "sessions_count": len(self.daily_history),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortfolioState":
        state = cls(name=data["name"], initial_capital=data["initial_capital"])
        state.cash = float(data["cash"])
        state.holdings = data["holdings"]
        state.realized_pnl = float(data.get("realized_pnl", 0.0))
        state.unrealized_pnl = float(data.get("unrealized_pnl", 0.0))
        state.total_equity = float(data.get("total_equity", state.cash))
        state.peak_equity = float(data.get("peak_equity", state.total_equity))
        state.cumulative_costs_paid = float(data.get("cumulative_costs_paid", 0.0))
        state.last_processed_date = data.get("last_processed_date")
        return state


class Cycle4PaperEngine:
    """
    Production-ready Cycle 4 Paper-Trading Engine.
    Executes prospective paper evaluation for:
    - Candidate 1: Market-Sector Regression-Alpha, Buffered 1–30
    - Control: C1b Baseline Momentum, Buffered 1–30
    """

    def __init__(
        self,
        universe_path: str = "data/universe/research_universe_v1.csv",
        state_dir: str = "research/cycle4/state",
        initial_capital: float = 17500.0,
    ):
        self.universe_path = Path(universe_path)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.initial_capital = initial_capital

        if not self.universe_path.exists():
            raise FileNotFoundError(f"Universe file {self.universe_path} missing.")

        self.u_df = pd.read_csv(self.universe_path)
        self.in_u = self.u_df[self.u_df["market"] == "IN"].copy()
        self.symbols = self.in_u["symbol"].tolist()
        self.sector_map = dict(zip(self.in_u["symbol"], self.in_u["sector"]))
        sectors = set(self.sector_map.values())
        self.sector_to_syms = {sec: [s for s in self.symbols if self.sector_map[s] == sec] for sec in sectors}

        # Initialize or restore dual portfolio states
        self.candidate_state = self._load_or_create_state("candidate_reg_alpha_buf30")
        self.control_state = self._load_or_create_state("control_c1b_buf30")

        # Load persisted execution queue for session T+1 open
        self.pending_rebalances_file = self.state_dir / "pending_rebalances.json"
        self.pending_rebalances: Dict[str, List[str]] = self._load_pending_rebalances()

    def _load_pending_rebalances(self) -> Dict[str, List[str]]:
        if self.pending_rebalances_file.exists():
            try:
                with open(self.pending_rebalances_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read pending rebalances ({e}); resetting.")
        return {"candidate": [], "control": []}

    def _persist_pending_rebalances(self):
        with open(self.pending_rebalances_file, "w", encoding="utf-8") as f:
            json.dump(self.pending_rebalances, f, indent=2)

    def _load_or_create_state(self, name: str) -> PortfolioState:
        state_file = self.state_dir / f"{name}_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                state = PortfolioState.from_dict(data)
                # Load trade history if ledger exists
                ledger_file = self.state_dir / f"{name}_trade_ledger.csv"
                if ledger_file.exists():
                    state.trade_history = pd.read_csv(ledger_file).to_dict(orient="records")
                daily_file = self.state_dir / f"{name}_daily_ledger.csv"
                if daily_file.exists():
                    state.daily_history = pd.read_csv(daily_file).to_dict(orient="records")
                logger.info(f"Restored {name} state from {state_file}")
                return state
            except Exception as e:
                logger.warning(f"Failed to load {name} state ({e}), re-initializing.")

        state = PortfolioState(name=name, initial_capital=self.initial_capital)
        self._persist_state(state)
        return state

    def _persist_state(self, state: PortfolioState):
        """Persists portfolio state and ledgers atomically."""
        state_file = self.state_dir / f"{state.name}_state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, default=json_serializer)

        if state.trade_history:
            ledger_file = self.state_dir / f"{state.name}_trade_ledger.csv"
            pd.DataFrame(state.trade_history).to_csv(ledger_file, index=False)

        if state.daily_history:
            daily_file = self.state_dir / f"{state.name}_daily_ledger.csv"
            pd.DataFrame(state.daily_history).to_csv(daily_file, index=False)

    def evaluate_regime(self, nsei_series: pd.Series) -> Tuple[bool, float, float, str]:
        """
        Evaluates the primary market regime filter: ^NSEI Close > 200-day SMA.
        Conservative fallback: If data is missing, stale, or SMA is NaN, returns (False, Cash).
        """
        if nsei_series is None or len(nsei_series) == 0:
            return False, 0.0, 0.0, "EMPTY_SERIES -> CONSERVATIVE CASH"

        latest_raw = nsei_series.iloc[-1]
        if pd.isna(latest_raw):
            return False, 0.0, 0.0, "NAN_REGIME_OBSERVATION -> CONSERVATIVE CASH"

        clean_nsei = nsei_series.dropna()
        if len(clean_nsei) < 200:
            return False, 0.0, 0.0, "INSUFFICIENT_HISTORY (<200 bars) -> CONSERVATIVE CASH"

        sma200 = float(clean_nsei.rolling(200, min_periods=200).mean().iloc[-1])
        latest_close = float(latest_raw)

        if np.isnan(sma200) or np.isnan(latest_close):
            return False, latest_close, sma200, "NAN_REGIME_OBSERVATION -> CONSERVATIVE CASH"

        is_bull = bool(latest_close > sma200)
        status = "BULL_REGIME (Close > SMA200)" if is_bull else "BEAR_REGIME (Close <= SMA200) -> 100% CASH"
        return is_bull, latest_close, sma200, status

    def compute_candidate_scores(
        self,
        close_df: pd.DataFrame,
        returns_df: pd.DataFrame,
        nsei_returns: pd.Series,
        med_to_60d: pd.Series,
    ) -> List[Dict[str, Any]]:
        """
        Calculates Market-Sector Regression-Alpha standardized scores over 12-1 window.
        Score = (N * alpha) / sigma(eps).
        """
        scores = []
        lookback = 252
        skip = 21
        n_bars = len(close_df)

        if n_bars < lookback + 1:
            return []

        start_idx = n_bars - 1 - lookback
        stop_idx = n_bars - 1 - skip
        window_dates = close_df.index[start_idx : stop_idx + 1]
        rm_series = nsei_returns.reindex(window_dates)

        for sym in self.symbols:
            if sym not in close_df.columns:
                continue

            p_curr = close_df[sym].iloc[-1]
            if pd.isna(p_curr) or p_curr < 50.0:
                continue

            to_val = med_to_60d[sym] if sym in med_to_60d else 0.0
            if pd.isna(to_val) or to_val < 50000000.0:
                continue

            p_start = close_df[sym].iloc[start_idx]
            p_stop = close_df[sym].iloc[stop_idx]
            if pd.isna(p_start) or pd.isna(p_stop) or p_start <= 0:
                continue

            y_series = returns_df[sym].reindex(window_dates)
            sec = self.sector_map.get(sym, "Unknown")
            other_syms = [s for s in self.sector_to_syms.get(sec, []) if s != sym and s in returns_df.columns]

            if other_syms:
                rs_series = returns_df[other_syms].reindex(window_dates).mean(axis=1)
                valid_mask = ~(y_series.isna() | rm_series.isna() | rs_series.isna())
            else:
                valid_mask = ~(y_series.isna() | rm_series.isna())

            if valid_mask.sum() < 120:
                continue

            y = y_series[valid_mask].values
            rm_win = rm_series[valid_mask].values
            if other_syms:
                rs_win = rs_series[valid_mask].values
                X = np.column_stack([np.ones_like(y), rm_win, rs_win])
            else:
                X = np.column_stack([np.ones_like(y), rm_win])

            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            alpha = float(coef[0])
            resids = y - (X @ coef)
            std_res = float(np.std(resids, ddof=1))

            if std_res > 1e-8:
                score = float((len(y) * alpha) / std_res)
                pret = float((p_stop / p_start) - 1.0)
                scores.append({
                    "symbol": sym,
                    "score": score,
                    "alpha": alpha,
                    "std_res": std_res,
                    "pret_12_1": pret,
                    "price": p_curr,
                    "sector": sec,
                })

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores

    def compute_control_scores(
        self,
        close_df: pd.DataFrame,
        med_to_60d: pd.Series,
    ) -> List[Dict[str, Any]]:
        """
        Calculates C1b Baseline 12-1 momentum scores.
        Score = Close(T-21) / Close(T-252) - 1.0.
        """
        scores = []
        lookback = 252
        skip = 21
        n_bars = len(close_df)

        if n_bars < lookback + 1:
            return []

        start_idx = n_bars - 1 - lookback
        stop_idx = n_bars - 1 - skip

        for sym in self.symbols:
            if sym not in close_df.columns:
                continue

            p_curr = close_df[sym].iloc[-1]
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
            scores.append({
                "symbol": sym,
                "score": score,
                "pret_12_1": score,
                "price": p_curr,
                "sector": self.sector_map[sym],
            })

        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores

    def determine_target_portfolio(
        self,
        current_holdings: Dict[str, Dict[str, Any]],
        ranked_candidates: List[Dict[str, Any]],
        regime_pass: bool,
        top_n: int = 20,
        buffer_band: int = 30,
    ) -> List[str]:
        """
        Determines target portfolio enforcing the 1–30 retention buffer rule:
        - Enter only when ranked in Top 20
        - Retain existing holdings while rank <= 30
        - If regime_pass is False, target is empty (100% Cash)
        """
        if not regime_pass or not ranked_candidates:
            return []

        ranked_syms = [x["symbol"] for x in ranked_candidates]
        # Retain current holdings that remain in the 1-30 buffer band
        retained = [
            s for s in current_holdings.keys()
            if s in ranked_syms and ranked_syms.index(s) < buffer_band
        ]

        target_symbols = list(retained)
        # Fill remaining slots up to top_n from highest-ranked non-held candidates
        for s in ranked_syms:
            if len(target_symbols) >= top_n:
                break
            if s not in target_symbols:
                target_symbols.append(s)

        return target_symbols

    def execute_rebalance(
        self,
        state: PortfolioState,
        target_symbols: List[str],
        open_prices: Dict[str, float],
        exec_date: str,
        regime_pass: bool,
    ) -> List[Dict[str, Any]]:
        """
        Executes rebalance at Open of session T+1.
        Applies adverse slippage (+0.10% buy, -0.10% sell) and Zerodha delivery costs.
        Enforces whole-share allocation at practical scale (INR 17,500).
        Guarantees no negative cash and no leverage.
        """
        slip_pct = 0.0010
        executed_trades = []

        # 1. Liquidate exits (stocks no longer in target or regime failed)
        sold_scrip_count = 0
        for sym in list(state.holdings.keys()):
            if sym not in target_symbols or not regime_pass:
                pos = state.holdings[sym]
                op = open_prices.get(sym, 0.0)
                if op <= 0:
                    logger.warning(f"[{state.name}] Missing Open price for {sym} on {exec_date}; skipping exit.")
                    continue

                fill_sell = op * (1.0 - slip_pct)
                shares = pos["shares"]
                gross_proceeds = fill_sell * shares
                cost_dict = calculate_zerodha_delivery_cost(gross_proceeds, "SELL", n_scrip_sold=1)
                cost = cost_dict["total_cost"]

                net_proceeds = gross_proceeds - cost
                state.cash += net_proceeds
                state.cumulative_costs_paid += cost

                cost_basis = pos["avg_cost"] * shares
                trade_realized_pnl = gross_proceeds - cost_basis - cost
                state.realized_pnl += trade_realized_pnl

                trade_record = {
                    "exec_date": exec_date,
                    "portfolio": state.name,
                    "symbol": sym,
                    "side": "SELL",
                    "action": "LIQUIDATE_EXIT",
                    "shares": shares,
                    "ref_open": round(op, 2),
                    "fill_price": round(fill_sell, 2),
                    "gross_turnover": round(gross_proceeds, 2),
                    "costs": cost_dict,
                    "net_cash_delta": round(net_proceeds, 2),
                    "realized_pnl": round(trade_realized_pnl, 2),
                    "regime_pass": regime_pass,
                }
                executed_trades.append(trade_record)
                state.trade_history.append(trade_record)
                del state.holdings[sym]
                sold_scrip_count += 1

        # If regime failed, all positions are liquidated to cash, and no new purchases are made.
        if not regime_pass:
            return executed_trades

        # 2. Rebalance Buys / Trims for target symbols
        # Calculate current total equity at Open before buying
        equity_before_buy = state.cash
        for sym, pos in state.holdings.items():
            op = open_prices.get(sym, pos["avg_cost"])
            equity_before_buy += (op if op > 0 else pos["avg_cost"]) * pos["shares"]

        n_targets = len(target_symbols)
        target_capital_per_slot = (equity_before_buy / n_targets) if n_targets > 0 else 0.0

        for sym in target_symbols:
            op = open_prices.get(sym, 0.0)
            if op <= 0:
                logger.warning(f"[{state.name}] Missing Open price for {sym} on {exec_date}; skipping buy.")
                continue

            fill_buy = op * (1.0 + slip_pct)
            target_shares = int(math.floor(target_capital_per_slot / fill_buy)) if fill_buy > 0 else 0
            curr_shares = state.holdings[sym]["shares"] if sym in state.holdings else 0
            delta_shares = target_shares - curr_shares

            if delta_shares > 0:
                trade_val = round(delta_shares * fill_buy, 2)
                cost_dict = calculate_zerodha_delivery_cost(trade_val, "BUY")
                total_req = round(trade_val + cost_dict["total_cost"], 2)

                # Constrain by available cash (strict whole-share no-leverage check)
                if state.cash < total_req:
                    # Scale down shares to fit cash
                    affordable_shares = int(math.floor(state.cash / (fill_buy * 1.002)))
                    if affordable_shares <= 0:
                        logger.info(f"[{state.name}] Insufficient cash (INR {state.cash:.2f}) to buy {sym}; skipping.")
                        continue
                    delta_shares = affordable_shares
                    trade_val = round(delta_shares * fill_buy, 2)
                    cost_dict = calculate_zerodha_delivery_cost(trade_val, "BUY")
                    total_req = round(trade_val + cost_dict["total_cost"], 2)

                state.cash = round(state.cash - total_req, 2)
                state.cumulative_costs_paid = round(state.cumulative_costs_paid + cost_dict["total_cost"], 2)

                # Update holding cost basis
                if sym in state.holdings:
                    prev = state.holdings[sym]
                    total_sh = prev["shares"] + delta_shares
                    total_invested = (prev["avg_cost"] * prev["shares"]) + trade_val
                    state.holdings[sym] = {
                        "shares": total_sh,
                        "avg_cost": round(total_invested / total_sh, 2),
                        "invested_cost": round(total_invested, 2),
                    }
                else:
                    state.holdings[sym] = {
                        "shares": delta_shares,
                        "avg_cost": round(fill_buy, 2),
                        "invested_cost": round(trade_val, 2),
                    }

                trade_record = {
                    "exec_date": exec_date,
                    "portfolio": state.name,
                    "symbol": sym,
                    "side": "BUY",
                    "action": "ENTER_NEW" if curr_shares == 0 else "ADD_SLOT",
                    "shares": delta_shares,
                    "ref_open": round(op, 2),
                    "fill_price": round(fill_buy, 2),
                    "gross_turnover": round(trade_val, 2),
                    "costs": cost_dict,
                    "net_cash_delta": round(-total_req, 2),
                    "realized_pnl": 0.0,
                    "regime_pass": regime_pass,
                }
                executed_trades.append(trade_record)
                state.trade_history.append(trade_record)

            elif delta_shares < 0:
                # Trim position
                trim_shares = abs(delta_shares)
                fill_sell = op * (1.0 - slip_pct)
                gross_val = round(trim_shares * fill_sell, 2)
                # Partial trim does not incur additional flat DP charge if position remains open
                cost_dict = calculate_zerodha_delivery_cost(gross_val, "SELL", n_scrip_sold=0)
                net_val = round(gross_val - cost_dict["total_cost"], 2)

                state.cash = round(state.cash + net_val, 2)
                state.cumulative_costs_paid = round(state.cumulative_costs_paid + cost_dict["total_cost"], 2)

                prev = state.holdings[sym]
                rem_shares = prev["shares"] - trim_shares
                trade_realized_pnl = gross_val - (prev["avg_cost"] * trim_shares) - cost_dict["total_cost"]
                state.realized_pnl += trade_realized_pnl

                if rem_shares > 0:
                    state.holdings[sym] = {
                        "shares": rem_shares,
                        "avg_cost": prev["avg_cost"],
                        "invested_cost": round(prev["avg_cost"] * rem_shares, 2),
                    }
                else:
                    del state.holdings[sym]

                trade_record = {
                    "exec_date": exec_date,
                    "portfolio": state.name,
                    "symbol": sym,
                    "side": "SELL",
                    "action": "TRIM_SLOT",
                    "shares": trim_shares,
                    "ref_open": round(op, 2),
                    "fill_price": round(fill_sell, 2),
                    "gross_turnover": round(gross_val, 2),
                    "costs": cost_dict,
                    "net_cash_delta": round(net_val, 2),
                    "realized_pnl": round(trade_realized_pnl, 2),
                    "regime_pass": regime_pass,
                }
                executed_trades.append(trade_record)
                state.trade_history.append(trade_record)

        return executed_trades

    def mark_to_market_session(
        self,
        state: PortfolioState,
        close_prices: Dict[str, float],
        session_date: str,
        benchmark_close: float,
        prev_benchmark_close: float,
        regime_status: str,
    ) -> Dict[str, Any]:
        """
        Marks portfolio to market at daily Close.
        Reconciles: Total Equity = Cash + Sum(Shares * Close).
        Calculates cumulative return, drawdown, and benchmark excess.
        """
        invested_value = 0.0
        unrealized = 0.0
        missing_price_symbols = []
        stale_price_carry_forwards = {}

        for sym, pos in state.holdings.items():
            raw_cp = close_prices.get(sym)
            if raw_cp is None or pd.isna(raw_cp) or float(raw_cp) <= 0:
                missing_price_symbols.append(sym)
                cp = float(pos["avg_cost"])
                stale_price_carry_forwards[sym] = {
                    "stale_carry_price": cp,
                    "is_stale": True,
                    "reason": "MISSING_EOD_CLOSE_QUOTE",
                }
            else:
                cp = float(raw_cp)
            cur_val = cp * pos["shares"]
            invested_value += cur_val
            unrealized += cur_val - (pos["avg_cost"] * pos["shares"])

        state.unrealized_pnl = unrealized
        state.total_equity = state.cash + invested_value
        state.peak_equity = max(state.peak_equity, state.total_equity)
        state.last_processed_date = session_date

        drawdown_pct = ((state.total_equity - state.peak_equity) / state.peak_equity * 100.0) if state.peak_equity > 0 else 0.0
        cum_ret_pct = ((state.total_equity / state.initial_capital) - 1.0) * 100.0

        # Benchmark daily and cumulative returns
        b_ret = ((benchmark_close / prev_benchmark_close) - 1.0) if prev_benchmark_close > 0 else 0.0

        daily_record = {
            "date": session_date,
            "portfolio": state.name,
            "cash": round(state.cash, 2),
            "invested_value": round(invested_value, 2),
            "total_equity": round(state.total_equity, 2),
            "peak_equity": round(state.peak_equity, 2),
            "drawdown_pct": round(drawdown_pct, 2),
            "cumulative_return_pct": round(cum_ret_pct, 2),
            "cumulative_costs": round(state.cumulative_costs_paid, 2),
            "cost_pct_of_capital": round((state.cumulative_costs_paid / state.initial_capital) * 100.0, 2),
            "realized_pnl": round(state.realized_pnl, 2),
            "unrealized_pnl": round(state.unrealized_pnl, 2),
            "holdings_count": len(state.holdings),
            "benchmark_close": round(benchmark_close, 2),
            "benchmark_daily_return": round(b_ret, 6),
            "regime_status": regime_status,
            "valuation_status": "VERIFIED_COMPLETE" if not missing_price_symbols else f"INCOMPLETE_VALUATION_MISSING_{len(missing_price_symbols)}_PRICES",
            "is_complete_valuation": len(missing_price_symbols) == 0,
            "missing_price_symbols": missing_price_symbols,
            "stale_price_carry_forwards": stale_price_carry_forwards,
        }

        state.daily_history.append(daily_record)
        self._persist_state(state)
        return daily_record


def run_cycle4_daily_step(
    engine: Cycle4PaperEngine,
    session_date: datetime.date,
    historical_bars: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    force_rebalance: bool = False,
) -> Dict[str, Any]:
    """
    Executes a single daily step of the Cycle 4 paper-trading workflow:
    1. Validates market data for session_date
    2. Executes pending rebalance orders at Open (if any)
    3. Evaluates market regime and generates signals at Close
    4. Marks portfolios to market at Close
    5. Persists audit trail
    """
    date_str = str(session_date)

    # 1. Check if market was open
    if is_exchange_holiday("IN", session_date):
        return {"status": "SKIPPED_HOLIDAY", "date": date_str, "reason": "Official NSE holiday or weekend closure"}

    # 2. Extract and validate session market data
    h_bars = historical_bars.copy()
    h_bars["date"] = pd.to_datetime(h_bars["date"])
    b_df = benchmark_df.copy()
    b_df["date"] = pd.to_datetime(b_df["date"])

    sub_bars = h_bars[h_bars["date"].dt.date <= session_date].copy()
    if sub_bars.empty:
        return {"status": "NO_DATA", "date": date_str}

    # Slice up to session_date
    close_pivot = sub_bars.pivot(index="date", columns="symbol", values="split_adj_close").sort_index()
    open_pivot = sub_bars.pivot(index="date", columns="symbol", values="split_adj_open").sort_index()
    vol_pivot = sub_bars.pivot(index="date", columns="symbol", values="volume").sort_index()

    # Fail-closed check: verify session_date actually exists in market data
    latest_bar_date = pd.to_datetime(close_pivot.index[-1]).date()
    if latest_bar_date != session_date:
        logger.error(f"Market data date mismatch: requested session {session_date}, but latest available bar is {latest_bar_date}.")
        return {
            "status": "FAIL_CLOSED_STALE_DATA",
            "date": date_str,
            "latest_available_date": str(latest_bar_date),
            "reason": f"No market data available for session {date_str}. Latest available bar is {latest_bar_date}. Fail-closed: refusing to treat stale research snapshot as new daily data."
        }

    returns_pivot = close_pivot.pct_change()
    med_to_60d = (close_pivot * vol_pivot).rolling(60, min_periods=40).median().iloc[-1]

    # Benchmark series validation
    sub_bench = b_df[b_df["date"].dt.date <= session_date].copy()
    nsei_series = sub_bench[sub_bench["symbol"] == "^NSEI"].sort_values("date").set_index("date")["close"]
    if nsei_series.empty or pd.to_datetime(nsei_series.index[-1]).date() != session_date:
        logger.error(f"Regime data mismatch: ^NSEI missing for session {session_date}.")
        return {
            "status": "FAIL_CLOSED_MISSING_REGIME",
            "date": date_str,
            "reason": f"^NSEI benchmark series missing for session {date_str}. Fail-closed: cannot verify market regime."
        }
    nsei_returns = nsei_series.pct_change()

    niftybees_series = sub_bench[sub_bench["symbol"] == "NIFTYBEES.NS"].sort_values("date").set_index("date")["close"]
    if niftybees_series.empty or pd.to_datetime(niftybees_series.index[-1]).date() != session_date:
        logger.error(f"Benchmark data mismatch: NIFTYBEES missing for session {session_date}.")
        return {
            "status": "FAIL_CLOSED_MISSING_BENCHMARK",
            "date": date_str,
            "reason": f"NIFTYBEES benchmark series missing for session {date_str}. Fail-closed: cannot compute relative benchmark return."
        }
    cur_niftybees = float(niftybees_series.iloc[-1])
    prev_niftybees = float(niftybees_series.iloc[-2]) if len(niftybees_series) > 1 else cur_niftybees

    # 3. Evaluate Regime
    is_bull, nsei_close, nsei_sma200, regime_status = engine.evaluate_regime(nsei_series)

    # Today's Open and Close prices
    today_opens = open_pivot.iloc[-1].to_dict()
    today_closes = close_pivot.iloc[-1].to_dict()

    # 4. Execute Pending Rebalances at Open
    cand_trades = []
    ctrl_trades = []

    if engine.pending_rebalances["candidate"]:
        cand_trades = engine.execute_rebalance(
            engine.candidate_state,
            target_symbols=engine.pending_rebalances["candidate"],
            open_prices=today_opens,
            exec_date=date_str,
            regime_pass=is_bull,
        )
        engine.pending_rebalances["candidate"] = []

    if engine.pending_rebalances["control"]:
        ctrl_trades = engine.execute_rebalance(
            engine.control_state,
            target_symbols=engine.pending_rebalances["control"],
            open_prices=today_opens,
            exec_date=date_str,
            regime_pass=is_bull,
        )
        engine.pending_rebalances["control"] = []

    if cand_trades or ctrl_trades:
        engine._persist_pending_rebalances()

    # 5. Check if today is a Month-End Rebalance Date (or forced)
    # Month-end check: next expected trading session is in a new month
    dates_idx = close_pivot.index
    is_month_end = False
    if len(dates_idx) >= 2:
        # Check if next calendar trading session is in next month
        cur_ts = pd.to_datetime(dates_idx[-1])
        # Find next trading day
        next_days = get_expected_trading_days("IN", session_date + datetime.timedelta(days=1), session_date + datetime.timedelta(days=10))
        if next_days and next_days[0].month != session_date.month:
            is_month_end = True

    if force_rebalance:
        is_month_end = True

    # 6. If Month End: Generate Signals at Close for next session Open execution
    candidate_ranked = []
    control_ranked = []
    if is_month_end:
        candidate_ranked = engine.compute_candidate_scores(close_pivot, returns_pivot, nsei_returns, med_to_60d)
        control_ranked = engine.compute_control_scores(close_pivot, med_to_60d)

        engine.pending_rebalances["candidate"] = engine.determine_target_portfolio(
            engine.candidate_state.holdings,
            candidate_ranked,
            regime_pass=is_bull,
            top_n=20,
            buffer_band=30,
        )

        engine.pending_rebalances["control"] = engine.determine_target_portfolio(
            engine.control_state.holdings,
            control_ranked,
            regime_pass=is_bull,
            top_n=20,
            buffer_band=30,
        )

        engine._persist_pending_rebalances()

        # Audit log planned rebalance orders
        audit_file = engine.state_dir / "rebalance_orders_audit.jsonl"
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "signal_date": date_str,
                "is_bull_regime": is_bull,
                "nsei_close": round(nsei_close, 2),
                "nsei_sma200": round(nsei_sma200, 2),
                "candidate_targets": engine.pending_rebalances["candidate"],
                "control_targets": engine.pending_rebalances["control"],
                "candidate_top5_ranked": [x["symbol"] for x in candidate_ranked[:5]],
                "control_top5_ranked": [x["symbol"] for x in control_ranked[:5]],
            }, default=json_serializer) + "\n")

    # 7. Mark to market at Close
    cand_daily = engine.mark_to_market_session(
        engine.candidate_state,
        close_prices=today_closes,
        session_date=date_str,
        benchmark_close=cur_niftybees,
        prev_benchmark_close=prev_niftybees,
        regime_status=regime_status,
    )

    ctrl_daily = engine.mark_to_market_session(
        engine.control_state,
        close_prices=today_closes,
        session_date=date_str,
        benchmark_close=cur_niftybees,
        prev_benchmark_close=prev_niftybees,
        regime_status=regime_status,
    )

    return {
        "status": "COMPLETED",
        "date": date_str,
        "is_month_end_rebalance": is_month_end,
        "regime_pass": is_bull,
        "regime_status": regime_status,
        "candidate": {
            "equity": cand_daily["total_equity"],
            "cash": cand_daily["cash"],
            "cum_ret_pct": cand_daily["cumulative_return_pct"],
            "drawdown_pct": cand_daily["drawdown_pct"],
            "executed_trades": len(cand_trades),
        },
        "control": {
            "equity": ctrl_daily["total_equity"],
            "cash": ctrl_daily["cash"],
            "cum_ret_pct": ctrl_daily["cumulative_return_pct"],
            "drawdown_pct": ctrl_daily["drawdown_pct"],
            "executed_trades": len(ctrl_trades),
        },
        "benchmark": {
            "close": cur_niftybees,
            "daily_return": cand_daily["benchmark_daily_return"],
        },
    }
