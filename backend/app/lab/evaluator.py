"""Strategy Lab — Forward Paper Evaluator.

This module implements deterministic, non-liquidating paper-trade evaluation.

Key contracts:
- Uses study's FROZEN configuration only. Never reads live strategy config.
- Signals on the latest available bar become TomorrowOrders; they do NOT become
  paper fills until the next session's actual bar is available.
- Open positions are preserved — no END_OF_DATA liquidation.
- Gap-through-stop: if next session opens below stop, fill at open (with slippage).
- Idempotent: same data + same config → same DB rows, no duplicates.
- Deterministic trade key: SHA-256(study_id|strategy_id|config_hash|symbol|entry_date_iso).

Engine version: v1.0 (2026-11-24)
"""

import datetime
import hashlib
import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set

import numpy as np
import pandas as pd

from app.engine.indicators import add_all_indicators
from app.lab.signals import SIGNAL_FUNCTIONS

logger = logging.getLogger(__name__)

ENGINE_VERSION = "v1.0"
SLIPPAGE_PCT = 0.0010   # 10 bps one-way
MIN_HISTORY_BARS = 220  # bars needed before study start for warm-up

# Zerodha delivery cost constants
_STT = 0.001
_EXC = 0.00003
_SEBI = 10.0 / 10_000_000
_STAMP = 0.00015
_DP = 13.50
_GST = 0.18


def _cost_leg(turnover: float, side: str) -> float:
    stt = _STT * turnover
    exc = _EXC * turnover
    sebi = _SEBI * turnover
    stamp = _STAMP * turnover if side == "BUY" else 0.0
    dp = _DP if side == "SELL" else 0.0
    gst = _GST * (exc + sebi + dp)
    return stt + exc + sebi + stamp + dp + gst


def _round_trip_cost(entry: float, exit_: float, qty: int) -> float:
    return _cost_leg(entry * qty, "BUY") + _cost_leg(exit_ * qty, "SELL")


def make_trade_key(study_id: str, strategy_id: str, config_hash: str, symbol: str, entry_date: Any) -> str:
    """Deterministic trade key — same params always produce same key."""
    raw = f"{study_id}|{strategy_id}|{config_hash}|{symbol}|{str(entry_date)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def make_order_key(study_id: str, strategy_id: str, config_hash: str, symbol: str, signal_date: Any) -> str:
    raw = f"order|{study_id}|{strategy_id}|{config_hash}|{symbol}|{str(signal_date)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


# ─── Reason text templates ────────────────────────────────────────────────────

REASON_TEMPLATES = {
    "S01": "EMA{ema_len} pullback with RSI{rsi_len} upward turn while above long-term trend filter.",
    "S02": "Closed above prior {donchian_len}-bar Donchian high with volume {vol_multiplier:.1f}x confirmation.",
    "S03": "Closed above {lookback}-day high with volume confirmation while above SMA50 and SMA200.",
    "S04": "RSI({rsi_len}) dropped below {rsi_oversold:.0f} (oversold) while above 200-day SMA — mean reversion setup.",
    "S05": "{consecutive_down} consecutive lower closes while above SMA50 and SMA200 — mean reversion dip.",
    "S06": "Closed back above lower Bollinger Band ({bb_len},{bb_std:.0f}σ) while above 200-day average.",
    "S07": "Gapped up {min_gap_pct:.0f}%+ at open with volume {vol_multiplier:.0f}x avg — pivot breakout.",
    "S08": "New {lookback_days}-day high with positive {rs_lookback_days}d relative strength and volume confirmation.",
    "S09": "NR{nr_bars} inside-day contraction — range compression before potential expansion.",
    "S10": "EMA{ema_fast}/EMA{ema_slow} bullish cross with volume confirmation above 200-day SMA.",
}


def build_reason_text(strategy_id: str, params: Dict[str, Any]) -> str:
    template = REASON_TEMPLATES.get(strategy_id, f"{strategy_id} signal.")
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return f"{strategy_id} signal triggered."


# ─── Main evaluator ───────────────────────────────────────────────────────────

@dataclass
class OpenPosition:
    symbol: str
    entry_date: Any
    entry_price: float
    stop_price: Optional[float]
    qty: int
    planned_exit_date: Any
    signal_date: Any
    reason_text: str
    signal_context: Dict[str, Any]
    trade_key: str
    days_held: int = 0
    is_stale_data: bool = False


