import datetime
from zoneinfo import ZoneInfo
import pytest

from app.engine.calendars import (
    NSE_MUHURAT_SESSIONS,
    US_EARLY_CLOSE_DAYS,
    get_completed_sessions_held_count,
    get_expected_trading_days,
    get_session_hours,
    is_exchange_holiday,
    is_market_open,
    is_session_completed,
)
from app.engine.volume_pace import VolumePaceCalculator


def test_nse_2026_holidays_and_muhurat():
    """Verify official 2026 NSE holiday schedule and special Muhurat session."""
    # 1. Jan 15, 2026 - Maharashtra Municipal Corporation Election trading holiday
    assert is_exchange_holiday("IN", datetime.date(2026, 1, 15)) is True

    # 2. Mar 31, 2026 - Shri Mahavir Jayanti official trading holiday
    assert is_exchange_holiday("IN", datetime.date(2026, 3, 31)) is True

    # 3. Nov 8, 2026 - Sunday Diwali Muhurat Trading
    # Exchange is NOT closed (special session open for trading)
    assert is_exchange_holiday("IN", datetime.date(2026, 1, 15)) is True
    assert is_exchange_holiday("IN", datetime.date(2026, 11, 8)) is False

    # 4. Muhurat session is explicitly 60 minutes (18:15 - 19:15 IST), NOT 375 minutes!
    start_t, end_t, total_mins = get_session_hours("IN", datetime.date(2026, 11, 8))
    assert start_t == datetime.time(18, 15)
    assert end_t == datetime.time(19, 15)
    assert total_mins == 60.0

    # Normal session hours are 09:15 - 15:30 (375 minutes)
    norm_start, norm_end, norm_mins = get_session_hours("IN", datetime.date(2026, 11, 9))
    assert norm_start == datetime.time(9, 15)
    assert norm_end == datetime.time(15, 30)
    assert norm_mins == 375.0


def test_nse_muhurat_intraday_boundaries():
    """Test market open and session completion around Muhurat trading boundaries."""
    tz_in = ZoneInfo("Asia/Kolkata")
    muhurat_d = datetime.date(2026, 11, 8)

    # Daytime (10:00 IST): exchange is NOT open
    day_time = datetime.datetime(2026, 11, 8, 10, 0, tzinfo=tz_in)
    assert is_market_open("IN", day_time) is False
    assert is_session_completed("IN", day_time) is False

    # Evening before Muhurat (18:14 IST): NOT open, NOT completed
    pre_muhurat = datetime.datetime(2026, 11, 8, 18, 14, tzinfo=tz_in)
    assert is_market_open("IN", pre_muhurat) is False
    assert is_session_completed("IN", pre_muhurat) is False

    # During Muhurat (18:30 IST): OPEN, NOT completed
    during_muhurat = datetime.datetime(2026, 11, 8, 18, 30, tzinfo=tz_in)
    assert is_market_open("IN", during_muhurat) is True
    assert is_session_completed("IN", during_muhurat) is False

    # One minute before close (19:14 IST): OPEN, NOT completed
    almost_done = datetime.datetime(2026, 11, 8, 19, 14, tzinfo=tz_in)
    assert is_market_open("IN", almost_done) is True
    assert is_session_completed("IN", almost_done) is False

    # Exactly at close (19:15 IST): COMPLETED
    at_close = datetime.datetime(2026, 11, 8, 19, 15, tzinfo=tz_in)
    assert is_session_completed("IN", at_close) is True


def test_us_2026_thanksgiving_black_friday_christmas():
    """Verify official NYSE/NASDAQ closures and early close schedule."""
    # Thanksgiving: Thursday Nov 26, 2026 -> CLOSED
    assert is_exchange_holiday("US", datetime.date(2026, 11, 26)) is True

    # Christmas Day: Friday Dec 25, 2026 -> CLOSED
    assert is_exchange_holiday("US", datetime.date(2026, 12, 25)) is True

    # Black Friday: Friday Nov 27, 2026 -> OPEN with Early Close at 13:00 ET
    assert is_exchange_holiday("US", datetime.date(2026, 11, 27)) is False
    assert datetime.date(2026, 11, 27) in US_EARLY_CLOSE_DAYS
    start_t, end_t, mins = get_session_hours("US", datetime.date(2026, 11, 27))
    assert start_t == datetime.time(9, 30)
    assert end_t == datetime.time(13, 0)
    assert mins == 210.0

    # Christmas Eve: Thursday Dec 24, 2026 -> OPEN with Early Close at 13:00 ET
    assert is_exchange_holiday("US", datetime.date(2026, 12, 24)) is False
    assert datetime.date(2026, 12, 24) in US_EARLY_CLOSE_DAYS
    start_t2, end_t2, mins2 = get_session_hours("US", datetime.date(2026, 12, 24))
    assert start_t2 == datetime.time(9, 30)
    assert end_t2 == datetime.time(13, 0)
    assert mins2 == 210.0


