"""
FastAPI Routes for Cycle 4 Paper-Trading Platform
Strictly Offline / Paper Simulation — No Live Broker Order Placement

Endpoints:
- GET /api/paper-trading/overview: Multi-strategy overview (Candidates 1–4, Benchmark, ₹20,000 capital, data freshness)
- GET /api/paper-trading/strategy/{strategy_id}: Detailed holdings, orders journal, trade ledger, fee breakdown
- GET /api/paper-trading/replay: Historical replay comparison (Normal vs 2x stress scenario)
- GET /api/paper-trading/ai-notes: Strictly informational AI research notes and bull/bear theses

NOTE: The replay/run POST endpoint is intentionally removed.
Phase 4 strategy-validation freeze is in effect. No new replay execution is permitted.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException

from app.engine.ai_research_assistant import ai_research_assistant
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Actual state directories verified on disk.
# research/cycle4/broker_state/ does NOT exist. Do not read from it.
REPLAY_STATE_DIR = Path("research/cycle4/replay_state")
CYCLE4_STATE_DIR = Path("research/cycle4/state")

# Map UI strategy IDs → actual file prefixes in broker_normal_run / broker_stress_run sub-dirs.
_STRATEGY_FILE_PREFIX = {
    "cand1_reg_alpha_buf30": "normal_cand1_reg_alpha_buf30",
    "cand2_c1b_buf30": "normal_cand2_c1b_buf30",
    "cand3_dual_momentum_buf30": "normal_cand3_dual_momentum_buf30",
}
_STRATEGY_FILE_PREFIX_STRESS = {
    "cand1_reg_alpha_buf30": "stress_cand1_reg_alpha_buf30",
    "cand2_c1b_buf30": "stress_cand2_c1b_buf30",
    "cand3_dual_momentum_buf30": "stress_cand3_dual_momentum_buf30",
}


def _load_replay_broker_state(strategy_id: str, stress: bool = False) -> Optional[Dict[str, Any]]:
    """
    Load broker account state from replay_state/broker_{normal,stress}_run/.
    Returns None if the file is absent; callers must handle None explicitly.
    """
    prefix_map = _STRATEGY_FILE_PREFIX_STRESS if stress else _STRATEGY_FILE_PREFIX
    file_prefix = prefix_map.get(strategy_id)
    if not file_prefix:
        return None
    sub_dir = "broker_stress_run" if stress else "broker_normal_run"
    state_file = REPLAY_STATE_DIR / sub_dir / f"{file_prefix}_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", state_file, exc)
    return None


def _load_replay_csv(strategy_id: str, kind: str, stress: bool = False) -> List[Dict[str, Any]]:
    """Load orders/trades/daily CSV for a strategy from the broker replay run dirs.
    kind must be one of: 'orders', 'trades', 'daily'.
    Returns an empty list if the file is absent.
    """
    prefix_map = _STRATEGY_FILE_PREFIX_STRESS if stress else _STRATEGY_FILE_PREFIX
    file_prefix = prefix_map.get(strategy_id)
    if not file_prefix:
        return []
    sub_dir = "broker_stress_run" if stress else "broker_normal_run"
    csv_file = REPLAY_STATE_DIR / sub_dir / f"{file_prefix}_{kind}.csv"
    if csv_file.exists():
        try:
            import pandas as pd
            return pd.read_csv(csv_file).fillna("").to_dict(orient="records")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", csv_file, exc)
    return []


@router.get("/paper-trading/overview")
def get_paper_trading_overview():
    """
    Returns high-level status of the 4 research strategies and passive benchmark.
    Capital: INR 20,000.00 each (Simulated Research Allocation).
    Source: replay_state/replay_normal_results.json (pre-computed historical replay).
    Returns real data or null metrics — never invented placeholder values.
    """
    replay_file = REPLAY_STATE_DIR / "replay_normal_results.json"
    replay_data = None
    replay_loaded = False
    if replay_file.exists():
        try:
            with open(replay_file, "r", encoding="utf-8") as f:
                replay_data = json.load(f)
            replay_loaded = True
        except Exception as exc:
            logger.warning("Failed to parse replay_normal_results.json: %s", exc)

    # Determine data freshness from replay metadata (not from parquet to avoid startup cost)
    replay_period = None
    if replay_data:
        replay_period = {
            "start_date": replay_data.get("evaluation_start_date"),
            "end_date": replay_data.get("evaluation_end_date"),
            "sessions_count": replay_data.get("sessions_count"),
            "scenario": replay_data.get("scenario"),
        }

    def _build_strategy_summary(replay_key: str, strat_id: str, strat_name: str, status: str,
                                 buffer_band: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Build a strategy summary from replay data or null-safe defaults.
        Returns null metrics (None) rather than invented zeros when no replay data is available.
        """
        summary: Dict[str, Any] = {
            "id": strat_id,
            "name": strat_name,
            "status": status,
            "buffer_band": buffer_band,
            "simulated_capital": 20000.0,
            # All metrics default to None — rendered as "No data" in the UI.
            "final_equity": None,
            "cagr_pct": None,
            "max_drawdown_pct": None,
            "sharpe_ratio": None,
            "trades_count": None,
            "holdings_count": None,
            "data_source": "NONE",
        }
        if reason:
            summary["reason"] = reason
        if status == "UNAVAILABLE":
            return summary

        if replay_data and replay_key in replay_data:
            cand = replay_data[replay_key]
            metrics = cand.get("metrics", {})
            summary["final_equity"] = cand.get("final_equity")
            summary["cagr_pct"] = metrics.get("cagr_pct")
            summary["max_drawdown_pct"] = metrics.get("max_drawdown_pct")
            summary["sharpe_ratio"] = metrics.get("sharpe_ratio")
            summary["trades_count"] = metrics.get("total_trades")
            summary["holdings_count"] = cand.get("latest_holdings_count")
            summary["data_source"] = "HISTORICAL_REPLAY"
        return summary

    cand1_summary = _build_strategy_summary(
        "candidate1", "cand1_reg_alpha_buf30",
        "Candidate 1: Market-Sector Regression-Alpha", "ACTIVE",
        "Top 20 Enter, Retain <= 30",
    )
    cand2_summary = _build_strategy_summary(
        "candidate2", "cand2_c1b_buf30",
        "Candidate 2: C1b Baseline Momentum (Control)", "ACTIVE",
        "Top 20 Enter, Retain <= 30",
    )
    cand3_summary = _build_strategy_summary(
        "candidate3", "cand3_dual_momentum_buf30",
        "Candidate 3: Relative-Plus-Absolute Strength", "ACTIVE",
        "Absolute (Ret>0 & >SMA200) + Relative Top 20",
    )
    cand4_summary = _build_strategy_summary(
        "candidate4", "cand4_value_radar",
        "Candidate 4: Value-Based Strategy", "UNAVAILABLE", "",
        reason="No trustworthy point-in-time fundamental data (balance sheets/quarterly P&L) available in frozen repository.",
    )

    benchmark_summary: Dict[str, Any] = {
        "id": "benchmark_niftybees",
        "name": "NIFTYBEES.NS Total Return ETF",
        "status": "PASSIVE_BENCHMARK",
        "cagr_pct": None,
        "net_return_pct": None,
        "max_drawdown_pct": None,
        "data_source": "NONE",
    }
    if replay_data and "benchmark" in replay_data:
        bench = replay_data["benchmark"]
        benchmark_summary["cagr_pct"] = bench.get("cagr_pct")
        benchmark_summary["net_return_pct"] = bench.get("net_return_pct")
        benchmark_summary["max_drawdown_pct"] = bench.get("max_drawdown_pct")
        benchmark_summary["data_source"] = "HISTORICAL_REPLAY"

    return {
        "disclaimer": "Simulated Research Capital (INR 20,000.00 each) — Not Deployable Broker Funds.",
        "phase_status": "PHASE_4_VALIDATION_FREEZE — Prospective paper trading PAUSED. Display is historical replay only.",
        "replay_loaded": replay_loaded,
        "replay_period": replay_period,
        "strategies": [
            cand1_summary,
            cand2_summary,
            cand3_summary,
            cand4_summary,
        ],
        "benchmark": benchmark_summary,
    }


