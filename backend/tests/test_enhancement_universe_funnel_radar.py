import datetime
import json
import unittest.mock as mock
import pandas as pd
import pytest

from app.engine.corporate_actions import verify_corporate_action_adjustments_sample
from app.engine.fundamentals import evaluate_fundamentals
from app.engine.fundamentals_engine import fundamentals_engine
from app.engine.pipeline import decision_pipeline
from app.engine.planner import planner, PlannedSignal, TradePlan
from app.engine.regime import evaluate_market_regime
from app.engine.screener import screener_engine
from app.engine.universe import universe_manager, UniverseStock
from app.engine.value_radar import value_radar_engine
from app.models import FundamentalSnapshot


# ============================================================================
# 1. Master Parsing & Series Filtering
# ============================================================================

def test_instrument_master_parsing_and_series_filtering():
    """Verify Angel One master parsing accepts NSE -EQ series, rejects SME/trade-for-trade,
    and excludes ETF / InVIT instruments with status SERIES_EXCLUDED.
    """
    mock_master = {
        "RELIANCE": {"token": "2885", "symbol": "RELIANCE", "raw_symbol": "RELIANCE-EQ", "name": "RELIANCE IND", "exch_seg": "NSE"},
        "NIFTYBEES": {"token": "10511", "symbol": "NIFTYBEES", "raw_symbol": "NIFTYBEES-EQ", "name": "NIPPON INDIA NIFTY BEES ETF", "exch_seg": "NSE"},
        "CPSEETF": {"token": "13143", "symbol": "CPSEETF", "raw_symbol": "CPSEETF-EQ", "name": "CPSE ETF", "exch_seg": "NSE"},
        "SMECO": {"token": "9999", "symbol": "SMECO", "raw_symbol": "SMECO-SM", "name": "SME COMPANY LTD", "exch_seg": "NSE"},
        "BECO": {"token": "8888", "symbol": "BECO", "raw_symbol": "BECO-BE", "name": "TRADE TO TRADE CO", "exch_seg": "NSE"},
        "BSECO": {"token": "7777", "symbol": "BSECO", "raw_symbol": "BSECO-EQ", "name": "BSE ONLY COMPANY", "exch_seg": "BSE"},
    }

    with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(mock_master))), \
         mock.patch("pathlib.Path.exists", return_value=True):
        parsed = universe_manager.parse_master_scrip_list(market="IN", bse_enabled=False)

    by_sym = {p["symbol"]: p for p in parsed}

    # 1. Standard NSE equity is SCANNED / eligible
    assert "RELIANCE" in by_sym
    assert by_sym["RELIANCE"]["status"] == "SCANNED"
    assert by_sym["RELIANCE"]["series"] == "EQ"

    # 2. ETFs are excluded
    assert "NIFTYBEES" in by_sym
    assert by_sym["NIFTYBEES"]["status"] == "SERIES_EXCLUDED"
    assert "CPSEETF" in by_sym
    assert by_sym["CPSEETF"]["status"] == "SERIES_EXCLUDED"

    # 3. SME (-SM) and Trade-for-Trade (-BE) are excluded
    assert "SMECO" in by_sym
    assert by_sym["SMECO"]["status"] == "SERIES_EXCLUDED"
    assert "BECO" in by_sym
    assert by_sym["BECO"]["status"] == "SERIES_EXCLUDED"

    # 4. BSE-only stock is omitted when bse_enabled=False
    assert "BSECO" not in by_sym


# ============================================================================
# 2. Every Instrument Gets Exactly One Status
# ============================================================================