@dataclass
class ClosedTrade:
    symbol: str
    strategy_id: str
    config_hash: str
    signal_date: Any
    entry_date: Any
    entry_price: float
    exit_date: Any
    exit_price: float
    stop_price: Optional[float]
    qty: int
    gross_pnl: float
    costs: float
    net_pnl: float
    r_multiple: float
    exit_reason: str
    planned_exit_date: Any
    reason_text: str
    signal_context: Dict[str, Any]
    trade_key: str
    holding_days_target: int


def evaluate_study(
    study_id: str,
    db,
    preloaded_bars: Optional[Dict[str, pd.DataFrame]] = None,
    preloaded_data_through_date: Optional[datetime.date] = None,
    allow_stale_for_test: bool = False,
) -> Dict[str, Any]:
    """
    Deterministic non-liquidating forward paper evaluator.

    Loads frozen study config, historical bars, and existing open positions.
    Returns a full evaluation result dict. All DB writes happen in the caller
    (persist_evaluation_result) to keep this function pure/testable.
    """
    from app.lab.models_lab import LabStudy, LabStudyStrategy, LabStrategy, LabPaperHolding

    # 1. Load frozen study config
    study = db.query(LabStudy).filter(LabStudy.id == study_id).first()
    if not study:
        raise ValueError(f"Study {study_id} not found")
    if study.status not in ("ACTIVE", "PAUSED"):
        return {"status": "SKIPPED", "reason": f"Study status is {study.status}"}

    study_strategies = db.query(LabStudyStrategy).filter(LabStudyStrategy.study_id == study_id).all()
    if not study_strategies:
        return {"status": "ERROR", "reason": "No strategies in study"}

    study_start = study.start_date
    capital = study.capital
    risk_pct = study.risk_pct
    max_positions = study.max_positions
    kill_threshold = study.kill_switch_threshold_pct / 100.0

    # 2. Load bars — use preloaded if provided (e.g. nightly batch), else load from Neon DB
    if preloaded_bars is not None:
        bars_dict = preloaded_bars
        data_through_date = preloaded_data_through_date
    else:
        from app.engine.research_loader import load_research_bars_for_paper
        bars_dict, data_through_date = load_research_bars_for_paper(db=db)

    if not bars_dict:
        return {"status": "ERROR", "reason": "No bars available for evaluation"}

    # 2b. Stale data check against exchange calendar (unless marked is_test or explicitly allowed)
    is_test_study = getattr(study, "is_test", False) or allow_stale_for_test
    expected_last_session = None
    if not is_test_study:
        from app.engine.calendars import get_last_completed_trading_session
        expected_last_session = get_last_completed_trading_session("IN")
        if data_through_date is None or data_through_date < expected_last_session:
            logger.warning(
                f"[Lab Evaluator] STALE DATA for study {study_id}: latest bar {data_through_date} "
                f"< expected last completed session {expected_last_session}."
            )
            return {
                "status": "STALE_DATA",
                "study_id": study_id,
                "reason": (
                    f"Market data through {data_through_date} is older than expected last "
                    f"completed NSE session ({expected_last_session}). Evaluation halted to avoid misleading results."
                ),
                "data_through_date": str(data_through_date) if data_through_date else None,
                "expected_session_date": str(expected_last_session),
            }

    # 2c. Per-symbol freshness check for open positions and symbols with signals
    stale_symbols: Set[str] = set()
    existing_holdings = (
        db.query(LabPaperHolding).filter(LabPaperHolding.study_id == study_id).all()
        if db else []
    )
    held_symbols = {h.symbol for h in existing_holdings}

    # Collect held symbols and latest bar signal symbols
    critical_symbols = set(held_symbols)
    for ss in study_strategies:
        s_fn = SIGNAL_FUNCTIONS.get(ss.strategy_id)
        s_params = json.loads(ss.parameters_json) if ss.parameters_json else {}
        if not s_fn:
            continue
        for sym, df in bars_dict.items():
            if len(df) < 50:
                continue
            try:
                sig = s_fn(df, s_params)
                if len(sig) > 0 and bool(sig.iloc[-1]):
                    critical_symbols.add(sym)
            except Exception:
                pass

    if not is_test_study and expected_last_session and critical_symbols:
        missing_symbols = []
        for sym in critical_symbols:
            df = bars_dict.get(sym)
            if df is None or df.empty or "date" not in df.columns:
                missing_symbols.append(sym)
                continue
            sym_max = df["date"].max()
            if hasattr(sym_max, "date"):
                sym_max = sym_max.date()
            if sym_max < expected_last_session:
                missing_symbols.append(sym)

        if missing_symbols:
            logger.warning(
                f"[Lab Evaluator] Per-symbol staleness detected for study {study_id}: "
                f"{len(missing_symbols)} critical symbol(s) lack data through {expected_last_session}: {missing_symbols}. "
                f"Attempting targeted re-ingest..."
            )
            try:
                from app.lab.ingest_paper import refresh_indian_paper_bars
                from app.engine.research_loader import load_research_bars_for_paper
                refresh_indian_paper_bars(db=db, symbols=missing_symbols, lookback_sessions=5)
                reloaded, _ = load_research_bars_for_paper(db=db, symbols=missing_symbols, force_refresh=True)
                for s, d in reloaded.items():
                    bars_dict[s] = d
            except Exception as e:
                logger.error(f"[Lab Evaluator] Targeted re-ingest error: {e}")

            for sym in missing_symbols:
                df = bars_dict.get(sym)
                if df is None or df.empty or "date" not in df.columns:
                    stale_symbols.add(sym)
                    continue
                sym_max = df["date"].max()
                if hasattr(sym_max, "date"):
                    sym_max = sym_max.date()
                if sym_max < expected_last_session:
                    stale_symbols.add(sym)

            if stale_symbols:
                logger.warning(
                    f"[Lab Evaluator] PARTIAL_STALE: Symbols still lacking latest session: {stale_symbols}. "
                    f"Exits will not be checked for these symbols."
                )

    # 3. Registry hash for audit
    registry_hash = _compute_registry_hash(study_strategies)

    # 4. Per-strategy evaluation
    all_closed: List[ClosedTrade] = []
    all_open: List[OpenPosition] = []
    tomorrow_orders_by_strategy: Dict[str, List[Dict]] = {}
    daily_equity_by_strategy: Dict[str, List[Dict]] = {}

    for ss in study_strategies:
        strategy_id = ss.strategy_id
        config_hash = ss.config_hash
        holding_days = ss.holding_days
        params = json.loads(ss.parameters_json) if ss.parameters_json else {}

        reason_text_template = build_reason_text(strategy_id, params)

        closed, open_pos, tomorrow, daily = _evaluate_strategy(
            strategy_id=strategy_id,
            config_hash=config_hash,
            holding_days=holding_days,
            params=params,
            bars_dict=bars_dict,
            study_id=study_id,
            study_start=study_start,
            capital=capital,
            risk_pct=risk_pct,
            max_positions=max_positions,
            kill_threshold=kill_threshold,
            data_through_date=data_through_date,
            reason_text_template=reason_text_template,
            db=db,
            stale_symbols=stale_symbols,
        )
        all_closed.extend(closed)
        all_open.extend(open_pos)
        tomorrow_orders_by_strategy[strategy_id] = tomorrow
        daily_equity_by_strategy[strategy_id] = daily

    status = "PARTIAL_STALE" if stale_symbols else "OK"
    return {
        "status": status,
        "study_id": study_id,
        "stale_symbols": sorted(list(stale_symbols)),
        "data_through_date": str(data_through_date) if data_through_date else None,
        "expected_session_date": str(expected_last_session) if expected_last_session else None,
        "registry_hash": registry_hash,
        "engine_version": ENGINE_VERSION,
        "closed_trades": all_closed,
        "open_positions": all_open,
        "tomorrow_orders": tomorrow_orders_by_strategy,
        "daily_equity": daily_equity_by_strategy,
    }