@router.get("/paper-trading/strategy/{strategy_id}")
def get_strategy_detail(strategy_id: str):
    """
    Returns detailed account state, holdings, orders journal, and trades journal.
    Source: research/cycle4/replay_state/broker_normal_run/ (historical replay broker files).
    Returns null account when files are absent — does not invent placeholder values.
    """
    allowed_ids = set(_STRATEGY_FILE_PREFIX.keys())
    if strategy_id not in allowed_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown strategy_id '{strategy_id}'. Valid ids: {sorted(allowed_ids)}",
        )

    acc_state = _load_replay_broker_state(strategy_id, stress=False)
    orders = _load_replay_csv(strategy_id, "orders", stress=False)
    trades = _load_replay_csv(strategy_id, "trades", stress=False)
    daily = _load_replay_csv(strategy_id, "daily", stress=False)

    # Normalize account field names for the UI.
    # Actual broker state uses 'account_id', 'strategy_name', 'orders_count', etc.
    # Map to what the frontend expects.
    if acc_state:
        # 'cumulative_costs' may be under 'cumulative_costs_paid' in broker state
        if "cumulative_costs_paid" in acc_state and "cumulative_costs" not in acc_state:
            acc_state["cumulative_costs"] = acc_state["cumulative_costs_paid"]
        if "cumulative_slippage" not in acc_state:
            acc_state["cumulative_slippage"] = 0.0
        # Flatten holding positions: strip position_id from each holding
        holdings = acc_state.get("holdings", {})
        for sym, pos in holdings.items():
            if isinstance(pos, dict):
                pos.pop("position_id", None)
                pos.pop("entry_date", None)

    return {
        "strategy_id": strategy_id,
        "data_source": "HISTORICAL_REPLAY" if acc_state else "NONE",
        "phase_status": "PHASE_4_VALIDATION_FREEZE — Prospective paper tracking PAUSED. Data shown is from historical replay only.",
        "account": acc_state,  # None when no saved state exists — UI must show no-data state
        "orders_count": len(orders),
        "trades_count": len(trades),
        "orders_journal": orders[-100:],
        "trades_journal": trades[-100:],
        "daily_snapshots": daily[-250:],
    }


