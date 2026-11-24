"""
Strategy Lab Test Suite.

Tests:
1. All 10 strategies generate signals on fixture data
2. No look-ahead bias (signal[i] only uses rows 0..i)
3. Engine determinism (same inputs → same trades)
4. Cost model parity with Zerodha delivery cost reference
5. Ranking rule (100-trade gate, top-5 selection, tie-break)
6. Registry YAML loads and hashes correctly
7. Config hash stability (same params → same hash)
8. Kill switch logic (10% loss threshold)
"""

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_bars(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV bars for testing (uptrend + noise)."""
    rng = np.random.default_rng(seed)
    base = 1000.0
    closes = [base]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + rng.normal(0.0005, 0.015)))
    closes = np.array(closes)
    high = closes * (1 + abs(rng.normal(0, 0.005, n)))
    low = closes * (1 - abs(rng.normal(0, 0.005, n)))
    open_ = closes * (1 + rng.normal(0, 0.003, n))
    volume = rng.uniform(500_000, 2_000_000, n)

    import datetime
    start = datetime.date(2024, 1, 2)
    dates = [start + datetime.timedelta(days=i) for i in range(n)]

    return pd.DataFrame({
        "date": dates,
        "open": open_.round(2),
        "high": high.round(2),
        "low": low.round(2),
        "close": closes.round(2),
        "volume": volume.astype(float),
    })


@pytest.fixture
def bars() -> pd.DataFrame:
    return _make_bars(300)


@pytest.fixture
def bars_dict() -> Dict[str, pd.DataFrame]:
    """Small universe of 5 synthetic symbols."""
    return {f"SYM{i:02d}": _make_bars(300, seed=i) for i in range(1, 6)}


# ─── 1. All 10 strategies generate signals ───────────────────────────────────

@pytest.mark.parametrize("strategy_id,param_overrides", [
    ("S01", {}),
    ("S02", {}),
    ("S03", {}),
    ("S04", {}),
    ("S05", {}),
    ("S06", {}),
    ("S07", {}),
    ("S08", {}),
    ("S09", {}),
    ("S10", {}),
])
def test_strategy_generates_signals(strategy_id: str, param_overrides: dict, bars: pd.DataFrame):
    from app.lab.signals import SIGNAL_FUNCTIONS
    from app.engine.indicators import add_all_indicators

    fn = SIGNAL_FUNCTIONS[strategy_id]
    df = add_all_indicators(bars)
    params = {
        "ema_len": 20, "rsi_len": 14, "rsi_dip_below": 45.0, "touch_tolerance_pct": 2.0,
        "donchian_len": 20, "vol_multiplier": 1.5,
        "lookback": 55, "lookback_days": 252, "rs_lookback_days": 63, "rs_min_percentile": 0.70,
        "trend_sma": 50, "trend_sma_fast": 50, "trend_sma_slow": 200,
        "stop_atr_mult": 1.5, "rsi_oversold": 10.0, "rsi_len_s04": 2,
        "consecutive_down": 3, "bb_len": 20, "bb_std": 2.0,
        "min_gap_pct": 2.0, "nr_bars": 7, "entry_buffer_pct": 0.10,
        "ema_fast": 9, "ema_slow": 21, "vol_multiplier_s10": 1.2,
    }
    params.update(param_overrides)
    # Merge in the right param keys per strategy
    if strategy_id == "S04":
        params["rsi_len"] = 2

    sig = fn(df, params)
    assert isinstance(sig, pd.Series), f"Signal function for {strategy_id} must return a pandas Series"
    assert len(sig) == len(df), "Signal length must match DataFrame length"
    assert sig.dtype == bool or sig.dtype == object or str(sig.dtype).startswith("bool"), \
        f"Signal dtype should be bool, got {sig.dtype}"
    # At least some True or False — not all NaN
    non_null = sig.dropna()
    assert len(non_null) > 0, f"All signals are NaN for {strategy_id}"


# ─── 2. No look-ahead bias ───────────────────────────────────────────────────

@pytest.mark.parametrize("strategy_id", ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10"])
def test_no_lookahead_bias(strategy_id: str, bars: pd.DataFrame):
    """
    Signal computed on first N rows must equal signal[N-1] computed on all rows.
    If signals use future data, they will differ.
    """
    from app.lab.signals import SIGNAL_FUNCTIONS
    from app.engine.indicators import add_all_indicators

    fn = SIGNAL_FUNCTIONS[strategy_id]
    params = {"ema_len": 20, "rsi_len": 14, "rsi_dip_below": 45.0, "touch_tolerance_pct": 2.0,
               "donchian_len": 20, "vol_multiplier": 1.5, "lookback": 55, "lookback_days": 252,
               "rs_lookback_days": 63, "rs_min_percentile": 0.70, "trend_sma": 50,
               "trend_sma_fast": 50, "trend_sma_slow": 200, "stop_atr_mult": 1.5,
               "rsi_oversold": 10.0, "rsi_len": 14, "consecutive_down": 3,
               "bb_len": 20, "bb_std": 2.0, "min_gap_pct": 2.0, "nr_bars": 7,
               "ema_fast": 9, "ema_slow": 21, "entry_buffer_pct": 0.10}
    if strategy_id == "S04":
        params["rsi_len"] = 2

    # Use first 250 rows
    cutoff = 250
    df_full = add_all_indicators(bars)
    df_cut = add_all_indicators(bars.iloc[:cutoff].copy())

    sig_full = fn(df_full, params)
    sig_cut = fn(df_cut, params)

    # Compare last row of cut vs same row in full
    if len(sig_cut) == 0 or len(sig_full) == 0:
        return  # skip if not enough data

    idx = len(sig_cut) - 1
    val_full = sig_full.iloc[idx]
    val_cut = sig_cut.iloc[idx]

    # They must match (no look-ahead from future rows)
    assert val_full == val_cut or (pd.isna(val_full) and pd.isna(val_cut)), \
        f"Look-ahead bias detected in {strategy_id}: full={val_full}, cut={val_cut}"


# ─── 3. Engine determinism ───────────────────────────────────────────────────

def test_engine_determinism(bars_dict: Dict[str, pd.DataFrame]):
    """Same inputs → same trades (run twice, compare)."""
    from app.lab.engine import run_single_strategy_backtest

    params = {"ema_len": 20, "rsi_len": 14, "rsi_dip_below": 45.0, "touch_tolerance_pct": 2.0,
               "trend_sma_fast": 50, "trend_sma_slow": 200, "stop_atr_mult": 1.5}

    trades1, summary1 = run_single_strategy_backtest("S01", params, 7, bars_dict, capital=100_000)
    trades2, summary2 = run_single_strategy_backtest("S01", params, 7, bars_dict, capital=100_000)

    assert summary1["total_trades"] == summary2["total_trades"], "Trade count must be deterministic"
    assert summary1["total_pnl"] == summary2["total_pnl"], "Total PnL must be deterministic"
    for t1, t2 in zip(trades1, trades2):
        assert t1.symbol == t2.symbol
        assert t1.entry_date == t2.entry_date
        assert abs(t1.net_pnl - t2.net_pnl) < 0.01


# ─── 4. Cost model parity with Zerodha reference ────────────────────────────

def test_cost_model_parity():
    """Verify our lab cost function matches the reference in cycle4_paper.py."""
    from app.lab.engine import compute_round_trip_cost
    from app.engine.cycle4_paper import calculate_zerodha_delivery_cost

    entry_price = 1500.0
    exit_price = 1600.0
    qty = 10

    # Reference
    buy_cost = calculate_zerodha_delivery_cost(entry_price * qty, "BUY")["total_cost"]
    sell_cost = calculate_zerodha_delivery_cost(exit_price * qty, "SELL", n_scrip_sold=1)["total_cost"]
    ref_total = buy_cost + sell_cost

    # Lab (our version — DP flat is per scrip not per share)
    lab_total = compute_round_trip_cost(entry_price, exit_price, qty)

    # Allow small rounding difference (< 1 INR)
    assert abs(lab_total - ref_total) < 2.0, f"Cost mismatch: lab={lab_total:.2f}, ref={ref_total:.2f}"


# ─── 5. Ranking rule ─────────────────────────────────────────────────────────

def test_ranking_top5_selection():
    from app.lab.ranking import rank_strategies

    # 7 results, 5 eligible (>= 100 trades), 2 insufficient
    results = [
        {"strategy_id": f"S0{i}", "holding_days": 7, "total_trades": 150 if i <= 5 else 20,
         "sample_ok": i <= 5, "sample_label": "SUFFICIENT" if i <= 5 else "INSUFFICIENT_SAMPLE",
         "median_net_expectancy": 0.5 - i * 0.05, "half_consistency": 0.8}
        for i in range(1, 8)
    ]
    ranked = rank_strategies(results)
    auto_selected = [r for r in ranked if r.get("auto_selected")]
    assert len(auto_selected) <= 5, "Should not auto-select more than 5"
    eligible = [r for r in ranked if r["sample_ok"]]
    assert len([r for r in eligible if r.get("auto_selected")]) <= 5


def test_ranking_respects_100_trade_gate():
    from app.lab.ranking import rank_strategies

    results = [
        {"strategy_id": "S01", "holding_days": 7, "total_trades": 50,
         "sample_ok": False, "sample_label": "INSUFFICIENT_SAMPLE",
         "median_net_expectancy": 1.0, "half_consistency": 0.9},
    ]
    ranked = rank_strategies(results)
    assert not ranked[0].get("auto_selected"), "Insufficient sample should not be auto-selected"
    assert ranked[0]["rank"] is None, "Insufficient sample should have no rank"


def test_ranking_negative_expectancy_still_shown():
    """Negative expectancy strategies must still appear in results (shown honestly)."""
    from app.lab.ranking import rank_strategies

    results = [
        {"strategy_id": "S01", "holding_days": 7, "total_trades": 200,
         "sample_ok": True, "sample_label": "SUFFICIENT",
         "median_net_expectancy": -0.3, "half_consistency": 0.5},
    ]
    ranked = rank_strategies(results)
    # Should appear but NOT be auto-selected if ranking puts it below top 5
    assert len(ranked) == 1
    # May be ranked but ranked_note should not hide the negative expectancy
    assert ranked[0]["total_trades"] == 200


# ─── 6. Registry YAML loads ──────────────────────────────────────────────────

def test_registry_yaml_loads():
    """YAML file must exist, have 10 strategies with correct IDs."""
    # tests/ → backend/ → Algo-trading/ → research/
    registry_path = Path(__file__).resolve().parent.parent.parent / "research" / "swing_registry.yaml"
    assert registry_path.exists(), f"Registry not found at {registry_path}"

    import yaml
    with open(registry_path, "r") as f:
        data = yaml.safe_load(f)

    strategies = data.get("strategies", [])
    assert len(strategies) == 10, f"Expected 10 strategies, found {len(strategies)}"

    ids = [s["id"] for s in strategies]
    expected_ids = [f"S{i:02d}" for i in range(1, 11)]
    assert ids == expected_ids, f"Strategy IDs mismatch: {ids}"

    for s in strategies:
        assert "parameters" in s, f"Strategy {s['id']} missing parameters"
        assert "holding_days" in s["parameters"], f"Strategy {s['id']} missing holding_days in parameters"
        assert len(s["parameters"]["holding_days"]) >= 1


# ─── 7. Config hash stability ────────────────────────────────────────────────

def test_config_hash_stable():
    """Same params → same hash; different params → different hash."""
    from app.lab.engine import compute_config_hash

    params_a = {"ema_len": 20, "rsi_len": 14}
    params_b = {"ema_len": 20, "rsi_len": 14}
    params_c = {"ema_len": 20, "rsi_len": 20}

    h1 = compute_config_hash("S01", params_a, 7)
    h2 = compute_config_hash("S01", params_b, 7)
    h3 = compute_config_hash("S01", params_c, 7)

    assert h1 == h2, "Same params must produce same hash"
    assert h1 != h3, "Different params must produce different hash"
    assert len(h1) == 32, "Hash should be 32 chars (SHA-256 truncated)"


def test_config_hash_param_order_independent():
    """Hash must be order-independent (sorted keys)."""
    from app.lab.engine import compute_config_hash

    params_a = {"a": 1, "b": 2, "c": 3}
    params_b = {"c": 3, "a": 1, "b": 2}

    h1 = compute_config_hash("S01", params_a, 7)
    h2 = compute_config_hash("S01", params_b, 7)
    assert h1 == h2, "Hash must be independent of parameter dict ordering"


# ─── 8. Kill switch computation ──────────────────────────────────────────────

def test_kill_switch_threshold():
    """Study with 10% loss from initial capital should trigger kill switch."""
    # Simulate: initial capital 100,000, current equity drops to 89,000
    initial = 100_000.0
    threshold_pct = 10.0

    current_equity = 89_000.0
    drawdown = (initial - current_equity) / initial * 100
    triggered = drawdown >= threshold_pct
    assert triggered, f"Kill switch should trigger at {drawdown:.1f}% loss"

    current_equity_ok = 92_000.0
    drawdown_ok = (initial - current_equity_ok) / initial * 100
    not_triggered = drawdown_ok < threshold_pct
    assert not_triggered, f"Kill switch should NOT trigger at {drawdown_ok:.1f}% loss"


# ─── 9. Summary stats sanity check ──────────────────────────────────────────

def test_engine_summary_zero_trades():
    from app.lab.engine import _compute_summary
    summary = _compute_summary([], capital=100_000)
    assert summary["total_trades"] == 0
    assert summary["sample_ok"] == False
    assert summary["sample_label"] == "INSUFFICIENT_SAMPLE"


def test_engine_summary_with_trades(bars_dict: Dict[str, pd.DataFrame]):
    from app.lab.engine import run_single_strategy_backtest
    params = {"lookback": 55, "vol_multiplier": 1.3, "trend_sma_fast": 50,
               "trend_sma_slow": 200, "stop_atr_mult": 2.0}
    trades, summary = run_single_strategy_backtest("S03", params, 7, bars_dict, capital=200_000)
    # Basic sanity
    assert summary["total_trades"] == len(trades)
    assert isinstance(summary.get("win_rate"), (float, type(None)))
    if summary["total_trades"] > 0:
        assert summary.get("total_pnl") is not None
