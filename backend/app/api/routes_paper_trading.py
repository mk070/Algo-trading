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
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException

from app.engine.ai_research_assistant import ai_research_assistant

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

