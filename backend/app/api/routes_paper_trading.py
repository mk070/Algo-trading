"""
FastAPI Routes for Cycle 4 Paper-Trading Platform
Strictly Offline / Paper Simulation — No Live Broker Order Placement

Endpoints:
- GET /api/paper-trading/overview: Multi-strategy overview (Candidates 1–4, Benchmark, ₹20,000 capital, data freshness)
- GET /api/paper-trading/strategy/{strategy_id}: Detailed holdings, orders journal, trade ledger, fee breakdown
- GET /api/paper-trading/replay: Historical replay comparison (Normal vs 2x stress scenario)
- POST /api/paper-trading/replay/run: Triggers replay run
- GET /api/paper-trading/ai-notes: Strictly informational AI research notes and bull/bear theses
"""

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.engine.ai_research_assistant import ai_research_assistant
from app.engine.replay_runner import HistoricalReplayRunner
from app.engine.paper_broker import DeterministicPaperBroker

logger = logging.getLogger(__name__)
router = APIRouter()

BROKER_STATE_DIR = Path("research/cycle4/broker_state")
REPLAY_STATE_DIR = Path("research/cycle4/replay_state")


def _load_account_state(account_id: str) -> Optional[Dict[str, Any]]:
    state_file = BROKER_STATE_DIR / f"{account_id}_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


