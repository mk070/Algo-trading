"""Strategy Lab — Backtest Engine.

Port of the cost and execution model from cycle4_paper.py and backtest/simulator.py.
Deterministic: same inputs + params always produce same trades.
No look-ahead: signals computed on bar[i] use only bars 0..i.
Entry: open of bar[i+1] with slippage.
Exit: time stop (holding_days) or stop-hit (whichever comes first).
"""

import hashlib
import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.engine.indicators import add_all_indicators, compute_atr_wilder
from app.lab.signals import SIGNAL_FUNCTIONS

logger = logging.getLogger(__name__)

# Cost model constants (Zerodha delivery)
STT_PCT = 0.001          # 0.1% each side
EXCHANGE_PCT = 0.00003   # 0.003%
SEBI_PER_CRORE = 10.0
STAMP_BUY_PCT = 0.00015  # 0.015% buy only
DP_FLAT_SELL = 13.50     # INR per sold scrip
GST_PCT = 0.18
SLIPPAGE_PCT = 0.0010    # 10 bps one-way


def compute_zerodha_cost(turnover: float, side: str) -> float:
    """Return total cost for a single leg (buy or sell) in INR."""
    if turnover <= 0:
        return 0.0
    stt = STT_PCT * turnover
    exc = EXCHANGE_PCT * turnover
    sebi = (SEBI_PER_CRORE / 10_000_000) * turnover
    stamp = STAMP_BUY_PCT * turnover if side.upper() == "BUY" else 0.0
    dp = DP_FLAT_SELL if side.upper() == "SELL" else 0.0
    gst = GST_PCT * (exc + sebi + dp)
    return stt + exc + sebi + stamp + dp + gst


def compute_round_trip_cost(entry_price: float, exit_price: float, qty: int) -> float:
    """Full round-trip cost (buy + sell) in INR."""
    buy_turn = entry_price * qty
    sell_turn = exit_price * qty
    return compute_zerodha_cost(buy_turn, "BUY") + compute_zerodha_cost(sell_turn, "SELL")