def test_every_instrument_gets_exactly_one_status():
    """Verify that every single candidate receives exactly one primary status code
    from the documented enumeration: SCANNED | NO_DATA | INSUFFICIENT_HISTORY (<252 bars) |
    ILLIQUID | PRICE_FLOOR | VOLATILITY_CAP | SERIES_EXCLUDED | DATA_ERROR.
    """
    valid_statuses = {
        "SCANNED",
        "NO_DATA",
        "INSUFFICIENT_HISTORY (<252 bars)",
        "ILLIQUID",
        "PRICE_FLOOR",
        "VOLATILITY_CAP",
        "SERIES_EXCLUDED",
        "DATA_ERROR",
    }

    dates = pd.date_range("2024-01-01", periods=300, freq="B").date

    # Case A: No data
    res_no_data = universe_manager.filter_stock("NODATA_SYM", None)
    assert res_no_data.status in valid_statuses
    assert res_no_data.status == "NO_DATA"

    # Case B: Insufficient history (< 252 bars)
    short_dates = dates[:100]
    df_short = pd.DataFrame({
        "date": short_dates,
        "open": [100.0] * 100, "high": [105.0] * 100, "low": [95.0] * 100,
        "close": [100.0] * 100, "volume": [10000000.0] * 100, "atr14": [2.0] * 100
    })
    res_short = universe_manager.filter_stock("SHORT_SYM", df_short)
    assert res_short.status in valid_statuses
    assert res_short.status == "INSUFFICIENT_HISTORY (<252 bars)"

    # Case C: Illiquid
    df_illiquid = pd.DataFrame({
        "date": dates,
        "open": [100.0] * 300, "high": [105.0] * 300, "low": [95.0] * 300,
        "close": [100.0] * 300, "volume": [10.0] * 300, "atr14": [2.0] * 300
    })
    res_illiquid = universe_manager.filter_stock("ILLIQUID_SYM", df_illiquid)
    assert res_illiquid.status in valid_statuses
    assert res_illiquid.status == "ILLIQUID"

    # Case D: Price Floor
    df_cheap = pd.DataFrame({
        "date": dates,
        "open": [10.0] * 300, "high": [12.0] * 300, "low": [9.0] * 300,
        "close": [10.0] * 300, "volume": [100000000.0] * 300, "atr14": [0.2] * 300
    })
    res_cheap = universe_manager.filter_stock("CHEAP_SYM", df_cheap)
    assert res_cheap.status in valid_statuses
    assert res_cheap.status == "PRICE_FLOOR"

    # Case E: Volatility Cap
    df_volatile = pd.DataFrame({
        "date": dates,
        "open": [100.0] * 300, "high": [120.0] * 300, "low": [80.0] * 300,
        "close": [100.0] * 300, "volume": [100000000.0] * 300, "atr14": [15.0] * 300 # 15% ATR > 6% cap
    })
    res_volatile = universe_manager.filter_stock("VOLATILE_SYM", df_volatile)
    assert res_volatile.status in valid_statuses
    assert res_volatile.status == "VOLATILITY_CAP"

    # Case F: Scanned & passed
    df_clean = pd.DataFrame({
        "date": dates,
        "open": [100.0] * 300, "high": [105.0] * 300, "low": [98.0] * 300,
        "close": [102.0] * 300, "volume": [10000000.0] * 300, "atr14": [2.0] * 300
    })
    res_clean = universe_manager.filter_stock("CLEAN_SYM", df_clean)
    assert res_clean.status in valid_statuses
    assert res_clean.status == "SCANNED"
    assert res_clean.passed is True


# ============================================================================
# 3. Funnel Monotonicity Guarantee
# ============================================================================

def test_funnel_monotonicity():
    """Verify that every funnel stage count never exceeds any previous stage count:
    Scanned >= Trend template pass >= Valid setup structure >= Fundamentals not RED >= News not BLOCKED >= Risk OK >= PASS.
    """
    mock_symbols = [UniverseStock(symbol=f"SYM{i}", name=f"Stock {i}", sector="General", industry="General", market="IN", tier="Large", series="EQ") for i in range(10)]
    dates = pd.date_range("2024-01-01", periods=300, freq="B").date

    bars_dict = {}
    for i, s in enumerate(mock_symbols):
        # SYM0-SYM4 liquid and uptrending, SYM5-SYM9 illiquid
        vol = 10000000.0 if i < 5 else 10.0
        close = 100.0 + (i * 10.0)
        bars_dict[s.symbol] = pd.DataFrame({
            "date": dates,
            "open": [close] * 300,
            "high": [close + 2.0] * 300,
            "low": [close - 2.0] * 300,
            "close": [close] * 300,
            "volume": [vol] * 300,
            "atr14": [2.0] * 300,
            "sma50": [close - 5.0] * 300,
            "sma150": [close - 10.0] * 300,
            "sma200": [close - 15.0] * 300,
            "ema20": [close - 2.0] * 300,
            "ema50": [close - 5.0] * 300,
            "high_52w": [close + 5.0] * 300,
            "low_52w": [close - 30.0] * 300,
        })

    with mock.patch.object(universe_manager, "load_universe", return_value=mock_symbols), \
         mock.patch("app.providers.manager.provider_manager.get_daily_bars", return_value=bars_dict):
        plan = planner.run_scan(market="IN", db=None)

    assert plan.funnel is not None and len(plan.funnel) == 7

    # Extract sequential counts
    counts = [stage["count"] for stage in plan.funnel]
    labels = [stage["label"] for stage in plan.funnel]

    # Monotonicity invariant: each stage <= previous stage
    for i in range(1, len(counts)):
        assert counts[i] <= counts[i - 1], f"Funnel violation: {labels[i]} ({counts[i]}) exceeded {labels[i-1]} ({counts[i-1]})"


