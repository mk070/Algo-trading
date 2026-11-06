import datetime
import json
import sys
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from sqlalchemy import text

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db import SessionLocal
from app.backtest.simulator import BacktestSimulator
from app.backtest.walkforward import run_walk_forward_analysis, WalkForwardResult
from app.backtest.metrics import compute_backtest_metrics
from app.engine.setups import SetupEngine, SetupCandidate
from app.engine.indicators import add_all_indicators
from app.engine.historical_ingestion import historical_ingestion_engine

class CachedSetupEngine:
    """Wraps SetupEngine to memoize daily setup evaluations for candidate runs."""
    def __init__(self, base_engine: SetupEngine):
        self.base = base_engine
        self.vcp_cfg = base_engine.vcp_cfg
        self.pullback_cfg = base_engine.pullback_cfg
        self._vcp_cache: Dict[tuple, Optional[SetupCandidate]] = {}
        self._pb_cache: Dict[tuple, Optional[SetupCandidate]] = {}

    def evaluate_vcp_breakout(self, sym: str, df: pd.DataFrame, tick: float = 0.05) -> Optional[SetupCandidate]:
        last_date = df["date"].iloc[-1]
        key = (sym, last_date)
        if key not in self._vcp_cache:
            self._vcp_cache[key] = self.base.evaluate_vcp_breakout(sym, df, tick=tick)
        return self._vcp_cache[key]

    def evaluate_pullback(self, sym: str, df: pd.DataFrame, tick: float = 0.05) -> Optional[SetupCandidate]:
        last_date = df["date"].iloc[-1]
        key = (sym, last_date)
        if key not in self._pb_cache:
            self._pb_cache[key] = self.base.evaluate_pullback(sym, df, tick=tick)
        return self._pb_cache[key]

def load_all_bars(market: str) -> Dict[str, pd.DataFrame]:
    """Loads all split-adjusted bars for the market from Neon PostgreSQL and pre-enriches technical indicators."""
    symbols = historical_ingestion_engine.get_symbols_for_market(market)
    print(f"Loading bars for {len(symbols)} {market} symbols...", flush=True)
    bars_dict = {}
    with SessionLocal() as s:
        for sym in symbols:
            rows = s.execute(text("""
                SELECT date, 
                       split_adj_open as open, 
                       split_adj_high as high, 
                       split_adj_low as low, 
                       split_adj_close as close, 
                       open as raw_open,
                       high as raw_high,
                       low as raw_low,
                       close as raw_close,
                       volume, source
                FROM bars_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """), {"sym": sym}).fetchall()
            if rows and len(rows) >= 30:
                df = pd.DataFrame(rows, columns=[
                    "date", "open", "high", "low", "close", 
                    "raw_open", "raw_high", "raw_low", "raw_close", "volume", "source"
                ])
                df["date"] = pd.to_datetime(df["date"]).dt.date
                df = add_all_indicators(df)
                bars_dict[sym] = df
    print(f"Loaded and enriched {len(bars_dict)} {market} symbols with bars.", flush=True)
    return bars_dict

