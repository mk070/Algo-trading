"""
Cycle 4: Daily Paper-Trading Runner
Strictly Offline / Paper Simulation — No Live Broker Order Placement

Usage:
    python research/cycle4/daily_paper_runner.py [--date YYYY-MM-DD] [--force-rebalance] [--capital 17500.0]
"""

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.engine.cycle4_paper import Cycle4PaperEngine, run_cycle4_daily_step, json_serializer
from app.engine.calendars import is_exchange_holiday

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Cycle4Runner")


def load_market_data(target_date: Optional[datetime.date] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Loads historical market data combining the frozen baseline snapshot with verified prospective EOD bars.
    Validates date, source, and completeness. Refuses to treat stale snapshot as new daily data.
    """
    snap_path = Path("data/research/research_snapshot_20261106.parquet")
    bench_path = Path("data/research/benchmark_series.parquet")

    if not snap_path.exists():
        raise FileNotFoundError(f"Snapshot {snap_path} missing.")
    if not bench_path.exists():
        raise FileNotFoundError(f"Benchmark file {bench_path} missing.")

    snap_df = pd.read_parquet(snap_path)
    bench_df = pd.read_parquet(bench_path)
    snap_df["date"] = pd.to_datetime(snap_df["date"])
    bench_df["date"] = pd.to_datetime(bench_df["date"])

    # Check prospective data directory for fresh daily bars beyond 2026-11-05
    data_dir = Path("research/cycle4/data")
    prosp_bars_file = data_dir / "prospective_daily_bars.parquet"
    prosp_bench_file = data_dir / "prospective_benchmarks.parquet"

    if prosp_bars_file.exists():
        p_bars = pd.read_parquet(prosp_bars_file)
        p_bars["date"] = pd.to_datetime(p_bars["date"])
        if not p_bars.empty:
            assert "source" in p_bars.columns, "Prospective bars missing source audit field"
            assert not p_bars["close"].isna().all(), "Prospective bars contain all-NaN close prices"
            snap_df = pd.concat([snap_df, p_bars], ignore_index=True).drop_duplicates(subset=["symbol", "date"], keep="last")

    if prosp_bench_file.exists():
        p_bench = pd.read_parquet(prosp_bench_file)
        p_bench["date"] = pd.to_datetime(p_bench["date"])
        if not p_bench.empty:
            bench_df = pd.concat([bench_df, p_bench], ignore_index=True).drop_duplicates(subset=["symbol", "date"], keep="last")

    return snap_df, bench_df


def main():
    parser = argparse.ArgumentParser(description="Cycle 4 Daily Paper-Trading Runner")
    parser.add_argument("--date", type=str, default=None, help="Trading session date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--force-rebalance", action="store_true", help="Force month-end rebalance calculation today.")
    parser.add_argument("--capital", type=float, default=17500.0, help="Starting capital (INR). Defaults to 17500.0.")
    args = parser.parse_args()

    if args.date:
        session_date = datetime.date.fromisoformat(args.date)
    else:
        # Default to current date; do not silently substitute frozen historical snapshot
        session_date = datetime.date.today()

    snap_df, bench_df = load_market_data(session_date)

    logger.info(f"Executing Cycle 4 Paper Trading for session: {session_date}")

    # Check holiday
    if is_exchange_holiday("IN", session_date):
        logger.info(f"Session {session_date} is an official exchange closure or weekend without special trading.")
        print(json.dumps({
            "status": "SKIPPED_HOLIDAY",
            "date": str(session_date),
            "reason": "Official exchange closure"
        }))
        return

    engine = Cycle4PaperEngine(
        universe_path="data/universe/research_universe_v1.csv",
        state_dir="research/cycle4/state",
        initial_capital=args.capital,
    )

    # Check idempotency: has this date already been processed?
    if engine.candidate_state.last_processed_date == str(session_date):
        logger.info(f"Session {session_date} already processed in candidate state. Checking daily ledger.")
        # If already recorded in daily_history, skip to avoid double execution
        past_dates = [r["date"] for r in engine.candidate_state.daily_history]
        if str(session_date) in past_dates and not args.force_rebalance:
            logger.info(f"Idempotency Guard: Session {session_date} already marked to market. Skipping re-execution.")
            print(json.dumps({
                "status": "ALREADY_PROCESSED",
                "date": str(session_date),
                "candidate_equity": engine.candidate_state.total_equity,
                "control_equity": engine.control_state.total_equity,
            }))
            return

    step_result = run_cycle4_daily_step(
        engine=engine,
        session_date=session_date,
        historical_bars=snap_df,
        benchmark_df=bench_df,
        force_rebalance=args.force_rebalance,
    )

    logger.info(f"Session {session_date} completed successfully.")
    logger.info(f"  Regime Status: {step_result.get('regime_status')}")
    logger.info(f"  Candidate Equity: INR {step_result['candidate']['equity']} (Cum Ret: {step_result['candidate']['cum_ret_pct']}%, DD: {step_result['candidate']['drawdown_pct']}%)")
    logger.info(f"  Control Equity:   INR {step_result['control']['equity']} (Cum Ret: {step_result['control']['cum_ret_pct']}%, DD: {step_result['control']['drawdown_pct']}%)")
    logger.info(f"  Benchmark (NIFTYBEES): INR {step_result['benchmark']['close']}")

    print(json.dumps(step_result, indent=2, default=json_serializer))


if __name__ == "__main__":
    main()