@router.get("/paper-trading/replay")
def get_replay_results(stress: bool = False):
    """Returns cached historical replay comparison results (normal or 2x stress).
    Returns the saved file contents only. Does NOT trigger a new replay run.
    Phase 4 validation freeze: on-demand re-execution is disabled.
    """
    prefix = "stress_" if stress else "normal_"
    replay_file = REPLAY_STATE_DIR / f"replay_{prefix}results.json"

    if replay_file.exists():
        try:
            with open(replay_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read replay file %s: %s", replay_file, e)
            raise HTTPException(
                status_code=500,
                detail=f"Replay file exists but could not be parsed: {e}",
            )

    # File is absent — return a structured no-data response rather than triggering execution.
    return {
        "status": "NO_DATA",
        "message": (
            f"No {'stress' if stress else 'normal'} replay results file found at "
            f"{replay_file}. Phase 4 validation freeze is in effect; "
            "re-execution is disabled. Contact maintainer to restore the file."
        ),
        "file_path": str(replay_file),
    }


@router.get("/paper-trading/ai-notes")
def get_ai_research_notes(symbol: Optional[str] = None):
    """
    Returns AI research assistant notes: Bull vs Bear arguments, filings summary, and post-trade reviews.
    Informational layer only.
    """
    target_sym = symbol or "RELIANCE.NS"
    notes = ai_research_assistant.analyze_candidate_thesis(
        symbol=target_sym,
        sector="Energy & Conglomerate",
        current_price=2750.45,
        momentum_score=2.85,
        regime_status="BULL_REGIME",
    )
    return notes


# ---------------------------------------------------------------------------
# Prospective Paper-Trading Endpoints (Cycle 4)
# Strictly Read-Only — Returns Saved Real Records Only — No Execution on GET
# ---------------------------------------------------------------------------

_PROSPECTIVE_STRATEGY_MAP = {
    "candidate": "candidate_reg_alpha_buf30",
    "candidate_reg_alpha_buf30": "candidate_reg_alpha_buf30",
    "cand1_reg_alpha_buf30": "candidate_reg_alpha_buf30",
    "control": "control_c1b_buf30",
    "control_c1b_buf30": "control_c1b_buf30",
    "cand2_c1b_buf30": "control_c1b_buf30",
}


def _load_prospective_state_db(name: str) -> Optional[Dict[str, Any]]:
    """Loads prospective portfolio state from Neon PostgreSQL."""
    try:
        from app.db import transaction_context
        from app.models import PaperAccount, PaperHolding, PaperTrade, PaperDailyHistory
        with transaction_context() as session:
            acc = session.query(PaperAccount).filter(PaperAccount.strategy_id == name).first()
            if not acc:
                return None
            holdings = session.query(PaperHolding).filter(PaperHolding.strategy_id == name, PaperHolding.run_type == "FORWARD").all()
            holdings_dict = {
                h.symbol: {
                    "shares": h.shares,
                    "avg_cost": round(h.avg_cost, 2),
                    "invested_cost": round(h.invested_cost, 2),
                }
                for h in holdings
            }
            trades_count = session.query(PaperTrade).filter(PaperTrade.strategy_id == name, PaperTrade.run_type == "FORWARD").count()
            sessions_count = session.query(PaperDailyHistory).filter(PaperDailyHistory.strategy_id == name, PaperDailyHistory.run_type == "FORWARD").count()
            return {
                "name": acc.strategy_id,
                "initial_capital": round(acc.initial_capital, 2),
                "cash": round(acc.cash, 2),
                "holdings": holdings_dict,
                "realized_pnl": round(acc.realized_pnl, 2),
                "unrealized_pnl": round(acc.unrealized_pnl, 2),
                "total_equity": round(acc.total_equity, 2),
                "peak_equity": round(acc.peak_equity, 2),
                "cumulative_costs_paid": round(acc.cumulative_costs_paid, 2),
                "cost_pct_of_capital": round((acc.cumulative_costs_paid / acc.initial_capital) * 100.0, 2) if acc.initial_capital > 0 else 0.0,
                "last_processed_date": str(acc.last_processed_date) if acc.last_processed_date else None,
                "trades_count": trades_count,
                "sessions_count": sessions_count,
            }
    except Exception as exc:
        logger.warning("Failed to load prospective state from DB for %s: %s", name, exc)
        return None


def _load_prospective_state(name: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Loads prospective state from Neon PostgreSQL first, falling back to local files.
    Returns (state_dict, source).
    """
    # If state dir was redirected (e.g. in test fixture to tmp_path), do not query DB
    if CYCLE4_STATE_DIR != Path("research/cycle4/state"):
        path = CYCLE4_STATE_DIR / f"{name}_state.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f), "PROSPECTIVE_STATE_FILES"
            except Exception as exc:
                logger.warning("Failed to load prospective state %s: %s", path, exc)
        return None, "NONE"

    # 1. Query PostgreSQL
    db_state = _load_prospective_state_db(name)
    if db_state is not None:
        return db_state, "NEON_POSTGRESQL"

    # 2. Fallback to local filesystem state files
    path = CYCLE4_STATE_DIR / f"{name}_state.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f), "PROSPECTIVE_STATE_FILES"
        except Exception as exc:
            logger.warning("Failed to load prospective state %s: %s", path, exc)
    return None, "NONE"


def _load_prospective_csv(name: str, kind: str) -> List[Dict[str, Any]]:
    path = CYCLE4_STATE_DIR / f"{name}_{kind}.csv"
    if path.exists():
        try:
            import pandas as pd
            return pd.read_csv(path).fillna("").to_dict(orient="records")
        except Exception as exc:
            logger.warning("Failed to load prospective csv %s: %s", path, exc)
    return []


def _load_prospective_daily(name: str) -> List[Dict[str, Any]]:
    """Loads prospective daily history from PostgreSQL first, falling back to daily_ledger CSV."""
    if CYCLE4_STATE_DIR == Path("research/cycle4/state"):
        try:
            from app.db import transaction_context
            from app.models import PaperDailyHistory
            with transaction_context() as session:
                rows = (
                    session.query(PaperDailyHistory)
                    .filter(PaperDailyHistory.strategy_id == name, PaperDailyHistory.run_type == "FORWARD")
                    .order_by(PaperDailyHistory.session_date.asc())
                    .all()
                )
                if rows:
                    return [
                        {
                            "date": str(r.session_date),
                            "portfolio": r.strategy_id,
                            "cash": r.cash,
                            "invested_value": r.invested_value,
                            "total_equity": r.total_equity,
                            "peak_equity": r.peak_equity,
                            "drawdown_pct": r.drawdown_pct,
                            "cumulative_return_pct": r.cumulative_return_pct,
                            "cumulative_costs": r.cumulative_costs,
                            "cost_pct_of_capital": r.cost_pct_of_capital,
                            "realized_pnl": r.realized_pnl,
                            "unrealized_pnl": r.unrealized_pnl,
                            "holdings_count": r.holdings_count,
                            "benchmark_close": r.benchmark_close,
                            "benchmark_daily_return": r.benchmark_daily_return,
                            "regime_status": r.regime_status,
                            "valuation_status": r.valuation_status,
                            "is_complete_valuation": r.is_complete_valuation,
                            "missing_price_symbols": r.missing_price_symbols or "[]",
                            "stale_price_carry_forwards": r.stale_price_carry_forwards or "{}",
                        }
                        for r in rows
                    ]
        except Exception as exc:
            logger.warning("Failed to load prospective daily history from DB for %s: %s", name, exc)

    return _load_prospective_csv(name, "daily_ledger")


def _load_prospective_trades(name: str) -> List[Dict[str, Any]]:
    """Loads prospective trade history from PostgreSQL first, falling back to trade_ledger CSV."""
    if CYCLE4_STATE_DIR == Path("research/cycle4/state"):
        try:
            from app.db import transaction_context
            from app.models import PaperTrade
            with transaction_context() as session:
                rows = (
                    session.query(PaperTrade)
                    .filter(PaperTrade.strategy_id == name, PaperTrade.run_type == "FORWARD")
                    .order_by(PaperTrade.exec_date.asc(), PaperTrade.id.asc())
                    .all()
                )
                if rows:
                    return [
                        {
                            "exec_date": str(r.exec_date),
                            "portfolio": r.strategy_id,
                            "symbol": r.symbol,
                            "side": r.side,
                            "action": r.action,
                            "shares": r.shares,
                            "ref_open": r.ref_open,
                            "fill_price": r.fill_price,
                            "gross_turnover": r.gross_turnover,
                            "costs": json.loads(r.costs_json) if r.costs_json else {},
                            "net_cash_delta": r.net_cash_delta,
                            "realized_pnl": r.realized_pnl,
                            "regime_pass": r.regime_pass,
                        }
                        for r in rows
                    ]
        except Exception as exc:
            logger.warning("Failed to load prospective trade history from DB for %s: %s", name, exc)

    return _load_prospective_csv(name, "trade_ledger")


def _load_prospective_orders_audit() -> List[Dict[str, Any]]:
    """Loads rebalance orders audit from PostgreSQL first, falling back to JSONL file."""
    if CYCLE4_STATE_DIR == Path("research/cycle4/state"):
        try:
            from app.db import transaction_context
            from app.models import PaperRebalanceAudit
            with transaction_context() as session:
                rows = (
                    session.query(PaperRebalanceAudit)
                    .order_by(PaperRebalanceAudit.signal_date.asc())
                    .all()
                )
                if rows:
                    return [
                        {
                            "signal_date": str(r.signal_date),
                            "is_bull_regime": r.is_bull_regime,
                            "nsei_close": r.nsei_close,
                            "nsei_sma200": r.nsei_sma200,
                            "candidate_targets": json.loads(r.candidate_targets_json) if r.candidate_targets_json else [],
                            "control_targets": json.loads(r.control_targets_json) if r.control_targets_json else [],
                            "candidate_top5_ranked": json.loads(r.candidate_top5_json) if r.candidate_top5_json else [],
                            "control_top5_ranked": json.loads(r.control_top5_json) if r.control_top5_json else [],
                        }
                        for r in rows
                    ]
        except Exception as exc:
            logger.warning("Failed to load prospective rebalance audit from DB: %s", exc)

    path = CYCLE4_STATE_DIR / "rebalance_orders_audit.jsonl"
    if path.exists():
        try:
            lines = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(json.loads(line))
            return lines
        except Exception as exc:
            logger.warning("Failed to load rebalance orders audit %s: %s", path, exc)
    return []


@router.get("/paper-trading/prospective/overview")
def get_prospective_paper_overview():
    """
    Returns the real saved state for prospective paper trading (Cycle 4).
    Separated strictly from historical replay.
    Does not trigger any execution.
    """
    cand_state, cand_src = _load_prospective_state("candidate_reg_alpha_buf30")
    ctrl_state, ctrl_src = _load_prospective_state("control_c1b_buf30")
    cand_daily = _load_prospective_daily("candidate_reg_alpha_buf30")
    ctrl_daily = _load_prospective_daily("control_c1b_buf30")

    has_data = cand_state is not None or ctrl_state is not None
    data_src = cand_src if cand_state else (ctrl_src if ctrl_state else "NONE")

    if not settings.forward_paper_trading_enabled:
        study_status = "AWAITING_OWNER_APPROVAL"
    elif has_data:
        study_status = "RUNNING"
    else:
        study_status = "NOT_STARTED"

    last_date = None
    if cand_state and cand_state.get("last_processed_date"):
        last_date = cand_state.get("last_processed_date")
    elif ctrl_state and ctrl_state.get("last_processed_date"):
        last_date = ctrl_state.get("last_processed_date")

    is_complete_val = None
    missing_symbols = []
    if cand_daily:
        latest_daily = cand_daily[-1]
        is_complete_val = bool(latest_daily.get("is_complete_valuation", True))
        try:
            missing_raw = latest_daily.get("missing_price_symbols", "[]")
            missing_symbols = json.loads(missing_raw) if isinstance(missing_raw, str) else missing_raw
        except Exception:
            missing_symbols = []

    benchmark_comp = None
    if cand_daily:
        first_b = cand_daily[0].get("benchmark_close")
        last_b = cand_daily[-1].get("benchmark_close")
        if first_b and last_b and float(first_b) > 0:
            b_return_pct = round(((float(last_b) / float(first_b)) - 1.0) * 100.0, 2)
            benchmark_comp = {
                "symbol": "NIFTYBEES.NS",
                "start_close": float(first_b),
                "latest_close": float(last_b),
                "cumulative_return_pct": b_return_pct,
                "sessions_count": len(cand_daily),
            }

    return {
        "disclaimer": "Simulated Research Capital (INR 17,500.00 each) — Forward Paper Observation Only. No real funds.",
        "study_status": study_status,
        "forward_paper_trading_enabled": settings.forward_paper_trading_enabled,
        "data_source": data_src,
        "data_freshness": {
            "last_processed_date": last_date,
            "status": "AWAITING_OWNER_APPROVAL" if not settings.forward_paper_trading_enabled else ("DATA_SYNCHRONIZED" if has_data else "NO_DATA"),
            "valuation_completeness": is_complete_val,
            "missing_price_symbols": missing_symbols,
        },
        "candidate": cand_state,
        "control": ctrl_state,
        "benchmark": benchmark_comp,
    }


@router.get("/paper-trading/prospective/strategy/{strategy_id}")
def get_prospective_strategy_detail(strategy_id: str):
    """
    Returns detailed account state, holdings, daily equity history, trades, and orders
    for a prospective strategy (candidate or control).
    """
    canonical = _PROSPECTIVE_STRATEGY_MAP.get(strategy_id)
    if not canonical:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown prospective strategy_id '{strategy_id}'. Valid IDs: ['candidate', 'control', 'candidate_reg_alpha_buf30', 'control_c1b_buf30']",
        )

    acc_state, acc_src = _load_prospective_state(canonical)
    daily = _load_prospective_daily(canonical)
    trades = _load_prospective_trades(canonical)
    orders_audit = _load_prospective_orders_audit()

    if not settings.forward_paper_trading_enabled:
        study_status = "AWAITING_OWNER_APPROVAL"
    elif acc_state:
        study_status = "RUNNING"
    else:
        study_status = "NOT_STARTED"

    is_complete_val = None
    if daily:
        latest_daily = daily[-1]
        is_complete_val = bool(latest_daily.get("is_complete_valuation", True))

    holdings = acc_state.get("holdings", {}) if acc_state else {}

    return {
        "strategy_id": canonical,
        "study_status": study_status,
        "forward_paper_trading_enabled": settings.forward_paper_trading_enabled,
        "data_source": acc_src,
        "account": acc_state,
        "holdings": holdings,
        "orders_count": len(orders_audit),
        "trades_count": len(trades),
        "daily_history": daily[-250:],
        "trades_journal": trades[-100:],
        "orders_journal": orders_audit[-100:],
        "last_processed_date": acc_state.get("last_processed_date") if acc_state else None,
        "valuation_completeness": is_complete_val,
        "disclaimer": "Simulated Research Capital (INR 17,500.00) — Prospective Paper Observation Only.",
    }