def _evaluate_strategy(
    strategy_id: str,
    config_hash: str,
    holding_days: int,
    params: Dict[str, Any],
    bars_dict: Dict[str, pd.DataFrame],
    study_id: str,
    study_start: datetime.date,
    capital: float,
    risk_pct: float,
    max_positions: int,
    kill_threshold: float,
    data_through_date: Optional[datetime.date],
    reason_text_template: str,
    db,
    stale_symbols: Optional[Set[str]] = None,
) -> Tuple[List[ClosedTrade], List[OpenPosition], List[Dict], List[Dict]]:
    """
    Evaluate one strategy for one study.
    Returns (closed_trades, open_positions, tomorrow_orders, daily_equity_rows).
    """
    from app.lab.models_lab import LabPaperHolding

    signal_fn = SIGNAL_FUNCTIONS.get(strategy_id)
    if not signal_fn:
        logger.warning(f"No signal function for {strategy_id}")
        return [], [], [], []

    atr_mult = float(params.get("stop_atr_mult", 1.5))
    risk_amount = capital * (risk_pct / 100.0)

    # Load existing open holdings from DB (restore state)
    existing_holdings = (
        db.query(LabPaperHolding)
        .filter(
            LabPaperHolding.study_id == study_id,
            LabPaperHolding.strategy_id == strategy_id,
        )
        .all()
    )

    # Reconstruct open positions from DB
    open_positions: Dict[str, OpenPosition] = {}
    for h in existing_holdings:
        # Determine planned_exit_date from days_held tracking
        entry_date = h.entry_date
        hd = holding_days
        planned = _add_trading_days(entry_date, hd, bars_dict)
        tkey = make_trade_key(study_id, strategy_id, config_hash, h.symbol, entry_date)
        signal_date = h.entry_date  # approximation if not stored
        open_positions[h.symbol] = OpenPosition(
            symbol=h.symbol,
            entry_date=entry_date,
            entry_price=h.entry_price,
            stop_price=h.stop_price,
            qty=h.qty,
            planned_exit_date=planned,
            signal_date=signal_date,
            reason_text=reason_text_template,
            signal_context={},
            trade_key=tkey,
            days_held=0,
        )

    # Pre-enrich all bars and compute signals
    enriched_dict: Dict[str, pd.DataFrame] = {}
    signal_dict: Dict[str, pd.Series] = {}

    for sym, df in bars_dict.items():
        if len(df) < 50:
            continue
        df2 = df.copy()
        if "atr14" not in df2.columns:
            df2 = add_all_indicators(df2)
        enriched_dict[sym] = df2.reset_index(drop=True)
        try:
            sig = signal_fn(df2, params)
            signal_dict[sym] = sig.reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Signal error {strategy_id}/{sym}: {e}")

    # Build sorted date list from study start (include pre-history for existing positions)
    all_dates_set = set()
    for df in enriched_dict.values():
        col = df["date"] if "date" in df.columns else pd.Series(df.index)
        all_dates_set.update(col.tolist())
    all_dates = sorted(all_dates_set)

    # Filter to study window + allow pre-start for existing positions
    study_dates = [d for d in all_dates if d >= study_start]

    closed_trades: List[ClosedTrade] = []
    tomorrow_orders: List[Dict] = []
    daily_equity: List[Dict] = []
    cash = capital
    realized_pnl = 0.0
    cumulative_costs = 0.0
    peak_equity = capital
    kill_triggered = False

    for today in study_dates:
        if kill_triggered:
            break

        syms_today = sorted([
            sym for sym, df in enriched_dict.items()
            if _has_date(df, today)
        ])

        # ── 1. Process exits for open positions ───────────────────────────────
        to_close: List[Tuple[str, float, Any, str]] = []
        for sym, pos in list(open_positions.items()):
            if stale_symbols and sym in stale_symbols:
                # Per-symbol staleness: do not mark exits as checked on missing session
                pos.is_stale_data = True
                continue
            if sym not in enriched_dict:
                continue
            df = enriched_dict[sym]
            i = _find_date_idx(df, today)
            if i is None:
                continue

            pos.days_held += 1
            bar = df.iloc[i]

            stop = pos.stop_price
            # Stop-hit check (use previous close as reference for gap)
            if stop is not None:
                # Check if gap-through: open < stop
                open_price = float(bar["open"])
                if open_price < stop:
                    # Gap through stop — fill at actual open with sell slippage
                    fill = open_price * (1 - SLIPPAGE_PCT)
                    to_close.append((sym, fill, today, "GAP_THROUGH_STOP"))
                    continue
                # Normal stop: low touches/breaches stop
                if float(bar["low"]) <= stop:
                    fill = max(stop, float(bar["low"])) * (1 - SLIPPAGE_PCT)
                    to_close.append((sym, fill, today, "STOP_HIT"))
                    continue

            # Time exit
            if today >= pos.planned_exit_date:
                fill = float(bar["open"]) * (1 - SLIPPAGE_PCT)
                to_close.append((sym, fill, today, "TIME_EXIT"))

        for sym, exit_price, exit_date, reason in to_close:
            pos = open_positions.pop(sym)
            qty = pos.qty
            entry_price = pos.entry_price
            stop = pos.stop_price
            gross = (exit_price - entry_price) * qty
            costs = _round_trip_cost(entry_price, exit_price, qty)
            net = gross - costs
            risk_per_share = abs(entry_price - stop) if stop else entry_price * 0.02
            r_mult = net / (risk_per_share * qty) if risk_per_share * qty > 0 else 0.0

            cash += entry_price * qty + net  # simplified: cash += proceeds
            realized_pnl += net
            cumulative_costs += costs

            closed_trades.append(ClosedTrade(
                symbol=sym,
                strategy_id=strategy_id,
                config_hash=config_hash,
                signal_date=pos.signal_date,
                entry_date=pos.entry_date,
                entry_price=entry_price,
                exit_date=exit_date,
                exit_price=round(exit_price, 4),
                stop_price=stop,
                qty=qty,
                gross_pnl=round(gross, 2),
                costs=round(costs, 2),
                net_pnl=round(net, 2),
                r_multiple=round(r_mult, 4),
                exit_reason=reason,
                planned_exit_date=pos.planned_exit_date,
                reason_text=pos.reason_text,
                signal_context=pos.signal_context,
                trade_key=pos.trade_key,
                holding_days_target=holding_days,
            ))

        # ── 2. Check for new entry signals ────────────────────────────────────
        is_latest_bar = (today == study_dates[-1]) if study_dates else False

        for sym in syms_today:
            if sym in open_positions or (stale_symbols and sym in stale_symbols):
                continue
            if len(open_positions) >= max_positions:
                break
            if sym not in signal_dict or sym not in enriched_dict:
                continue

            df = enriched_dict[sym]
            sig = signal_dict[sym]
            i = _find_date_idx(df, today)
            if i is None or not bool(sig.iloc[i]):
                continue

            # Need next bar to fill — check if next bar exists
            if i + 1 >= len(df):
                # This is the latest available bar — signal becomes TomorrowOrder
                if is_latest_bar or today == study_dates[-1]:
                    curr_bar = df.iloc[i]
                    atr = float(curr_bar.get("atr14", curr_bar["close"] * 0.02)) or curr_bar["close"] * 0.02
                    if pd.isna(atr) or atr <= 0:
                        atr = curr_bar["close"] * 0.02
                    est_entry = float(curr_bar["close"]) * (1 + SLIPPAGE_PCT)
                    stop_price = est_entry - atr_mult * atr if strategy_id != "S04" else None
                    risk_ps = est_entry - stop_price if stop_price else est_entry * 0.02
                    research_qty = max(1, int(risk_amount / risk_ps)) if risk_ps > 0 else 1
                    practical_qty = max(1, int(17500 * (risk_pct / 100.0) / risk_ps)) if risk_ps > 0 else 1

                    # Build signal context
                    ctx = _build_signal_context(strategy_id, params, curr_bar)
                    reason = build_reason_text(strategy_id, params)

                    planned_exit = _add_trading_days(today, holding_days + 1, bars_dict)
                    okey = make_order_key(study_id, strategy_id, config_hash, sym, today)
                    tomorrow_orders.append({
                        "order_key": okey,
                        "study_id": study_id,
                        "strategy_id": strategy_id,
                        "config_hash": config_hash,
                        "symbol": sym,
                        "signal_date": today,
                        "signal_reason": reason,
                        "signal_context_json": json.dumps(ctx),
                        "planned_entry": round(est_entry, 2),
                        "stop_price": round(stop_price, 2) if stop_price else None,
                        "research_qty": research_qty,
                        "practical_qty": practical_qty,
                        "planned_exit_date": planned_exit,
                        "holding_days_target": holding_days,
                        "data_through_date": data_through_date,
                        "status": "PENDING",
                    })
                continue

            # Next bar available — fill at next open
            next_bar = df.iloc[i + 1]
            next_date = next_bar["date"] if "date" in next_bar else next_bar.name

            # Only fill if next_date is within study window
            if next_date < study_start:
                continue

            entry_price = float(next_bar["open"]) * (1 + SLIPPAGE_PCT)

            curr_bar = df.iloc[i]
            atr = float(curr_bar.get("atr14", curr_bar["close"] * 0.02)) or curr_bar["close"] * 0.02
            if pd.isna(atr) or atr <= 0:
                atr = curr_bar["close"] * 0.02
            stop_price = entry_price - atr_mult * atr if strategy_id != "S04" else None

            risk_ps = entry_price - stop_price if stop_price else entry_price * 0.02
            if risk_ps <= 0:
                continue

            qty = max(1, int(risk_amount / risk_ps))
            # Cap at 20% capital
            if qty * entry_price > capital * 0.20:
                qty = max(1, int(capital * 0.20 / entry_price))

            # Cost gate
            est_costs = _round_trip_cost(entry_price, entry_price, qty)
            if est_costs / (risk_ps * qty) > 0.25:
                continue

            cash -= entry_price * qty
            planned_exit = _add_trading_days(next_date, holding_days, bars_dict)
            tkey = make_trade_key(study_id, strategy_id, config_hash, sym, next_date)
            ctx = _build_signal_context(strategy_id, params, curr_bar)
            reason = build_reason_text(strategy_id, params)

            open_positions[sym] = OpenPosition(
                symbol=sym,
                entry_date=next_date,
                entry_price=entry_price,
                stop_price=stop_price,
                qty=qty,
                planned_exit_date=planned_exit,
                signal_date=today,
                reason_text=reason,
                signal_context=ctx,
                trade_key=tkey,
                days_held=0,
            )

        # ── 3. Daily equity snapshot ───────────────────────────────────────────
        invested = 0.0
        unrealized = 0.0
        for sym, pos in open_positions.items():
            if sym in enriched_dict:
                df = enriched_dict[sym]
                i = _find_date_idx(df, today)
                if i is not None:
                    last_close = float(df.iloc[i]["close"])
                    pos_val = last_close * pos.qty
                    invested += pos.entry_price * pos.qty
                    unrealized += (last_close - pos.entry_price) * pos.qty - \
                                  _round_trip_cost(pos.entry_price, last_close, pos.qty)

        total_equity = cash + sum(pos.entry_price * pos.qty for pos in open_positions.values()) + unrealized
        if total_equity > peak_equity:
            peak_equity = total_equity
        drawdown = (peak_equity - total_equity) / peak_equity * 100 if peak_equity > 0 else 0.0
        cum_ret = (total_equity / capital - 1) * 100

        # Kill switch check
        if drawdown >= kill_threshold * 100:
            kill_triggered = True
            logger.warning(f"[Lab] Kill switch triggered for study {study_id} strategy {strategy_id}: drawdown {drawdown:.1f}%")

        daily_equity.append({
            "strategy_id": strategy_id,
            "session_date": today,
            "cash": round(cash, 2),
            "invested_value": round(invested, 2),
            "total_equity": round(total_equity, 2),
            "peak_equity": round(peak_equity, 2),
            "drawdown_pct": round(drawdown, 4),
            "cumulative_return_pct": round(cum_ret, 4),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "open_positions": len(open_positions),
            "trades_today": len(to_close),
            "cumulative_costs": round(cumulative_costs, 2),
        })

    # Return open positions (not liquidated)
    return closed_trades, list(open_positions.values()), tomorrow_orders, daily_equity


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _has_date(df: pd.DataFrame, d: datetime.date) -> bool:
    col = df["date"] if "date" in df.columns else pd.Series(df.index)
    return bool((col == d).any())