def evaluate_candidate(
    candidate_name: str,
    market: str,
    bars_data: Dict[str, pd.DataFrame],
    setup_filter: str,
    require_contraction: bool = True,
    capital: float = 17500.0,
) -> Dict:
    print(f"\n=======================================================", flush=True)
    print(f"Evaluating {candidate_name} ({market})...", flush=True)
    print(f"=======================================================", flush=True)
    
    # Configure cached setup engine
    base_engine = SetupEngine()
    base_engine.vcp_cfg.require_contraction = require_contraction
    engine = CachedSetupEngine(base_engine)
    simulator = BacktestSimulator(market=market, setup_engine_override=engine)
    
    # 1. Full 5-Year Backtest
    print("Running Full 5-Year Backtest...", flush=True)
    sim_res = simulator.run(
        bars_data=bars_data,
        capital=capital,
        setup_filter=setup_filter,
    )
    trades = sim_res["trades"]
    metrics = sim_res["metrics"]
    
    total_trades = len(trades)
    net_pnl = float(metrics.get("total_pnl", 0.0))
    gross_profit = float(metrics.get("gross_profit", 0.0))
    gross_loss = float(metrics.get("gross_loss", 0.0))
    gross_pnl = gross_profit - gross_loss
    total_costs = float(metrics.get("total_costs", 0.0))
    expectancy_r = float(metrics.get("expectancy_r", 0.0))
    profit_factor = float(metrics.get("profit_factor", 0.0))
    max_dd = float(metrics.get("max_drawdown_pct", 0.0))
    win_rate = float(metrics.get("win_rate", 0.0))
    
    currency = "INR " if market == "IN" else "USD "
    print(f"Total Completed Trades: {total_trades}", flush=True)
    print(f"Gross P&L: {currency}{gross_pnl:,.2f} | Costs: {currency}{total_costs:,.2f} | Net P&L: {currency}{net_pnl:,.2f}", flush=True)
    print(f"Net Expectancy: {expectancy_r:+.3f}R | Profit Factor: {profit_factor:.2f} | Max DD: {max_dd:.1f}%", flush=True)
    print(f"Win Rate: {win_rate:.1f}% (Wins: {metrics.get('winning_trades', 0)} / Losses: {metrics.get('losing_trades', 0)})", flush=True)
    
    # 2. Year-by-Year Performance Breakdown
    trades_df = pd.DataFrame([t.model_dump() if hasattr(t, "model_dump") else t for t in trades])
    yearly_results = {}
    positive_years = 0
    total_years = 0
    if not trades_df.empty and "exit_date" in trades_df.columns:
        trades_df["exit_date"] = pd.to_datetime(trades_df["exit_date"]).dt.date
        trades_df["year"] = pd.to_datetime(trades_df["exit_date"]).dt.year
        for yr, group in trades_df.groupby("year"):
            total_years += 1
            yr_trades = group.to_dict("records")
            yr_metrics = compute_backtest_metrics(yr_trades)
            if yr_metrics.total_pnl > 0 and yr_metrics.expectancy_r > 0:
                positive_years += 1
            yearly_results[int(yr)] = {
                "trades": len(yr_trades),
                "net_pnl": yr_metrics.total_pnl,
                "expectancy_r": yr_metrics.expectancy_r,
                "profit_factor": yr_metrics.profit_factor,
                "win_rate_pct": yr_metrics.win_rate,
            }
            print(f"  Year {yr}: {len(yr_trades)} trades | Net P&L: {currency}{yr_metrics.total_pnl:,.2f} | Exp: {yr_metrics.expectancy_r:+.2f}R | PF: {yr_metrics.profit_factor:.2f}", flush=True)
    else:
        print("  No trades to segment by year.", flush=True)
    
    yearly_stability_passed = (positive_years >= 3)
    print(f"Yearly Stability: {positive_years}/{total_years} positive years (Requirement: >= 3 positive years -> {'PASS' if yearly_stability_passed else 'FAIL'})", flush=True)
        
    # 3. Walk-Forward Analysis (12-mo train / 4-mo test folds, 6-mo holdout)
    print("Running Walk-Forward Rolling Analysis (with memoized candidates)...", flush=True)
    wf_res = run_walk_forward_analysis(
        bars_data=bars_data,
        market=market,
        train_months=12,
        test_months=4,
        holdout_months=6,  # Final 6 months (May 2026 - Nov 2026) reserved untouched
        setup_filter=setup_filter,
        setup_engine_override=engine,
        capital=capital,
    )
    print(f"Walk-Forward Status: {wf_res.status} | Robustness: {wf_res.robustness_score_pct}% | Windows: {wf_res.total_windows}", flush=True)
    for w in wf_res.windows:
        print(f"  Fold {w.window_index} [{w.test_start} to {w.test_end}]: Test Trades: {w.test_trades} | Test Exp: {w.test_expectancy:+.2f}R | PF: {w.test_profit_factor:.2f} | Passed: {w.passed} ({w.reason or 'OK'})", flush=True)
        
    # 4. Final Untouched Holdout Evaluation (last 6 months: 2026-05-01 to 2026-11-05)
    print("Running Untouched Holdout Evaluation...", flush=True)
    all_dates = sorted(list(set(d for df in bars_data.values() for d in df["date"])))
    holdout_start = datetime.date(2026, 5, 1)
    holdout_end = all_dates[-1] if all_dates else datetime.date.today()
    holdout_res = simulator.run(
        bars_data=bars_data,
        start_date=holdout_start,
        end_date=holdout_end,
        capital=capital,
        setup_filter=setup_filter,
    )
    holdout_trades = holdout_res["trades"]
    holdout_metrics = holdout_res["metrics"]
    h_trades_cnt = len(holdout_trades)
    h_exp = float(holdout_metrics.get("expectancy_r", 0.0))
    h_pf = float(holdout_metrics.get("profit_factor", 0.0))
    h_pnl = float(holdout_metrics.get("total_pnl", 0.0))
    h_dd = float(holdout_metrics.get("max_drawdown_pct", 0.0))
    print(f"Untouched Holdout [{holdout_start} to {holdout_end}]:", flush=True)
    print(f"  Trades: {h_trades_cnt} | Net P&L: {currency}{h_pnl:,.2f} | Exp: {h_exp:+.2f}R | PF: {h_pf:.2f} | Max DD: {h_dd:.1f}%", flush=True)
    
    # 5. Acceptance Criteria Verification
    c1_trades = (total_trades >= 150)
    c2_exp = (expectancy_r >= 0.15)
    c3_pf = (profit_factor >= 1.30)
    c4_dd = (max_dd <= 20.0)
    c5_yearly = yearly_stability_passed
    c6_wf = (wf_res.passed_validation)
    c7_holdout = (h_trades_cnt > 0 and h_exp > 0 and h_pf >= 1.0)
    
    if total_trades < 150:
        overall_status = "INSUFFICIENT DATA"
    elif c1_trades and c2_exp and c3_pf and c4_dd and c5_yearly and c6_wf and c7_holdout:
        overall_status = "PASS"
    else:
        overall_status = "FAIL"
        
    print(f"\nCRITERIA CHECK FOR {candidate_name} ({market}):", flush=True)
    print(f"  1. Minimum 150 Trades: {total_trades} >= 150 -> {'PASS' if c1_trades else 'FAIL'}", flush=True)
    print(f"  2. Net Expectancy >= +0.15R: {expectancy_r:+.3f}R -> {'PASS' if c2_exp else 'FAIL'}", flush=True)
    print(f"  3. Profit Factor >= 1.30: {profit_factor:.2f} -> {'PASS' if c3_pf else 'FAIL'}", flush=True)
    print(f"  4. Max Drawdown <= 20%: {max_dd:.1f}% -> {'PASS' if c4_dd else 'FAIL'}", flush=True)
    print(f"  5. Yearly Stability (>= 3 positive years): {positive_years} -> {'PASS' if c5_yearly else 'FAIL'}", flush=True)
    print(f"  6. Walk-Forward Robustness (>= 70%): {wf_res.robustness_score_pct}% -> {'PASS' if c6_wf else 'FAIL'}", flush=True)
    print(f"  7. Untouched Holdout Edge: Trades={h_trades_cnt}, Exp={h_exp:+.2f}R, PF={h_pf:.2f} -> {'PASS' if c7_holdout else 'FAIL'}", flush=True)
    print(f"==> OVERALL STATUS: {overall_status}\n", flush=True)
    
    return {
        "candidate": candidate_name,
        "market": market,
        "total_trades": total_trades,
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "total_costs": total_costs,
        "expectancy_r": expectancy_r,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd,
        "win_rate_pct": win_rate,
        "metrics": metrics,
        "yearly": yearly_results,
        "yearly_stability_passed": yearly_stability_passed,
        "walk_forward": wf_res.model_dump(),
        "holdout": {
            "start": str(holdout_start),
            "end": str(holdout_end),
            "trades": h_trades_cnt,
            "net_pnl": h_pnl,
            "expectancy_r": h_exp,
            "profit_factor": h_pf,
            "max_drawdown_pct": h_dd,
        },
        "criteria": {
            "c1_trades": c1_trades,
            "c2_exp": c2_exp,
            "c3_pf": c3_pf,
            "c4_dd": c4_dd,
            "c5_yearly": c5_yearly,
            "c6_wf": c6_wf,
            "c7_holdout": c7_holdout,
        },
        "status": overall_status,
    }