# ============================================================================
# 4. Regime-Blocked Rows & NOT EVALUATED Stages
# ============================================================================

from app.engine.indicators import add_all_indicators

def test_regime_blocked_rows_show_exact_distance_and_not_evaluated_stages():
    """Verify that when market regime is WEAK, blocked rows show exact distance in %
    and downstream stages that were not reached are labeled NOT EVALUATED (not UNKNOWN/WAIT).
    """
    dates = pd.date_range("2024-01-01", periods=300, freq="B").date
    # Nifty 50 close = 23,810.85 below SMA200 24,017.32 -> -0.86%
    index_df = pd.DataFrame({
        "date": dates,
        "open": [23800.0] * 300, "high": [23900.0] * 300, "low": [23700.0] * 300,
        "close": [23810.85] * 300, "volume": [100000.0] * 300,
        "sma50": [24500.0] * 300, "sma200": [24017.32] * 300,
    })

    stock_df = pd.DataFrame({
        "date": dates,
        "open": [500.0] * 300, "high": [510.0] * 300, "low": [490.0] * 300,
        "close": [500.0] * 300, "volume": [1000000.0] * 300,
    })
    stock_df = add_all_indicators(stock_df)

    decision = decision_pipeline.evaluate(
        symbol="TESTSYM",
        df=stock_df,
        market="IN",
        index_df=index_df,
        db=None,
    )

    # 1. Market regime check note format
    regime_check = next(c for c in decision.stages[0].checks if c.name == "Market Regime")
    assert not regime_check.passed
    assert "Regime WEAK" in regime_check.note
    assert "23,810.85" in regime_check.note
    assert "24,017.32" in regime_check.note
    assert "-0.86%" in regime_check.note

    # 2. Unevaluated execution mechanics must have status "NOT EVALUATED"
    stage_map = {s.stage_name: s.status for s in decision.stages}
    assert stage_map["Entry Planner"] == "NOT EVALUATED"
    assert stage_map["Exit Planner"] == "NOT EVALUATED"
    assert stage_map["Position Sizer"] == "NOT EVALUATED"
    assert stage_map["Risk Validator"] == "NOT EVALUATED"


# ============================================================================
# 5. Corporate Action Adjustment Check
# ============================================================================

def test_corporate_action_adjustment_check():
    """Verify that sample split adjustment check accurately verifies split-adjusted
    series and flags unadjusted artificial drops (>40% plunge across ex-dates).
    """
    dates = pd.date_range("2022-07-20", periods=20, freq="B").date
    # TATASTEEL 10:1 split was 2022-07-28

    # Clean split-adjusted series (~100 before and after)
    clean_df = pd.DataFrame({
        "date": dates,
        "close": [98.0 if d < datetime.date(2022, 7, 28) else 100.0 for d in dates],
        "volume": [100000.0] * 20,
    })

    # Unadjusted series (~1000 before, ~100 after = 90% plunge)
    unadjusted_df = pd.DataFrame({
        "date": dates,
        "close": [1000.0 if d < datetime.date(2022, 7, 28) else 100.0 for d in dates],
        "volume": [10000.0] * 20,
    })

    clean_audit = verify_corporate_action_adjustments_sample({"TATASTEEL": clean_df}, sample_symbols=["TATASTEEL"])
    assert clean_audit["is_safe"] is True
    assert clean_audit["unadjusted_count"] == 0

    dirty_audit = verify_corporate_action_adjustments_sample({"TATASTEEL": unadjusted_df}, sample_symbols=["TATASTEEL"])
    assert dirty_audit["is_safe"] is False
    assert dirty_audit["unadjusted_count"] == 1
    assert "TATASTEEL" in dirty_audit["unadjusted_symbols"]


# ============================================================================
# 6. Fundamentals Completeness & UNKNOWN Never Green
# ============================================================================