def _find_date_idx(df: pd.DataFrame, d: datetime.date) -> Optional[int]:
    col = df["date"] if "date" in df.columns else pd.Series(df.index)
    matches = col[col == d].index
    return int(matches[0]) if len(matches) > 0 else None


def _add_trading_days(start: datetime.date, n: int, bars_dict: Dict[str, pd.DataFrame]) -> datetime.date:
    """Return approximate trading day n sessions after start."""
    # Use actual dates from bars if available
    all_dates = sorted(set(
        d for df in bars_dict.values()
        for d in (df["date"].tolist() if "date" in df.columns else df.index.tolist())
        if d > start
    ))
    if len(all_dates) >= n:
        return all_dates[n - 1]
    # Fallback: add calendar days
    result = start
    added = 0
    while added < n:
        result += datetime.timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


def _build_signal_context(strategy_id: str, params: Dict, bar: pd.Series) -> Dict[str, Any]:
    """Capture key indicator values at signal time for card display."""
    ctx: Dict[str, Any] = {
        "close": float(bar.get("close", 0)),
        "volume": float(bar.get("volume", 0)),
    }
    for field in ["rsi14", "atr14", "ema20", "ema50", "sma50", "sma200", "avg_vol20"]:
        v = bar.get(field)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            ctx[field] = round(float(v), 4)
    return ctx


def _compute_registry_hash(study_strategies) -> str:
    """Hash of the study's frozen strategy configurations."""
    items = sorted(
        (ss.strategy_id, ss.config_hash, ss.holding_days)
        for ss in study_strategies
    )
    raw = json.dumps(items)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
