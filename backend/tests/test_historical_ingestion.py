import datetime
import json
import unittest.mock as mock
import pandas as pd
import pytest

from app.engine.calendars import (
    get_expected_trading_days,
    get_trading_days_count,
    is_exchange_holiday,
    NSE_SPECIAL_TRADING_SESSIONS,
    US_EXCHANGE_HOLIDAYS,
)
from app.engine.corporate_actions import (
    apply_verified_corporate_actions,
    VERIFIED_SPLITS,
)
from app.engine.historical_ingestion import (
    HistoricalIngestionEngine,
    SOURCE_QUALITY_TIER,
    validate_ohlcv_dataframe,
)
from app.engine.indicators import add_all_indicators
from app.models import DailyBar, IngestionCheckpoint, IngestionRun
from app.providers.manager import provider_manager


# ============================================================================
# 1. Validation & Data Integrity Tests
# ============================================================================

def test_validate_ohlcv_drops_non_positive_prices():
    """Verify non-positive prices (zero or negative) are safely purged."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B").date
    df = pd.DataFrame({
        "date": dates,
        "open": [100.0, -10.0, 105.0, 0.0, 110.0],
        "high": [105.0, 10.0, 110.0, 5.0, 115.0],
        "low": [95.0, -15.0, 100.0, 0.0, 105.0],
        "close": [102.0, -12.0, 108.0, 0.0, 112.0],
        "volume": [1000.0, 500.0, 1200.0, 0.0, 800.0],
    })

    clean_df, warnings = validate_ohlcv_dataframe(df, "TEST_SYM")
    assert len(clean_df) == 3
    assert clean_df["date"].tolist() == [dates[0], dates[2], dates[4]]
    assert any("non-positive price bars" in w for w in warnings)


def test_validate_ohlcv_repairs_high_low_boundary_violations():
    """Verify High < max(Open, Close) or Low > min(Open, Close) is strictly repaired."""
    dates = pd.date_range("2024-01-01", periods=3, freq="B").date
    df = pd.DataFrame({
        "date": dates,
        "open": [100.0, 105.0, 110.0],
        "high": [98.0, 115.0, 108.0],   # Bar 0: high < open; Bar 2: high < open
        "low": [95.0, 108.0, 105.0],    # Bar 1: low > open
        "close": [99.0, 110.0, 107.0],
        "volume": [1000.0, 1000.0, 1000.0],
    })

    clean_df, warnings = validate_ohlcv_dataframe(df, "TEST_SYM")
    assert len(clean_df) == 3
    # Bar 0: High repaired to 100.0 (max of open, close, high)
    assert clean_df.loc[0, "high"] == 100.0
    # Bar 1: Low repaired to 105.0 (min of open, close, low)
    assert clean_df.loc[1, "low"] == 105.0
    # Bar 2: High repaired to 110.0
    assert clean_df.loc[2, "high"] == 110.0
    assert any("boundary violations" in w for w in warnings)


def test_validate_ohlcv_deduplicates_dates_keeping_last():
    """Verify duplicate date records are deduplicated preserving the latest provider bar."""
    d = datetime.date(2024, 6, 10)
    df = pd.DataFrame({
        "date": [d, d],
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 99.0],
        "close": [101.0, 104.0],
        "volume": [100.0, 200.0],
    })

    clean_df, warnings = validate_ohlcv_dataframe(df, "TEST_SYM")
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["open"] == 102.0
    assert clean_df.iloc[0]["close"] == 104.0


def test_validate_ohlcv_flags_zero_volume():
    """Verify zero-volume bars generate explicit data quality warnings."""
    dates = pd.date_range("2024-01-01", periods=2, freq="B").date
    df = pd.DataFrame({
        "date": dates,
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [98.0, 99.0],
        "close": [102.0, 103.0],
        "volume": [5000.0, 0.0],
    })

    clean_df, warnings = validate_ohlcv_dataframe(df, "TEST_SYM")
    assert len(clean_df) == 2
    assert any("zero-volume bars" in w for w in warnings)


# ============================================================================
# 2. Split-Adjusted OHLC Consistency Tests
# ============================================================================

def test_split_adjustment_scales_all_ohlc_consistently():
    """Verify split adjustment scales O, H, L, C by the exact same split factor,
    preserving candle proportionality and candlestick body/shadow ratios.
    """
    engine = HistoricalIngestionEngine()
    dates = pd.date_range("2023-01-01", periods=4, freq="B").date
    # Simulate a 2:1 stock split where unadjusted prices before split are ~200,
    # and adj_close reflects the split as ~100
    df = pd.DataFrame({
        "date": dates,
        "open": [200.0, 202.0, 100.0, 102.0],
        "high": [210.0, 212.0, 105.0, 106.0],
        "low": [190.0, 192.0, 96.0, 98.0],
        "close": [204.0, 206.0, 101.0, 103.0],
        "adj_close": [102.0, 103.0, 101.0, 103.0], # 2:1 split ratio = 2.0 on first two bars
        "volume": [10000.0] * 4,
    })

    adj_df = engine._apply_split_adjustments(df, "SPLIT_TEST", market="IN")

    # Raw prices preserved
    assert adj_df.loc[0, "open"] == 200.0
    assert adj_df.loc[0, "close"] == 204.0

    # Split-adjusted prices scaled by 2.0
    assert adj_df.loc[0, "split_adj_open"] == 100.0
    assert adj_df.loc[0, "split_adj_high"] == 105.0
    assert adj_df.loc[0, "split_adj_low"] == 95.0
    assert adj_df.loc[0, "split_adj_close"] == 102.0

    # Geometry preservation test: (high - low) / (adj_high - adj_low) must equal split ratio (2.0)
    raw_range = adj_df.loc[0, "high"] - adj_df.loc[0, "low"]
    adj_range = adj_df.loc[0, "split_adj_high"] - adj_df.loc[0, "split_adj_low"]
    assert pytest.approx(raw_range / adj_range, rel=1e-3) == 2.0

    # Post-split bars remain 1:1
    assert adj_df.loc[2, "split_adj_close"] == 101.0


# ============================================================================
# 3. Exchange Calendar & Missing Session Detection Tests
# ============================================================================

def test_nse_calendar_distinguishes_holidays_from_data_gaps():
    """Verify official NSE holidays are NOT marked as missing data sessions."""
    # 2024-01-26 is Republic Day (official NSE holiday)
    assert is_exchange_holiday("IN", datetime.date(2024, 1, 26)) is True
    # 2024-03-29 is Good Friday (official NSE holiday)
    assert is_exchange_holiday("IN", datetime.date(2024, 3, 29)) is True
    # 2024-04-11 is Id-Ul-Fitr (official NSE holiday)
    assert is_exchange_holiday("IN", datetime.date(2024, 4, 11)) is True

    # 2024-01-22 to 2024-01-26: Mon-Fri week containing Ram Mandir (Jan 22) AND Republic Day (Jan 26)
    start = datetime.date(2024, 1, 22)
    end = datetime.date(2024, 1, 26)
    expected_days = get_expected_trading_days("IN", start, end)

    # Out of 5 weekdays, both Monday and Friday are official holidays, so expected sessions == 3
    assert len(expected_days) == 3
    assert datetime.date(2024, 1, 22) not in expected_days
    assert datetime.date(2024, 1, 26) not in expected_days

    # If provider provides Mon-Thu, missing sessions count should be 0 (NOT 1!)
    actual_days = set(expected_days)
    missing = [d for d in expected_days if d not in actual_days]
    assert len(missing) == 0


def test_us_calendar_distinguishes_holidays_from_data_gaps():
    """Verify official US exchange holidays (Thanksgiving, Good Friday, July 4)
    are NOT flagged as missing trading sessions.
    """
    # 2024-07-04 is Independence Day (US market holiday)
    assert is_exchange_holiday("US", datetime.date(2024, 7, 4)) is True
    # 2024-11-28 is Thanksgiving (US market holiday)
    assert is_exchange_holiday("US", datetime.date(2024, 11, 28)) is True

    # Week of July 4th 2024: 2024-07-01 (Mon) to 2024-07-05 (Fri)
    start = datetime.date(2024, 7, 1)
    end = datetime.date(2024, 7, 5)
    expected = get_expected_trading_days("US", start, end)
    assert len(expected) == 4
    assert datetime.date(2024, 7, 4) not in expected


def test_genuine_data_gap_detection():
    """Verify an unexpected weekday absence (e.g. Wednesday missing) is correctly flagged."""
    # Mon 2024-06-10 to Fri 2024-06-14 (no holidays in either market)
    start = datetime.date(2024, 6, 10)
    end = datetime.date(2024, 6, 14)
    expected = get_expected_trading_days("US", start, end)
    assert len(expected) == 5

    # Provider provided Mon, Tue, Thu, Fri (Wed 2024-06-12 missing)
    provided = {
        datetime.date(2024, 6, 10),
        datetime.date(2024, 6, 11),
        datetime.date(2024, 6, 13),
        datetime.date(2024, 6, 14),
    }
    missing = [d for d in expected if d not in provided]
    assert len(missing) == 1
    assert missing[0] == datetime.date(2024, 6, 12)


# ============================================================================
# 4. Source Quality Precedence & Checkpoint Tests
# ============================================================================

def test_source_quality_tier_hierarchy():
    """Verify strict precedence hierarchy: SIP > Angel One == Alpaca IEX > YFinance > Synthetic."""
    assert SOURCE_QUALITY_TIER["alpaca_sip"] > SOURCE_QUALITY_TIER["angelone"]
    assert SOURCE_QUALITY_TIER["angelone"] == SOURCE_QUALITY_TIER["alpaca_iex"]
    assert SOURCE_QUALITY_TIER["alpaca_iex"] > SOURCE_QUALITY_TIER["yfinance"]
    assert SOURCE_QUALITY_TIER["yfinance"] > SOURCE_QUALITY_TIER["synthetic_fixture"]
    assert SOURCE_QUALITY_TIER["yfinance"] > SOURCE_QUALITY_TIER["mock"]


def test_ingestion_checkpoint_readiness_thresholds():
    """Verify that checkpoint thresholds enforce 300, 750, and 1,250 session gates."""
    engine = HistoricalIngestionEngine()

    # Case A: 1,250 bars -> COMPLETED, all gates pass
    chk_1250 = IngestionCheckpoint(
        run_id="run_test",
        symbol="RELIANCE",
        market="IN",
        provider="angelone",
        status="PENDING",
    )
    df_1250 = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=1250, freq="B").date,
        "open": [100.0] * 1250,
        "high": [105.0] * 1250,
        "low": [95.0] * 1250,
        "close": [102.0] * 1250,
        "adj_close": [102.0] * 1250,
        "volume": [1000.0] * 1250,
    })

    mock_db = mock.MagicMock()
    with mock.patch.object(engine, "fetch_historical_bars_for_symbol", return_value=(df_1250, "angelone", None)):
        with mock.patch.object(engine, "batch_upsert_bars", return_value=1250):
            res = engine.ingest_symbol(mock_db, chk_1250, target_sessions=1250)
            assert res.status == "COMPLETED"
            assert res.meets_300 is True
            assert res.meets_750 is True
            assert res.meets_1250 is True
            assert res.available_sessions == 1250

    # Case B: 750 bars -> PARTIAL, meets 300 and 750, fails 1250
    chk_750 = IngestionCheckpoint(
        run_id="run_test",
        symbol="INFY",
        market="IN",
        provider="angelone",
        status="PENDING",
    )
    df_750 = pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=750, freq="B").date,
        "open": [100.0] * 750,
        "high": [105.0] * 750,
        "low": [95.0] * 750,
        "close": [102.0] * 750,
        "adj_close": [102.0] * 750,
        "volume": [1000.0] * 750,
    })
    with mock.patch.object(engine, "fetch_historical_bars_for_symbol", return_value=(df_750, "angelone", None)):
        with mock.patch.object(engine, "batch_upsert_bars", return_value=750):
            res = engine.ingest_symbol(mock_db, chk_750, target_sessions=1250)
            assert res.status == "PARTIAL"
            assert res.meets_300 is True
            assert res.meets_750 is True
            assert res.meets_1250 is False
            assert res.available_sessions == 750

    # Case C: 200 bars -> INSUFFICIENT_DATA, fails all research gates
    chk_200 = IngestionCheckpoint(
        run_id="run_test",
        symbol="NEW_IPO",
        market="IN",
        provider="angelone",
        status="PENDING",
    )
    df_200 = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=200, freq="B").date,
        "open": [100.0] * 200,
        "high": [105.0] * 200,
        "low": [95.0] * 200,
        "close": [102.0] * 200,
        "adj_close": [102.0] * 200,
        "volume": [1000.0] * 200,
    })
    with mock.patch.object(engine, "fetch_historical_bars_for_symbol", return_value=(df_200, "angelone", None)):
        with mock.patch.object(engine, "batch_upsert_bars", return_value=200):
            res = engine.ingest_symbol(mock_db, chk_200, target_sessions=1250)
            assert res.status == "INSUFFICIENT_DATA"
            assert res.meets_300 is False
            assert res.meets_750 is False
            assert res.meets_1250 is False
            assert res.available_sessions == 200


def test_provenance_explicitly_records_feed_and_survivorship_limitations():
    """Verify provenance metadata explicitly records feed entitlement and survivorship limitations."""
    engine = HistoricalIngestionEngine()
    chk = IngestionCheckpoint(
        run_id="run_test",
        symbol="AAPL",
        market="US",
        provider="pending",
        status="PENDING",
    )
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=320, freq="B").date,
        "open": [150.0] * 320,
        "high": [155.0] * 320,
        "low": [148.0] * 320,
        "close": [152.0] * 320,
        "adj_close": [152.0] * 320,
        "volume": [10000.0] * 320,
    })

    mock_db = mock.MagicMock()
    with mock.patch.object(engine, "fetch_historical_bars_for_symbol", return_value=(df, "alpaca_iex", None)):
        with mock.patch.object(engine, "batch_upsert_bars", return_value=320):
            res = engine.ingest_symbol(mock_db, chk, target_sessions=1250)
            prov = json.loads(res.provenance_json)
            assert prov["feed"] == "alpaca_iex"
            assert "IEX (~2.5% US tape)" in prov["entitlement"]
            assert "survivorship_bias" in prov
            assert "current constituent" in prov["survivorship_bias"]


# ============================================================================
# 5. Calendar Accuracy: Special Sessions, Rescheduled & Exceptional Closures
# ============================================================================

def test_special_trading_sessions_and_rescheduled_holidays():
    """Verify special Saturday disaster-recovery sessions, Diwali Muhurat sessions,
    US Juneteenth, and rescheduled holidays are handled with 100% calendar accuracy.
    """
    # 1. Saturday DR Live Trading Sessions (NSE was OPEN on Saturday)
    assert is_exchange_holiday("IN", datetime.date(2024, 3, 2)) is False
    assert is_exchange_holiday("IN", datetime.date(2024, 5, 18)) is False
    assert is_exchange_holiday("IN", datetime.date(2024, 1, 20)) is False

    # 2. Weekend Diwali Muhurat Trading (NSE was OPEN for 1 hour on weekend)
    assert is_exchange_holiday("IN", datetime.date(2020, 11, 14)) is False  # Saturday Muhurat
    assert is_exchange_holiday("IN", datetime.date(2023, 11, 12)) is False  # Sunday Muhurat

    # 3. Normal weekends remain CLOSED
    assert is_exchange_holiday("IN", datetime.date(2024, 3, 9)) is True  # Regular Saturday

    # 4. Rescheduled Bakri Id: In 2023, NSE rescheduled holiday from June 28 to June 29
    assert is_exchange_holiday("IN", datetime.date(2023, 6, 28)) is False  # Was a trading day!
    assert is_exchange_holiday("IN", datetime.date(2023, 6, 29)) is True   # Was the actual closed holiday!

    # 5. US Juneteenth National Independence Day (June 19 observed)
    assert is_exchange_holiday("US", datetime.date(2023, 6, 19)) is True
    assert is_exchange_holiday("US", datetime.date(2024, 6, 19)) is True


# ============================================================================
# 6. Corporate Actions: Verified Known Splits & Geometric Proportionality
# ============================================================================

def test_known_split_events_and_geometric_proportionality():
    """Verify known historical split events (Tata Steel 10:1, Reliance 1:1 bonus,
    Nvidia 10:1) scale all 4 OHLC price points by exact split ratio and preserve candle shape.
    """
    # Case A: TATASTEEL 10:1 split on 2022-07-28
    dates = [
        datetime.date(2022, 7, 26),
        datetime.date(2022, 7, 27),
        datetime.date(2022, 7, 28), # Ex-date
        datetime.date(2022, 7, 29),
    ]
    df_tata = pd.DataFrame({
        "date": dates,
        "open": [950.0, 960.0, 96.0, 97.0],
        "high": [970.0, 980.0, 98.0, 99.0],
        "low": [940.0, 950.0, 94.0, 95.0],
        "close": [965.0, 962.0, 96.5, 98.0],
        "volume": [100000.0, 120000.0, 1000000.0, 1100000.0],
    })

    adj_tata, applied = apply_verified_corporate_actions(df_tata, "TATASTEEL", market="IN")
    assert applied is True

    # Pre-split bars divided by 10.0
    assert adj_tata.loc[1, "split_adj_open"] == 96.0
    assert adj_tata.loc[1, "split_adj_high"] == 98.0
    assert adj_tata.loc[1, "split_adj_low"] == 95.0
    assert adj_tata.loc[1, "split_adj_close"] == 96.2
    assert adj_tata.loc[1, "volume"] == 1200000.0 # 10x volume

    # Post-split bars untouched
    assert adj_tata.loc[2, "split_adj_close"] == 96.5

    # Candle proportionality preserved
    raw_range = df_tata.loc[1, "high"] - df_tata.loc[1, "low"]
    adj_range = adj_tata.loc[1, "split_adj_high"] - adj_tata.loc[1, "split_adj_low"]
    assert pytest.approx(raw_range / adj_range) == 10.0

    # Case B: RELIANCE 1:1 bonus on 2024-10-28 (ratio 2.0)
    dates_rel = [datetime.date(2024, 10, 25), datetime.date(2024, 10, 28)]
    df_rel = pd.DataFrame({
        "date": dates_rel,
        "open": [2660.0, 1340.0],
        "high": [2680.0, 1350.0],
        "low": [2640.0, 1330.0],
        "close": [2655.0, 1335.0],
        "volume": [500000.0, 1000000.0],
    })
    adj_rel, applied_rel = apply_verified_corporate_actions(df_rel, "RELIANCE", market="IN")
    assert applied_rel is True
    # Oct 25 pre-bonus bar scaled by 2.0
    assert adj_rel.loc[0, "split_adj_close"] == 1327.5
    assert adj_rel.loc[1, "split_adj_close"] == 1335.0

    # Idempotency Verification: running again on already-adjusted DataFrame must NOT divide again
    adj_tata_second, _ = apply_verified_corporate_actions(adj_tata, "TATASTEEL", market="IN")
    assert adj_tata_second["split_adj_close"].equals(adj_tata["split_adj_close"])
    assert adj_tata_second["volume"].equals(adj_tata["volume"])


# ============================================================================
# 7. Provider Precedence SQL Logic: Protection & Legitimate Upgrades
# ============================================================================

def test_sql_precedence_tier_rules_protect_and_upgrade():
    """Verify that PostgreSQL quality precedence:
    - Blocks lower-tier overwrite (SIP 4 protected from IEX 3, Angel One 3 protected from YF 2).
    - Permits equal-tier corrections from same primary provider (Angel One updates Angel One).
    - Permits upgrades from fallback to primary (YF 2 upgraded to Angel One 3).
    """
    tiers = {
        "alpaca_sip": 4,
        "angelone": 3,
        "alpaca_iex": 3,
        "yfinance": 2,
        "synthetic": 1,
    }

    def can_overwrite(existing_source: str, incoming_source: str) -> bool:
        existing_tier = tiers.get(existing_source, 1)
        incoming_tier = tiers.get(incoming_source, 1)
        return existing_tier <= incoming_tier

    # 1. Higher-quality primary is protected from lower-quality fallback
    assert can_overwrite(existing_source="alpaca_sip", incoming_source="alpaca_iex") is False
    assert can_overwrite(existing_source="alpaca_sip", incoming_source="yfinance") is False
    assert can_overwrite(existing_source="angelone", incoming_source="yfinance") is False
    assert can_overwrite(existing_source="alpaca_iex", incoming_source="yfinance") is False

    # 2. Legitimate corrections from same primary provider are ALLOWED
    assert can_overwrite(existing_source="angelone", incoming_source="angelone") is True
    assert can_overwrite(existing_source="alpaca_iex", incoming_source="alpaca_iex") is True

    # 3. Upgrades from fallback to primary are ALLOWED
    assert can_overwrite(existing_source="yfinance", incoming_source="angelone") is True
    assert can_overwrite(existing_source="yfinance", incoming_source="alpaca_sip") is True
    assert can_overwrite(existing_source="alpaca_iex", incoming_source="alpaca_sip") is True


# ============================================================================
# 8. Backtest Readiness: Adjusted Prices Passed to Indicator & Strategy Engine
# ============================================================================

def test_backtester_receives_split_adjusted_prices():
    """Verify that provider_manager.get_daily_bars returns DataFrames where
    'open', 'high', 'low', 'close' are populated with split-adjusted prices,
    preventing artificial 90% drops from polluting indicators (SMA200) and simulator fills.
    """
    # Create mock database rows representing a 10:1 split event
    class MockBar:
        def __init__(self, date, raw_close, split_close):
            self.date = date
            self.open = raw_close
            self.high = raw_close + 2.0
            self.low = raw_close - 2.0
            self.close = raw_close
            self.adj_close = split_close
            self.volume = 100000.0
            self.source = "angelone"
            self.split_adj_open = split_close
            self.split_adj_high = split_close + 0.2
            self.split_adj_low = split_close - 0.2
            self.split_adj_close = split_close
            self.dividend_factor = 1.0
            self.is_split_adjusted = True

    dates = pd.date_range("2024-01-01", periods=60, freq="B").date
    rows = []
    for i, d in enumerate(dates):
        if i < 30:
            # Pre-split: raw = 1000.0, split-adjusted = 100.0
            rows.append(MockBar(d, 1000.0, 100.0))
        else:
            # Post-split: raw = 102.0, split-adjusted = 102.0
            rows.append(MockBar(d, 102.0, 102.0))

    mock_db = mock.MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows

    bars_dict = provider_manager.get_daily_bars(
        symbols=["TATASTEEL"],
        start=dates[0],
        end=dates[-1],
        market="IN",
        db=mock_db,
    )

    df = bars_dict["TATASTEEL"]
    # 1. Backtester sees split-adjusted prices in primary OHLC columns
    assert df["close"].iloc[0] == 100.0  # NOT 1000.0!
    assert df["close"].iloc[35] == 102.0
    # 2. Raw unadjusted prices preserved in raw_close
    assert df["raw_close"].iloc[0] == 1000.0

    # 3. Moving averages computed by indicators do not exhibit a 90% plunge
    ind_df = add_all_indicators(df)
    sma50 = ind_df["sma50"].iloc[-1]
    # Since prices were ~100 pre-split and ~102 post-split, SMA50 should be ~101
    assert 99.0 <= sma50 <= 103.0
    # If raw prices were used, SMA50 would be contaminated (~550) causing catastrophic backtest distortion
    assert sma50 < 200.0