def compute_config_hash(strategy_id: str, params: Dict[str, Any], holding_days: int) -> str:
    """Deterministic SHA-256 hash of strategy configuration."""
    payload = json.dumps({
        "strategy_id": strategy_id,
        "params": params,
        "holding_days": holding_days,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


@dataclass
class LabTradeRecord:
    symbol: str
    strategy_id: str
    holding_days_target: int
    entry_date: Any
    entry_price: float
    exit_date: Optional[Any]
    exit_price: Optional[float]
    stop_price: Optional[float]
    qty: int
    gross_pnl: float
    costs: float
    net_pnl: float
    r_multiple: float
    exit_reason: str
    holding_days_actual: int


def run_single_strategy_backtest(
    strategy_id: str,
    params: Dict[str, Any],
    holding_days: int,
    bars_dict: Dict[str, pd.DataFrame],
    capital: float = 500_000.0,
    risk_pct: float = 0.5,
    max_positions: int = 5,
    stop_atr_mult: float = 1.5,
) -> Tuple[List[LabTradeRecord], Dict[str, Any]]:
    """
    Run a full backtest for one strategy/holding combination.

    Returns:
        (trades, summary_dict)

    Rules:
    - Entry: open of bar[i+1] * (1 + SLIPPAGE_PCT)
    - Exit on time: open of bar[entry_i + 1 + holding_days] * (1 - SLIPPAGE_PCT)
      (open of the bar AFTER holding_days bars have been held — conservative)
    - Stop: if any bar's low after entry falls below stop, exit at stop price
    - Max positions at any time: max_positions
    - Risk per trade: risk_pct% of capital
    - No re-entry in same symbol while in position
    - Deterministic: sorted by date then symbol
    """
    signal_fn = SIGNAL_FUNCTIONS.get(strategy_id)
    if signal_fn is None:
        raise ValueError(f"Unknown strategy: {strategy_id}")

    atr_mult = float(params.get("stop_atr_mult", stop_atr_mult))

    all_trades: List[LabTradeRecord] = []
    open_positions: Dict[str, Dict] = {}  # symbol -> position dict

    # Build unified sorted date list
    all_dates = sorted(set(
        d for df in bars_dict.values()
        for d in (df["date"].tolist() if "date" in df.columns else df.index.tolist())
    ))

    # Pre-compute signals for all symbols
    signals_dict: Dict[str, pd.Series] = {}
    enriched_dict: Dict[str, pd.DataFrame] = {}

    for sym, df in bars_dict.items():
        if len(df) < 50:
            continue
        df2 = df.copy()
        if "atr14" not in df2.columns:
            df2 = add_all_indicators(df2)
        enriched_dict[sym] = df2.reset_index(drop=True)
        try:
            sig = signal_fn(df2, params)
            signals_dict[sym] = sig.reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Signal error {strategy_id}/{sym}: {e}")

    # Risk per trade in INR
    risk_amount = capital * (risk_pct / 100.0)

    # Main loop — iterate date by date
    date_to_syms: Dict[Any, List[str]] = {}
    for sym, df in enriched_dict.items():
        date_col = df["date"] if "date" in df.columns else pd.Series(df.index)
        for i, d in enumerate(date_col):
            date_to_syms.setdefault(d, []).append(sym)

    for date_idx, today in enumerate(all_dates):
        syms_today = sorted(date_to_syms.get(today, []))

        # 1. Close positions that hit time stop or stop-loss on this bar
        to_close = []
        for sym, pos in list(open_positions.items()):
            if sym not in enriched_dict:
                continue
            df = enriched_dict[sym]
            date_col = df["date"] if "date" in df.columns else pd.Series(df.index)
            # Find row index for today
            row_idx = date_col[date_col == today].index
            if len(row_idx) == 0:
                continue
            i = row_idx[0]
            bar = df.iloc[i]

            days_held = pos.get("days_held", 0) + 1
            pos["days_held"] = days_held

            stop = pos.get("stop_price")
            # Check stop hit
            if stop is not None and bar["low"] <= stop:
                exit_price = max(stop, bar["low"]) * (1 - SLIPPAGE_PCT)
                to_close.append((sym, exit_price, today, "STOP_HIT"))
            elif days_held >= holding_days:
                # Time stop — exit at open of this bar (conservative: open after holding_days)
                exit_price = bar["open"] * (1 - SLIPPAGE_PCT)
                to_close.append((sym, exit_price, today, "TIME_EXIT"))

        for sym, exit_price, exit_date, reason in to_close:
            pos = open_positions.pop(sym)
            qty = pos["qty"]
            entry_price = pos["entry_price"]
            stop = pos.get("stop_price")
            gross_pnl = (exit_price - entry_price) * qty
            costs = compute_round_trip_cost(entry_price, exit_price, qty)
            net_pnl = gross_pnl - costs
            risk_per_share = max(abs(entry_price - stop), 0.01) if stop else (entry_price * 0.02)
            r_mult = net_pnl / (risk_per_share * qty) if risk_per_share > 0 else 0.0

            all_trades.append(LabTradeRecord(
                symbol=sym,
                strategy_id=strategy_id,
                holding_days_target=holding_days,
                entry_date=pos["entry_date"],
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=round(exit_price, 4),
                stop_price=stop,
                qty=qty,
                gross_pnl=round(gross_pnl, 2),
                costs=round(costs, 2),
                net_pnl=round(net_pnl, 2),
                r_multiple=round(r_mult, 4),
                exit_reason=reason,
                holding_days_actual=pos.get("days_held", holding_days),
            ))

        # 2. Check for new entry signals
        if len(open_positions) >= max_positions:
            continue

        for sym in syms_today:
            if sym in open_positions:
                continue
            if len(open_positions) >= max_positions:
                break
            if sym not in signals_dict or sym not in enriched_dict:
                continue

            df = enriched_dict[sym]
            sig = signals_dict[sym]
            date_col = df["date"] if "date" in df.columns else pd.Series(df.index)
            today_rows = date_col[date_col == today].index
            if len(today_rows) == 0:
                continue
            i = today_rows[0]
            if not sig.iloc[i]:
                continue

            # Need next bar for entry
            if i + 1 >= len(df):
                continue

            next_bar = df.iloc[i + 1]
            entry_price = float(next_bar["open"]) * (1 + SLIPPAGE_PCT)

            # Compute stop
            curr_bar = df.iloc[i]
            atr = curr_bar.get("atr14", entry_price * 0.02)
            if pd.isna(atr) or atr <= 0:
                atr = entry_price * 0.02
            stop_price = entry_price - atr_mult * float(atr)

            # S04: no stop (pure time exit)
            if strategy_id == "S04":
                stop_price = None

            # Position sizing
            risk_per_share = entry_price - stop_price if stop_price else entry_price * 0.02
            if risk_per_share <= 0:
                continue
            qty = max(1, int(risk_amount / risk_per_share))
            # Cap at 20% of capital
            max_val = capital * 0.20
            if qty * entry_price > max_val:
                qty = max(1, int(max_val / entry_price))

            # Cost check
            costs_est = compute_round_trip_cost(entry_price, entry_price, qty)
            cost_in_r = costs_est / (risk_per_share * qty) if risk_per_share * qty > 0 else 999
            if cost_in_r > 0.25:
                continue  # cost gate

            entry_date = date_col.iloc[i + 1] if i + 1 < len(date_col) else today
            open_positions[sym] = {
                "entry_price": entry_price,
                "stop_price": stop_price,
                "qty": qty,
                "entry_date": entry_date,
                "days_held": 0,
            }

    # Close any remaining open positions at last available price
    for sym, pos in open_positions.items():
        if sym in enriched_dict:
            df = enriched_dict[sym]
            last_row = df.iloc[-1]
            exit_price = float(last_row["close"]) * (1 - SLIPPAGE_PCT)
            last_date = last_row["date"] if "date" in last_row else last_row.name
            qty = pos["qty"]
            entry_price = pos["entry_price"]
            stop = pos.get("stop_price")
            gross_pnl = (exit_price - entry_price) * qty
            costs = compute_round_trip_cost(entry_price, exit_price, qty)
            net_pnl = gross_pnl - costs
            risk_per_share = abs(entry_price - stop) if stop else entry_price * 0.02
            r_mult = net_pnl / (risk_per_share * qty) if risk_per_share * qty > 0 else 0.0
            all_trades.append(LabTradeRecord(
                symbol=sym,
                strategy_id=strategy_id,
                holding_days_target=holding_days,
                entry_date=pos["entry_date"],
                entry_price=entry_price,
                exit_date=last_date,
                exit_price=round(exit_price, 4),
                stop_price=stop,
                qty=qty,
                gross_pnl=round(gross_pnl, 2),
                costs=round(costs, 2),
                net_pnl=round(net_pnl, 2),
                r_multiple=round(r_mult, 4),
                exit_reason="END_OF_DATA",
                holding_days_actual=pos.get("days_held", 0),
            ))

    # Compute summary stats
    summary = _compute_summary(all_trades, capital)
    return all_trades, summary


def _compute_summary(trades: List[LabTradeRecord], capital: float) -> Dict[str, Any]:
    MIN_SAMPLE = 100
    n = len(trades)
    if n == 0:
        return {
            "total_trades": 0,
            "win_rate": None,
            "expectancy_r": None,
            "median_net_expectancy": None,
            "avg_win_r": None,
            "avg_loss_r": None,
            "profit_factor": None,
            "cagr_pct": None,
            "max_drawdown_pct": None,
            "sharpe_ratio": None,
            "total_pnl": 0.0,
            "total_costs": 0.0,
            "sample_ok": False,
            "sample_label": "INSUFFICIENT_SAMPLE",
            "half1_expectancy": None,
            "half2_expectancy": None,
            "half_consistency": None,
        }

    pnls = np.array([t.net_pnl for t in trades])
    r_mults = np.array([t.r_multiple for t in trades])
    costs = np.array([t.costs for t in trades])

    wins = r_mults[r_mults > 0]
    losses = r_mults[r_mults <= 0]
    win_rate = len(wins) / n if n > 0 else 0.0
    avg_win_r = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss_r = float(np.mean(losses)) if len(losses) > 0 else 0.0
    expectancy_r = float(np.mean(r_mults)) if n > 0 else 0.0
    median_net_expectancy = float(np.median(r_mults)) if n > 0 else 0.0

    gross_profit = float(np.sum(pnls[pnls > 0])) if np.any(pnls > 0) else 0.0
    gross_loss = float(abs(np.sum(pnls[pnls < 0]))) if np.any(pnls < 0) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    total_pnl = float(np.sum(pnls))
    total_costs = float(np.sum(costs))

    # CAGR estimate
    dates = sorted([t.entry_date for t in trades if t.entry_date is not None])
    if len(dates) >= 2:
        import datetime
        d0, d1 = dates[0], dates[-1]
        if hasattr(d0, "toordinal"):
            years = (d1.toordinal() - d0.toordinal()) / 365.25
        else:
            years = 2.0
        years = max(years, 0.1)
        final_val = capital + total_pnl
        cagr_pct = ((final_val / capital) ** (1 / years) - 1) * 100 if capital > 0 else 0.0
    else:
        cagr_pct = 0.0

    # Max drawdown (simple, on cumulative PnL)
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak)
    max_dd_pct = float(abs(dd.min()) / capital * 100) if capital > 0 else 0.0

    # Sharpe (annualized, rough)
    if n > 1 and np.std(r_mults) > 0:
        sharpe = float(np.mean(r_mults) / np.std(r_mults) * math.sqrt(252 / max(1, int(np.mean([t.holding_days_actual for t in trades])))))
    else:
        sharpe = 0.0

    # Half-consistency
    half = n // 2
    h1 = float(np.median(r_mults[:half])) if half > 0 else 0.0
    h2 = float(np.median(r_mults[half:])) if (n - half) > 0 else 0.0
    if max(abs(h1), abs(h2)) > 0:
        half_consistency = min(h1, h2) / max(abs(h1), abs(h2)) if h1 >= 0 and h2 >= 0 else 0.0
    else:
        half_consistency = 0.0

    sample_ok = n >= MIN_SAMPLE
    sample_label = "SUFFICIENT" if sample_ok else "INSUFFICIENT_SAMPLE"

    return {
        "total_trades": n,
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(expectancy_r, 4),
        "median_net_expectancy": round(median_net_expectancy, 4),
        "avg_win_r": round(avg_win_r, 4),
        "avg_loss_r": round(avg_loss_r, 4),
        "profit_factor": round(profit_factor, 4),
        "cagr_pct": round(cagr_pct, 4),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "sharpe_ratio": round(sharpe, 4),
        "total_pnl": round(total_pnl, 2),
        "total_costs": round(total_costs, 2),
        "sample_ok": sample_ok,
        "sample_label": sample_label,
        "half1_expectancy": round(h1, 4),
        "half2_expectancy": round(h2, 4),
        "half_consistency": round(half_consistency, 4),
    }