@router.get("/paper-trading/overview")
def get_paper_trading_overview():
    """
    Returns high-level status of the 4 research strategies and passive benchmark.
    Capital: INR 20,000.00 each (Simulated Research Allocation).
    """
    # Load replay or live paper state if available
    replay_file = REPLAY_STATE_DIR / "replay_normal_results.json"
    replay_data = None
    if replay_file.exists():
        try:
            with open(replay_file, "r", encoding="utf-8") as f:
                replay_data = json.load(f)
        except Exception:
            pass

    # Read latest snapshot date for data freshness
    snapshot_date = "2026-11-05"
    snap_path = Path("data/research/research_snapshot_20261106.parquet")
    if snap_path.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(snap_path, columns=["date"])
            snapshot_date = str(pd.to_datetime(df["date"]).max().date())
        except Exception:
            pass

    cand1_summary = {
        "id": "cand1_reg_alpha_buf30",
        "name": "Candidate 1: Market-Sector Regression-Alpha",
        "status": "ACTIVE",
        "buffer_band": "Top 20 Enter, Retain <= 30",
        "simulated_capital": 20000.0,
        "cash_balance": 20000.0,
        "total_equity": 20000.0,
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "trades_count": 0,
        "holdings_count": 0,
    }

    cand2_summary = {
        "id": "cand2_c1b_buf30",
        "name": "Candidate 2: C1b Baseline Momentum",
        "status": "ACTIVE",
        "buffer_band": "Top 20 Enter, Retain <= 30",
        "simulated_capital": 20000.0,
        "cash_balance": 20000.0,
        "total_equity": 20000.0,
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "trades_count": 0,
        "holdings_count": 0,
    }

    cand3_summary = {
        "id": "cand3_dual_momentum_buf30",
        "name": "Candidate 3: Relative-Plus-Absolute Strength",
        "status": "ACTIVE",
        "buffer_band": "Absolute (Ret>0 & >SMA200) + Relative Top 20",
        "simulated_capital": 20000.0,
        "cash_balance": 20000.0,
        "total_equity": 20000.0,
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "trades_count": 0,
        "holdings_count": 0,
    }

    cand4_summary = {
        "id": "cand4_value_radar",
        "name": "Candidate 4: Value-Based Strategy",
        "status": "UNAVAILABLE",
        "reason": "No trustworthy point-in-time fundamental data (balance sheets/quarterly P&L) available in frozen repository.",
        "simulated_capital": 20000.0,
        "cash_balance": 20000.0,
        "total_equity": 20000.0,
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trades_count": 0,
        "holdings_count": 0,
    }

    benchmark_summary = {
        "id": "benchmark_niftybees",
        "name": "NIFTYBEES.NS Total Return ETF",
        "status": "PASSIVE_BENCHMARK",
        "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0,
    }

    if replay_data:
        c1 = replay_data.get("candidate1", {})
        m1 = c1.get("metrics", {})
        cand1_summary["total_equity"] = c1.get("final_equity", 20000.0)
        cand1_summary["cagr_pct"] = m1.get("cagr_pct", 0.0)
        cand1_summary["max_drawdown_pct"] = m1.get("max_drawdown_pct", 0.0)
        cand1_summary["sharpe_ratio"] = m1.get("sharpe_ratio", 0.0)
        cand1_summary["trades_count"] = m1.get("total_trades", 0)
        cand1_summary["holdings_count"] = c1.get("latest_holdings_count", 0)

        c2 = replay_data.get("candidate2", {})
        m2 = c2.get("metrics", {})
        cand2_summary["total_equity"] = c2.get("final_equity", 20000.0)
        cand2_summary["cagr_pct"] = m2.get("cagr_pct", 0.0)
        cand2_summary["max_drawdown_pct"] = m2.get("max_drawdown_pct", 0.0)
        cand2_summary["sharpe_ratio"] = m2.get("sharpe_ratio", 0.0)
        cand2_summary["trades_count"] = m2.get("total_trades", 0)
        cand2_summary["holdings_count"] = c2.get("latest_holdings_count", 0)

        c3 = replay_data.get("candidate3", {})
        m3 = c3.get("metrics", {})
        cand3_summary["total_equity"] = c3.get("final_equity", 20000.0)
        cand3_summary["cagr_pct"] = m3.get("cagr_pct", 0.0)
        cand3_summary["max_drawdown_pct"] = m3.get("max_drawdown_pct", 0.0)
        cand3_summary["sharpe_ratio"] = m3.get("sharpe_ratio", 0.0)
        cand3_summary["trades_count"] = m3.get("total_trades", 0)
        cand3_summary["holdings_count"] = c3.get("latest_holdings_count", 0)

        bench = replay_data.get("benchmark", {})
        benchmark_summary["cagr_pct"] = bench.get("cagr_pct", 0.0)
        benchmark_summary["max_drawdown_pct"] = bench.get("max_drawdown_pct", 0.0)

    return {
        "disclaimer": "Simulated Research Capital (INR 20,000.00 each) — Not Deployable Broker Funds.",
        "data_freshness": {
            "last_processed_date": snapshot_date,
            "status": "DATA_SYNCHRONIZED",
            "universe_count": 70,
            "regime_filter": "NSE 200-day SMA Active",
        },
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
    Returns detailed account state, holdings, orders journal, and trades journal for a strategy.
    """
    prefix = "normal_"
    acc_id = f"{prefix}{strategy_id}"
    acc_state = _load_account_state(acc_id) or _load_account_state(strategy_id)

    # Read CSVs if present
    orders = []
    trades = []
    daily = []

    orders_file = BROKER_STATE_DIR / f"{acc_id}_orders.csv"
    if not orders_file.exists():
        orders_file = BROKER_STATE_DIR / f"{strategy_id}_orders.csv"
    if orders_file.exists():
        try:
            import pandas as pd
            orders = pd.read_csv(orders_file).fillna("").to_dict(orient="records")
        except Exception:
            pass

    trades_file = BROKER_STATE_DIR / f"{acc_id}_trades.csv"
    if not trades_file.exists():
        trades_file = BROKER_STATE_DIR / f"{strategy_id}_trades.csv"
    if trades_file.exists():
        try:
            import pandas as pd
            trades = pd.read_csv(trades_file).fillna("").to_dict(orient="records")
        except Exception:
            pass

    daily_file = BROKER_STATE_DIR / f"{acc_id}_daily.csv"
    if not daily_file.exists():
        daily_file = BROKER_STATE_DIR / f"{strategy_id}_daily.csv"
    if daily_file.exists():
        try:
            import pandas as pd
            daily = pd.read_csv(daily_file).fillna("").to_dict(orient="records")
        except Exception:
            pass

    return {
        "strategy_id": strategy_id,
        "account": acc_state or {
            "initial_capital": 20000.0,
            "cash": 20000.0,
            "total_equity": 20000.0,
            "holdings": {},
            "cumulative_costs": 0.0,
            "cumulative_slippage": 0.0,
        },
        "orders_count": len(orders),
        "trades_count": len(trades),
        "orders_journal": orders[-100:],  # latest 100
        "trades_journal": trades[-100:],  # latest 100
        "daily_snapshots": daily[-250:],  # latest 250 bars for equity curve
    }


@router.get("/paper-trading/replay")
def get_replay_results(stress: bool = False):
    """Returns cached historical replay comparison results (normal or 2x stress)."""
    prefix = "stress_" if stress else "normal_"
    replay_file = REPLAY_STATE_DIR / f"replay_{prefix}results.json"

    if replay_file.exists():
        try:
            with open(replay_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read replay file {replay_file}: {e}")

    # If not yet generated, run replay runner on demand
    runner = HistoricalReplayRunner(
        output_dir=str(REPLAY_STATE_DIR),
        initial_capital=20000.0,
    )
    result = runner.run_replay(stress_multiplier=2.0 if stress else 1.0)
    return result


@router.post("/paper-trading/replay/run")
def trigger_replay_run(stress: bool = False):
    """Triggers a complete historical replay re-run across the frozen dataset."""
    try:
        runner = HistoricalReplayRunner(
            output_dir=str(REPLAY_STATE_DIR),
            initial_capital=20000.0,
        )
        result = runner.run_replay(stress_multiplier=2.0 if stress else 1.0)
        return {"status": "SUCCESS", "message": "Replay run completed successfully.", "summary": result}
    except Exception as e:
        logger.error(f"Replay run error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