def test_us_early_close_exact_minute_boundaries():
    """Test 1 minute before and exactly at early close (13:00 ET)."""
    tz_us = ZoneInfo("America/New_York")
    early_d = datetime.date(2026, 11, 27)

    # 1. 09:29 ET: Pre-market -> open=False, completed=False
    t_0929 = datetime.datetime(2026, 11, 27, 9, 29, tzinfo=tz_us)
    assert is_market_open("US", t_0929) is False
    assert is_session_completed("US", t_0929) is False

    # 2. 09:30 ET: Market Open -> open=True, completed=False
    t_0930 = datetime.datetime(2026, 11, 27, 9, 30, tzinfo=tz_us)
    assert is_market_open("US", t_0930) is True
    assert is_session_completed("US", t_0930) is False

    # 3. 12:59 ET (one minute before early close) -> open=True, completed=False
    t_1259 = datetime.datetime(2026, 11, 27, 12, 59, tzinfo=tz_us)
    assert is_market_open("US", t_1259) is True
    assert is_session_completed("US", t_1259) is False

    # 4. 13:00 ET (at early close) -> open=True, completed=True
    t_1300 = datetime.datetime(2026, 11, 27, 13, 0, tzinfo=tz_us)
    assert is_session_completed("US", t_1300) is True

    # 5. 13:01 ET (post-close) -> open=False, completed=True
    t_1301 = datetime.datetime(2026, 11, 27, 13, 1, tzinfo=tz_us)
    assert is_market_open("US", t_1301) is False
    assert is_session_completed("US", t_1301) is True


def test_volume_pace_uses_actual_scheduled_session_length():
    """Verify volume pace calculates against 210 minutes on US early-close days vs 390 on normal days."""
    tz_us = ZoneInfo("America/New_York")

    # Early close: Nov 27, 2026 at 11:15 ET (105 elapsed minutes out of 210 -> exactly 50%)
    dt_early = datetime.datetime(2026, 11, 27, 11, 15, tzinfo=tz_us)
    pace_params_early = VolumePaceCalculator.get_session_parameters("US", dt_early.date())
    assert pace_params_early["total_minutes"] == 210.0
    assert pace_params_early["end_hour"] == 13

    # Normal day: Nov 25, 2026 at 11:15 ET (105 elapsed minutes out of 390 -> 26.9%)
    dt_normal = datetime.datetime(2026, 11, 25, 11, 15, tzinfo=tz_us)
    pace_params_norm = VolumePaceCalculator.get_session_parameters("US", dt_normal.date())
    assert pace_params_norm["total_minutes"] == 390.0
    assert pace_params_norm["end_hour"] == 16

    # Verify pace output difference
    pace_early = VolumePaceCalculator.calculate_volume_pace(
        symbol="AAPL",
        avg_volume_20d=1_000_000.0,
        current_day_volume=500_000.0,  # 500k at 50% through session
        market="US",
        current_time=dt_early,
    )
    # Expected: 500k / (1M * (105/210)) = 500k / 500k = 1.00x!
    assert pace_early == 1.0

    pace_norm = VolumePaceCalculator.calculate_volume_pace(
        symbol="AAPL",
        avg_volume_20d=1_000_000.0,
        current_day_volume=500_000.0,
        market="US",
        current_time=dt_normal,
    )
    # Expected: 500k / (1M * (105/390)) = 500k / 269.2k = ~1.857x
    assert pace_norm == 1.857


def test_completed_sessions_held_count_around_holidays_and_early_close():
    """Verify time-stop holding count correctly handles holiday + early close boundaries."""
    tz_us = ZoneInfo("America/New_York")
    # Entry on Wednesday Nov 25, 2026
    entry_d = datetime.date(2026, 11, 25)

    # 1. Nov 25 intraday & post-close: 0 completed post-entry sessions
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 25, 12, 0, tzinfo=tz_us)) == 0
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 25, 16, 5, tzinfo=tz_us)) == 0

    # 2. Nov 26 (Thanksgiving - holiday): still 0 completed post-entry sessions
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 26, 14, 0, tzinfo=tz_us)) == 0

    # 3. Nov 27 (Early Close):
    # - 12:59 ET (before early close): still 0 completed sessions
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 27, 12, 59, tzinfo=tz_us)) == 0
    # - 13:00 ET (at early close): exactly 1 completed session!
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 27, 13, 0, tzinfo=tz_us)) == 1
    # - 16:00 ET: still 1 completed session
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 27, 16, 0, tzinfo=tz_us)) == 1

    # 4. Weekend (Saturday Nov 28): still 1 completed session
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 28, 12, 0, tzinfo=tz_us)) == 1

    # 5. Monday Nov 30 after close: exactly 2 completed sessions!
    assert get_completed_sessions_held_count("US", entry_d, datetime.datetime(2026, 11, 30, 16, 5, tzinfo=tz_us)) == 2
