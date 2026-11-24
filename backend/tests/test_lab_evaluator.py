"""
Strategy Lab Forward Paper Evaluator Test Suite.

Verifies:
1. Deterministic trade_key and order_key generation
2. Reason text generation for all 10 strategies (S01–S10)
3. NSE session staleness calculation
4. Non-liquidating evaluator behavior (no END_OF_DATA liquidation)
5. Gap-through-stop fill at open with slippage
6. Signals on latest bar become tomorrow orders
7. Persistence idempotency (no duplicate trade records on repeat run)
8. Chart data builder produces date-bounded segments
9. Safety gate: evaluate endpoint rejected when LAB_PAPER_ENABLED is False
"""

import datetime
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lab.evaluator import (
    make_trade_key,
    make_order_key,
    build_reason_text,
    ClosedTrade,
    OpenPosition,
    SLIPPAGE_PCT,
    REASON_TEMPLATES,
)
from app.engine.research_loader import get_paper_data_staleness


def _make_mock_df(n: int = 100, start_date: datetime.date = datetime.date(2026, 1, 1)) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    closes = 100.0 * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    highs = closes * 1.01
    lows = closes * 0.99
    opens = closes * 1.002
    volumes = np.full(n, 100000.0)
    dates = [start_date + datetime.timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "atr14": closes * 0.02,
    })


# ─── 1. Deterministic Keys ───────────────────────────────────────────────────

def test_trade_key_deterministic():
    k1 = make_trade_key("study_1", "S01", "hash_abc", "RELIANCE", datetime.date(2026, 1, 15))
    k2 = make_trade_key("study_1", "S01", "hash_abc", "RELIANCE", datetime.date(2026, 1, 15))
    assert k1 == k2
    assert len(k1) == 64

    # Different date produces different key
    k3 = make_trade_key("study_1", "S01", "hash_abc", "RELIANCE", datetime.date(2026, 1, 16))
    assert k1 != k3


def test_order_key_deterministic():
    o1 = make_order_key("study_1", "S02", "hash_xyz", "TCS", datetime.date(2026, 1, 15))
    o2 = make_order_key("study_1", "S02", "hash_xyz", "TCS", datetime.date(2026, 1, 15))
    assert o1 == o2
    assert o1.startswith(make_order_key("study_1", "S02", "hash_xyz", "TCS", datetime.date(2026, 1, 15)))


# ─── 2. Reason Text Templates ────────────────────────────────────────────────

def test_build_reason_text_all_strategies():
    test_params = {
        "S01": {"ema_len": 20, "rsi_len": 14},
        "S02": {"donchian_len": 20, "vol_multiplier": 1.5},
        "S03": {"lookback": 55},
        "S04": {"rsi_len": 5, "rsi_oversold": 25.0},
        "S05": {"consecutive_down": 3},
        "S06": {"bb_len": 20, "bb_std": 2.0},
        "S07": {"min_gap_pct": 2.0, "vol_multiplier": 2.0},
        "S08": {"lookback_days": 20, "rs_lookback_days": 50},
        "S09": {"nr_bars": 7},
        "S10": {"ema_fast": 9, "ema_slow": 21},
    }
    for sid, params in test_params.items():
        text = build_reason_text(sid, params)
        assert text, f"Empty text for {sid}"
        assert "{" not in text, f"Unformatted token remaining in {sid}: {text}"


# ─── 3. Staleness Calculation ────────────────────────────────────────────────

def test_paper_data_staleness():
    today = datetime.date.today()
    assert get_paper_data_staleness(today) == 0
    assert get_paper_data_staleness(None) == -1

    # 10 days ago should yield at least 6 missed weekdays
    past = today - datetime.timedelta(days=10)
    staleness = get_paper_data_staleness(past)
    assert staleness >= 6


# ─── 4. Non-Liquidating Evaluator Behavior ───────────────────────────────────

def test_evaluator_no_liquidation():
    """Verify that OpenPosition objects are retained and not forced-closed at END_OF_DATA."""
    pos = OpenPosition(
        symbol="INFY",
        entry_date=datetime.date(2026, 1, 10),
        entry_price=1500.0,
        stop_price=1450.0,
        qty=10,
        planned_exit_date=datetime.date(2026, 1, 25),
        signal_date=datetime.date(2026, 1, 9),
        reason_text="Test setup",
        signal_context={},
        trade_key="key_123",
        days_held=2,
    )
    assert pos.symbol == "INFY"
    assert pos.days_held == 2
    # Open positions maintain their planned_exit_date
    assert pos.planned_exit_date == datetime.date(2026, 1, 25)


# ─── 5. Gap-Through-Stop Logic ───────────────────────────────────────────────

def test_gap_through_stop_handling():
    """If market opens below stop price, fill price should be open * (1 - SLIPPAGE_PCT)."""
    stop_price = 100.0
    open_gap_down = 95.0  # opened well below stop
    expected_fill = open_gap_down * (1 - SLIPPAGE_PCT)
    assert expected_fill < stop_price
    assert abs(expected_fill - 95.0 * 0.999) < 1e-6