def save_intermediate(results: List[Dict]):
    with open("strategy_lab_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

def run_all():
    in_bars = load_all_bars("IN")
    us_bars = load_all_bars("US")
    
    all_results = []
    
    # Candidate 1: VCP breakout
    res_vcp_in = evaluate_candidate("VCP Breakout", "IN", in_bars, setup_filter="VCP", require_contraction=True)
    all_results.append(res_vcp_in)
    save_intermediate(all_results)
    
    res_vcp_us = evaluate_candidate("VCP Breakout", "US", us_bars, setup_filter="VCP", require_contraction=True)
    all_results.append(res_vcp_us)
    save_intermediate(all_results)
    
    # Candidate 2: EMA pullback
    res_pb_in = evaluate_candidate("EMA Pullback", "IN", in_bars, setup_filter="PULLBACK", require_contraction=True)
    all_results.append(res_pb_in)
    save_intermediate(all_results)
    
    res_pb_us = evaluate_candidate("EMA Pullback", "US", us_bars, setup_filter="PULLBACK", require_contraction=True)
    all_results.append(res_pb_us)
    save_intermediate(all_results)
    
    # Candidate 3: 55-day high breakout baseline
    res_55_in = evaluate_candidate("55-Day High Breakout Baseline", "IN", in_bars, setup_filter="VCP", require_contraction=False)
    all_results.append(res_55_in)
    save_intermediate(all_results)
    
    res_55_us = evaluate_candidate("55-Day High Breakout Baseline", "US", us_bars, setup_filter="VCP", require_contraction=False)
    all_results.append(res_55_us)
    save_intermediate(all_results)
    
    # Candidate 4: ABCD pattern (Rule-based)
    res_abcd = {
        "candidate": "ABCD Pattern",
        "market": "IN / US",
        "total_trades": 0,
        "net_pnl": 0.0,
        "gross_pnl": 0.0,
        "total_costs": 0.0,
        "expectancy_r": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "metrics": {"total_trades": 0, "total_pnl": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0, "win_rate": 0.0},
        "yearly": {},
        "yearly_stability_passed": False,
        "walk_forward": {"status": "INSUFFICIENT_DATA", "robustness_score_pct": 0.0, "passed_validation": False, "windows": []},
        "holdout": {"trades": 0, "net_pnl": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0},
        "criteria": {
            "c1_trades": False,
            "c2_exp": False,
            "c3_pf": False,
            "c4_dd": False,
            "c5_yearly": False,
            "c6_wf": False,
            "c7_holdout": False,
        },
        "status": "INSUFFICIENT DATA (NOT IMPLEMENTED)",
    }
    all_results.append(res_abcd)
    save_intermediate(all_results)
    
    # Candidate 5: Fibonacci trend pullback
    res_fib = {
        "candidate": "Fibonacci Trend Pullback",
        "market": "IN / US",
        "total_trades": 0,
        "net_pnl": 0.0,
        "gross_pnl": 0.0,
        "total_costs": 0.0,
        "expectancy_r": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "metrics": {"total_trades": 0, "total_pnl": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0, "win_rate": 0.0},
        "yearly": {},
        "yearly_stability_passed": False,
        "walk_forward": {"status": "INSUFFICIENT_DATA", "robustness_score_pct": 0.0, "passed_validation": False, "windows": []},
        "holdout": {"trades": 0, "net_pnl": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0},
        "criteria": {
            "c1_trades": False,
            "c2_exp": False,
            "c3_pf": False,
            "c4_dd": False,
            "c5_yearly": False,
            "c6_wf": False,
            "c7_holdout": False,
        },
        "status": "INSUFFICIENT DATA (NOT IMPLEMENTED)",
    }
    all_results.append(res_fib)
    save_intermediate(all_results)
    
    print("\n\nAll candidate evaluations completed and written to strategy_lab_results.json.", flush=True)

if __name__ == "__main__":
    run_all()