def test_fundamentals_completeness_and_unknown_never_green():
    """Verify that completeness calculation follows COMPLETE | PARTIAL | NONE,
    and missing values remain strictly UNKNOWN (never GREEN).
    """
    # 1. Missing data produces UNKNOWN, never GREEN
    lights_res = evaluate_fundamentals({"symbol": "TEST"}, sector="General", financial=False)
    for light in lights_res["lights"]:
        assert light["status"] in ("UNKNOWN", "YELLOW", "RED")
        # Missing fields must NEVER be GREEN
        if light["value"] in ("No data", "No sector comparison", None):
            assert light["status"] == "UNKNOWN"

    # 2. Completeness scoring
    comp_full = fundamentals_engine.calculate_completeness({
        "revenue_yoy": 15.0, "profit_yoy": 20.0, "op_margin": 2.5,
        "roce": 18.0, "pe": 22.0, "debt_equity": 0.3, "promoter_holding": 60.0
    })
    assert comp_full == "COMPLETE"

    comp_partial = fundamentals_engine.calculate_completeness({
        "revenue_yoy": 12.0, "profit_yoy": 14.0
    })
    assert comp_partial == "PARTIAL"

    comp_none = fundamentals_engine.calculate_completeness({})
    assert comp_none == "NONE"


# ============================================================================
# 7. Value Radar Criteria & Why Zero Breakdown
# ============================================================================

def test_value_radar_criteria_and_why_zero_breakdown():
    """Verify Value Radar filtering rules and verify that when 0 ideas pass,
    it produces an honest 'Why Zero' breakdown counting exclusions by each rule.
    """
    class MockSnap:
        def __init__(self, sym, val_ratio, quality, profit_growth, pe=15.0, sec_pe=20.0):
            self.symbol = sym
            self.revenue_yoy = 10.0
            self.profit_yoy = profit_growth
            self.op_margin = 1.0
            self.roce = quality
            self.roe = quality
            self.debt_equity = 0.4
            self.interest_coverage = 4.0
            self.pe = pe
            self.sector_median_pe = sec_pe
            self.promoter_holding = 50.0
            self.pledge_pct = 0.0
            self.lights_json = None

    dates = pd.date_range("2024-01-01", periods=250, freq="B").date
    bars_dict = {
        "CHEAP_PASS": pd.DataFrame({"date": dates, "close": [100.0] * 250, "volume": [100000.0] * 250}),
        "EXPENSIVE": pd.DataFrame({"date": dates, "close": [100.0] * 250, "volume": [100000.0] * 250}),
        "POOR_QUALITY": pd.DataFrame({"date": dates, "close": [100.0] * 250, "volume": [100000.0] * 250}),
    }

    mock_snaps = {
        # Cheap (PE 15 vs sec 20 = 0.75x < 0.8x -> Green), ROCE 18% (Green), Profit growth 20% (Green)
        "CHEAP_PASS": MockSnap("CHEAP_PASS", val_ratio=0.75, quality=18.0, profit_growth=20.0),
        # Expensive (PE 35 vs sec 20 = 1.75x > 1.5x -> Red)
        "EXPENSIVE": MockSnap("EXPENSIVE", val_ratio=1.75, quality=18.0, profit_growth=20.0, pe=35.0, sec_pe=20.0),
        # Poor quality (ROCE 5% < 10% -> Red)
        "POOR_QUALITY": MockSnap("POOR_QUALITY", val_ratio=0.75, quality=5.0, profit_growth=20.0),
    }

    with mock.patch.object(fundamentals_engine, "get_all_latest_snapshots", return_value=mock_snaps):
        res = value_radar_engine.evaluate_universe(
            market="IN",
            candidate_symbols=["CHEAP_PASS", "EXPENSIVE", "POOR_QUALITY", "NO_DATA_STOCK"],
            bars_dict=bars_dict,
        )

    summary = res["summary"]
    assert summary["total_scanned"] == 4
    assert summary["with_fundamentals"] == 3
    assert summary["no_fundamentals"] == 1
    assert summary["excluded_valuation"] == 1 # EXPENSIVE
    assert summary["excluded_quality"] == 1   # POOR_QUALITY
    assert len(res["ideas"]) == 1
    assert res["ideas"][0]["symbol"] == "CHEAP_PASS"
    assert "scanned" in res["explanation"]