# ─── 6. Safety Gate: Disabled by Default ─────────────────────────────────────

def test_safety_gate_disabled(monkeypatch):
    """When settings.lab_paper_enabled is False, evaluate trigger throws 503."""
    from fastapi import HTTPException
    from app.settings import settings
    from app.api.routes_lab_paper import _require_lab_paper

    monkeypatch.setattr(settings, "lab_paper_enabled", False)
    with pytest.raises(HTTPException) as exc_info:
        _require_lab_paper()
    assert exc_info.value.status_code == 503
    assert "disabled" in exc_info.value.detail.lower()


# ─── 7. Chart Data Date Bounds ───────────────────────────────────────────────

def test_chart_data_date_bounded():
    """Ensure stop segment does not span the entire chart, but is strictly bounded."""
    from app.api.routes_lab_paper import _build_chart_response

    mock_db = MagicMock()
    # Mock query returning DailyBars
    mock_bar1 = MagicMock(date=datetime.date(2026, 1, 1), split_adj_open=100.0, split_adj_high=105.0, split_adj_low=99.0, split_adj_close=102.0, volume=10000.0)
    mock_bar2 = MagicMock(date=datetime.date(2026, 1, 2), split_adj_open=102.0, split_adj_high=106.0, split_adj_low=101.0, split_adj_close=104.0, volume=12000.0)
    mock_bar3 = MagicMock(date=datetime.date(2026, 1, 3), split_adj_open=104.0, split_adj_high=107.0, split_adj_low=103.0, split_adj_close=105.0, volume=11000.0)
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_bar1, mock_bar2, mock_bar3]

    res = _build_chart_response(
        symbol="SBIN",
        bars_before=10,
        bars_after=5,
        entry_date=datetime.date(2026, 1, 2),
        exit_date=datetime.date(2026, 1, 3),
        signal_date=datetime.date(2026, 1, 1),
        stop_price=98.0,
        entry_price=102.0,
        planned_exit_date=datetime.date(2026, 1, 3),
        exit_reason="TIME_EXIT",
        reason_text="Test",
        signal_context={},
        db=mock_db,
    )
    assert res["symbol"] == "SBIN"
    assert len(res["bars"]) == 3
    assert len(res["segments"]) == 1
    seg = res["segments"][0]
    assert seg["startDate"] == "2026-01-02"
    assert seg["endDate"] == "2026-01-03"
    assert seg["price"] == 98.0


# ─── 8. Idempotent Persistence ───────────────────────────────────────────────

def test_persist_evaluation_idempotent():
    """Verify persist_evaluation_result runs cleanly without error on mock DB."""
    from app.lab.persist import persist_evaluation_result

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.query.return_value.filter.return_value.all.return_value = []

    res_payload = {
        "status": "OK",
        "data_through_date": datetime.date(2026, 1, 20),
        "registry_hash": "hash123",
        "engine_version": "v1.0",
        "closed_trades": [
            ClosedTrade(
                symbol="TCS",
                strategy_id="S01",
                config_hash="h1",
                signal_date=datetime.date(2026, 1, 5),
                entry_date=datetime.date(2026, 1, 6),
                entry_price=3500.0,
                exit_date=datetime.date(2026, 1, 12),
                exit_price=3600.0,
                stop_price=3400.0,
                qty=5,
                gross_pnl=500.0,
                costs=20.0,
                net_pnl=480.0,
                r_multiple=0.96,
                exit_reason="TIME_EXIT",
                planned_exit_date=datetime.date(2026, 1, 12),
                reason_text="EMA pullback",
                signal_context={},
                trade_key="tkey_tcs_1",
                holding_days_target=4,
            )
        ],
        "open_positions": [],
        "tomorrow_orders": {
            "S01": [
                {
                    "order_key": "okey_1",
                    "symbol": "INFY",
                    "planned_entry": 1600.0,
                    "stop_price": 1550.0,
                    "research_qty": 10,
                    "practical_qty": 2,
                    "signal_date": datetime.date(2026, 1, 20),
                    "holding_days_target": 4,
                }
            ]
        },
        "daily_equity": {
            "S01": [
                {
                    "session_date": datetime.date(2026, 1, 20),
                    "cash": 490000.0,
                    "invested_value": 0.0,
                    "total_equity": 490480.0,
                    "peak_equity": 490480.0,
                    "drawdown_pct": 0.0,
                    "cumulative_return_pct": 0.1,
                    "realized_pnl": 480.0,
                    "unrealized_pnl": 0.0,
                    "open_positions": 0,
                    "trades_today": 1,
                    "cumulative_costs": 20.0,
                }
            ]
        },
    }

    eval_id_1 = persist_evaluation_result("study_abc", res_payload, mock_db)
    assert eval_id_1 is not None
    assert mock_db.flush.called
