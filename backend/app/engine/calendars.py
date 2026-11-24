import datetime
from typing import List, Set, Optional
from zoneinfo import ZoneInfo
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    USFederalHolidayCalendar,
    GoodFriday,
    nearest_workday,
)

# Explicit Juneteenth rule for US Exchanges (NYSE/NASDAQ observed starting 2022)
Juneteenth = Holiday(
    "Juneteenth National Independence Day",
    month=6,
    day=19,
    start_date="2021-06-18",
    observance=nearest_workday,
)


class USExchangeCalendar(AbstractHolidayCalendar):
    """NYSE / NASDAQ Trading Holidays (US Federal Holidays excluding Columbus Day and Veterans Day, plus Good Friday)."""
    rules = [
        r for r in USFederalHolidayCalendar.rules
        if r.name not in ("Columbus Day", "Veterans Day")
    ]
    # Ensure Good Friday is present (not a US federal holiday, but closed on NYSE/NASDAQ)
    if not any(r.name == "Good Friday" for r in rules):
        rules.append(GoodFriday)


# Precompute US exchange holidays 2020 - 2030
_us_cal = USExchangeCalendar()
_us_holidays_series = _us_cal.holidays(start="2020-01-01", end="2030-12-31")
US_EXCHANGE_HOLIDAYS: Set[datetime.date] = set(_us_holidays_series.date)
# Special National Days of Mourning (exchanges officially closed)
US_EXCHANGE_HOLIDAYS.add(datetime.date(2025, 1, 9))  # President Jimmy Carter National Day of Mourning

# Official NSE (National Stock Exchange of India) Trading Holidays (2020 - 2027)
# Compiled from official NSE circulars, amended schedules, and exchange holiday lists.
NSE_TRADING_HOLIDAYS: Set[datetime.date] = {
    # 2020
    datetime.date(2020, 2, 21),   # Mahashivratri
    datetime.date(2020, 3, 10),   # Holi
    datetime.date(2020, 4, 2),    # Ram Navami
    datetime.date(2020, 4, 6),    # Mahavir Jayanti
    datetime.date(2020, 4, 10),   # Good Friday
    datetime.date(2020, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2020, 5, 1),    # Maharashtra Day
    datetime.date(2020, 5, 25),   # Id-Ul-Fitr
    datetime.date(2020, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2020, 11, 16),  # Diwali Balipratipada
    datetime.date(2020, 11, 30),  # Gurunanak Jayanti
    datetime.date(2020, 12, 25),  # Christmas
    # 2021
    datetime.date(2021, 1, 26),   # Republic Day
    datetime.date(2021, 3, 11),   # Mahashivratri
    datetime.date(2021, 3, 29),   # Holi
    datetime.date(2021, 4, 2),    # Good Friday
    datetime.date(2021, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2021, 4, 21),   # Ram Navami
    datetime.date(2021, 5, 13),   # Id-Ul-Fitr
    datetime.date(2021, 7, 21),   # Bakri Id
    datetime.date(2021, 8, 19),   # Muharram
    datetime.date(2021, 9, 10),   # Ganesh Chaturthi
    datetime.date(2021, 10, 15),  # Dussehra
    datetime.date(2021, 11, 5),   # Diwali Balipratipada
    datetime.date(2021, 11, 19),  # Gurunanak Jayanti
    # 2022
    datetime.date(2022, 1, 26),   # Republic Day
    datetime.date(2022, 3, 1),    # Mahashivratri
    datetime.date(2022, 3, 18),   # Holi
    datetime.date(2022, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2022, 4, 15),   # Good Friday
    datetime.date(2022, 5, 3),    # Id-Ul-Fitr
    datetime.date(2022, 8, 9),    # Muharram
    datetime.date(2022, 8, 15),   # Independence Day
    datetime.date(2022, 8, 31),   # Ganesh Chaturthi
    datetime.date(2022, 10, 5),   # Dussehra
    datetime.date(2022, 10, 26),  # Diwali Balipratipada
    datetime.date(2022, 11, 8),   # Gurunanak Jayanti
    # 2023
    datetime.date(2023, 1, 26),   # Republic Day
    datetime.date(2023, 3, 7),    # Holi
    datetime.date(2023, 3, 30),   # Ram Navami
    datetime.date(2023, 4, 4),    # Mahavir Jayanti
    datetime.date(2023, 4, 7),    # Good Friday
    datetime.date(2023, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2023, 5, 1),    # Maharashtra Day
    datetime.date(2023, 6, 29),   # Bakri Id (Rescheduled from June 28 via NSE Circular 67/2023)
    datetime.date(2023, 8, 15),   # Independence Day
    datetime.date(2023, 9, 19),   # Ganesh Chaturthi
    datetime.date(2023, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2023, 10, 24),  # Dussehra
    datetime.date(2023, 11, 14),  # Diwali Balipratipada
    datetime.date(2023, 11, 27),  # Gurunanak Jayanti
    datetime.date(2023, 12, 25),  # Christmas
    # 2024
    datetime.date(2024, 1, 22),   # Special Holiday (Ayodhya Ram Mandir; trading held Sat Jan 20)
    datetime.date(2024, 1, 26),   # Republic Day
    datetime.date(2024, 3, 8),    # Mahashivratri
    datetime.date(2024, 3, 25),   # Holi
    datetime.date(2024, 3, 29),   # Good Friday
    datetime.date(2024, 4, 11),   # Id-Ul-Fitr
    datetime.date(2024, 4, 17),   # Ram Navami
    datetime.date(2024, 5, 1),    # Maharashtra Day
    datetime.date(2024, 5, 20),   # Parliamentary Elections (Mumbai Constituency)
    datetime.date(2024, 6, 17),   # Bakri Id
    datetime.date(2024, 7, 17),   # Muharram
    datetime.date(2024, 8, 15),   # Independence Day
    datetime.date(2024, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2024, 11, 15),  # Gurunanak Jayanti
    datetime.date(2024, 11, 20),  # Maharashtra State Assembly Election
    datetime.date(2024, 12, 25),  # Christmas
    # 2025
    datetime.date(2025, 2, 26),   # Mahashivratri
    datetime.date(2025, 3, 14),   # Holi
    datetime.date(2025, 3, 31),   # Id-Ul-Fitr
    datetime.date(2025, 4, 10),   # Mahavir Jayanti
    datetime.date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2025, 4, 18),   # Good Friday
    datetime.date(2025, 5, 1),    # Maharashtra Day
    datetime.date(2025, 8, 15),   # Independence Day
    datetime.date(2025, 8, 27),   # Ganesh Chaturthi
    datetime.date(2025, 10, 2),   # Mahatma Gandhi Jayanti / Dussehra
    datetime.date(2025, 10, 22),  # Diwali Balipratipada
    datetime.date(2025, 11, 5),   # Gurunanak Jayanti
    datetime.date(2025, 12, 25),  # Christmas
    # 2026
    datetime.date(2026, 1, 15),   # Maharashtra Municipal Corporation Election
    datetime.date(2026, 1, 26),   # Republic Day
    datetime.date(2026, 2, 16),   # Mahashivratri
    datetime.date(2026, 3, 3),    # Holi
    datetime.date(2026, 3, 20),   # Id-Ul-Fitr
    datetime.date(2026, 3, 26),   # Ram Navami
    datetime.date(2026, 3, 31),   # Shri Mahavir Jayanti (Official NSE Holiday)
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2026, 5, 1),    # Maharashtra Day
    datetime.date(2026, 5, 28),   # Bakri Id
    datetime.date(2026, 6, 26),   # Muharram
    datetime.date(2026, 9, 14),   # Milad-un-Nabi
    datetime.date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2026, 10, 20),  # Dussehra
    datetime.date(2026, 11, 24),  # Gurunanak Jayanti
    datetime.date(2026, 12, 25),  # Christmas
    # 2027
    datetime.date(2027, 1, 26),   # Republic Day
    datetime.date(2027, 3, 8),    # Mahashivratri
    datetime.date(2027, 3, 22),   # Holi
    datetime.date(2027, 3, 26),   # Good Friday
    datetime.date(2027, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2027, 4, 19),   # Mahavir Jayanti
    datetime.date(2027, 8, 16),   # Independence Day observed
    datetime.date(2027, 10, 29),  # Diwali
    datetime.date(2027, 12, 25),  # Christmas
}

# Special Trading Sessions (dates when exchange was OPEN despite being a weekend or holiday):
# Includes Saturday DR switchover live trading sessions and 1-hour evening Diwali Muhurat sessions.
NSE_SPECIAL_TRADING_SESSIONS: Set[datetime.date] = {
    # Special Saturday Sessions (Disaster Recovery site drills / rescheduled live trading)
    datetime.date(2024, 1, 20),  # Saturday live trading session (swapped for Jan 22 Ram Mandir holiday)
    datetime.date(2024, 3, 2),   # Saturday live DR drill session
    datetime.date(2024, 5, 18),  # Saturday live DR drill session
    # Diwali Muhurat Trading Sessions (1-hour evening trading session, candles generated by broker)
    datetime.date(2020, 11, 14), # Saturday Diwali Muhurat
    datetime.date(2021, 11, 4),  # Thursday Diwali Muhurat
    datetime.date(2022, 10, 24), # Monday Diwali Muhurat
    datetime.date(2023, 11, 12), # Sunday Diwali Muhurat
    datetime.date(2024, 11, 1),  # Friday Diwali Muhurat
    datetime.date(2025, 10, 21), # Tuesday Diwali Muhurat
    datetime.date(2026, 11, 8),  # Sunday Diwali Muhurat
}

# Explicit Diwali Muhurat Sessions (60-minute special evening session: 18:15 - 19:15 IST)
# These sessions must NEVER be treated as normal 375-minute sessions.
NSE_MUHURAT_SESSIONS: Set[datetime.date] = {
    datetime.date(2020, 11, 14),
    datetime.date(2021, 11, 4),
    datetime.date(2022, 10, 24),
    datetime.date(2023, 11, 12),
    datetime.date(2024, 11, 1),
    datetime.date(2025, 10, 21),
    datetime.date(2026, 11, 8),
}

# US Equity Market (NYSE / NASDAQ) Early Close Days (closes at 13:00 ET / 210 session minutes)
US_EARLY_CLOSE_DAYS: Set[datetime.date] = {
    datetime.date(2020, 11, 27), # Black Friday
    datetime.date(2020, 12, 24), # Christmas Eve
    datetime.date(2021, 11, 26), # Black Friday
    datetime.date(2022, 11, 25), # Black Friday
    datetime.date(2023, 7, 3),   # Pre-Independence Day
    datetime.date(2023, 11, 24), # Black Friday
    datetime.date(2024, 7, 3),   # Pre-Independence Day
    datetime.date(2024, 11, 29), # Black Friday
    datetime.date(2024, 12, 24), # Christmas Eve
    datetime.date(2025, 7, 3),   # Pre-Independence Day
    datetime.date(2025, 11, 28), # Black Friday
    datetime.date(2025, 12, 24), # Christmas Eve
    datetime.date(2026, 11, 27), # Friday after Thanksgiving
    datetime.date(2026, 12, 24), # Christmas Eve
    datetime.date(2027, 11, 26), # Friday after Thanksgiving
}


def get_session_hours(market: str, d: Optional[datetime.date] = None):
    """Returns (start_time, end_time, total_minutes) for the given market and date.
    Strictly accounts for:
    - US Early Closes (13:00 ET / 210 minutes)
    - NSE Diwali Muhurat Sessions (18:15 - 19:15 IST / 60 minutes)
    - Normal Indian Equity Market (09:15 - 15:30 IST / 375 minutes)
    - Normal US Equity Market (09:30 - 16:00 ET / 390 minutes)
    """
    m = market.upper()
    target_d = d or datetime.date.today()
    if m in ("IN", "NSE"):
        if target_d in NSE_MUHURAT_SESSIONS:
            return datetime.time(18, 15), datetime.time(19, 15), 60.0
        return datetime.time(9, 15), datetime.time(15, 30), 375.0
    elif m == "US":
        if target_d in US_EARLY_CLOSE_DAYS:
            return datetime.time(9, 30), datetime.time(13, 0), 210.0
        return datetime.time(9, 30), datetime.time(16, 0), 390.0
    return datetime.time(9, 30), datetime.time(16, 0), 390.0


def is_exchange_holiday(market: str, d: datetime.date) -> bool:
    """Returns True if date is a complete exchange closure for the specified market."""
    m = market.upper()
    if m in ("IN", "NSE"):
        # If it is a special trading session (Muhurat or Saturday DR), the market was OPEN
        if d in NSE_SPECIAL_TRADING_SESSIONS:
            return False
        # Weekends without special trading sessions are closed
        if d.weekday() >= 5:
            return True
        # Official full NSE holiday
        return d in NSE_TRADING_HOLIDAYS
    elif m == "US":
        if d.weekday() >= 5:
            return True
        return d in US_EXCHANGE_HOLIDAYS
    return d.weekday() >= 5


def get_expected_trading_days(market: str, start_date: datetime.date, end_date: datetime.date) -> List[datetime.date]:
    """Returns all expected open trading sessions between start and end date (inclusive),
    accounting for special sessions, disaster recovery drills, and exchange-specific closures.
    """
    if start_date > end_date:
        return []

    m = market.upper()
    # Generate full calendar day range to capture weekend special sessions
    all_days = pd.date_range(start_date, end_date).date
    open_sessions = [d for d in all_days if not is_exchange_holiday(m, d)]
    return sorted(open_sessions)


def get_trading_days_count(market: str, start_date: datetime.date, end_date: datetime.date) -> int:
    """Returns the total number of expected open trading sessions between start and end date."""
    return len(get_expected_trading_days(market, start_date, end_date))


def is_market_open(market: str, now: Optional[datetime.datetime] = None) -> bool:
    """Returns True if the specified market is currently in active trading hours.
    Uses Asia/Kolkata for IN and America/New_York for US,
    strictly accounting for exchange holidays, early closes, and Muhurat sessions.
    """
    m = market.upper()
    now_utc = now or datetime.datetime.now(datetime.timezone.utc)
    if m in ("IN", "NSE"):
        tz = ZoneInfo("Asia/Kolkata")
        now_local = now_utc.astimezone(tz)
        today = now_local.date()
        if is_exchange_holiday("IN", today):
            return False
        start_t, end_t, _ = get_session_hours("IN", today)
        return start_t <= now_local.time() <= end_t
    elif m == "US":
        tz = ZoneInfo("America/New_York")
        now_local = now_utc.astimezone(tz)
        today = now_local.date()
        if is_exchange_holiday("US", today):
            return False
        start_t, end_t, _ = get_session_hours("US", today)
        return start_t <= now_local.time() <= end_t
    return False


def is_session_completed(market: str, now: Optional[datetime.datetime] = None) -> bool:
    """Returns True if the market trading session on now's local date has fully closed.
    Correctly recognizes early close times (13:00 ET for US, 19:15 IST for Muhurat).
    """
    m = market.upper()
    now_utc = now or datetime.datetime.now(datetime.timezone.utc)
    if m in ("IN", "NSE"):
        tz = ZoneInfo("Asia/Kolkata")
        now_local = now_utc.astimezone(tz)
        today = now_local.date()
        if is_exchange_holiday("IN", today):
            return False
        _, end_t, _ = get_session_hours("IN", today)
        return now_local.time() >= end_t
    elif m == "US":
        tz = ZoneInfo("America/New_York")
        now_local = now_utc.astimezone(tz)
        today = now_local.date()
        if is_exchange_holiday("US", today):
            return False
        _, end_t, _ = get_session_hours("US", today)
        return now_local.time() >= end_t
    return False


def get_last_completed_trading_session(market: str = "IN", now: Optional[datetime.datetime] = None) -> datetime.date:
    """Returns the date of the most recent fully completed trading session.

    Accounts for exchange closures, weekends, and early closes (Muhurat etc.).
    If the session on `now`'s local date is currently open or pre-open, returns
    the prior completed session.
    """
    m = market.upper()
    now_utc = now or datetime.datetime.now(datetime.timezone.utc)
    tz_name = "Asia/Kolkata" if m in ("IN", "NSE") else "America/New_York"
    tz = ZoneInfo(tz_name)
    now_local = now_utc.astimezone(tz)
    today = now_local.date()

    # If today was a trading day and has completed, today is the last completed session
    if not is_exchange_holiday(m, today) and is_session_completed(m, now_utc):
        return today

    # Otherwise step back day by day until finding an open trading day
    cur = today - datetime.timedelta(days=1)
    while is_exchange_holiday(m, cur):
        cur -= datetime.timedelta(days=1)
    return cur


def get_completed_sessions_held_count(
    market: str,
    entry_date: datetime.date,
    asof_dt: Optional[datetime.datetime] = None,
) -> int:
    """Counts completed exchange sessions strictly elapsed post-entry.
    - Entry session (T_entry) is Session 0.
    - On T_entry + 1 intraday: 0 completed post-entry sessions.
    - On T_entry + 1 after market close: 1 completed post-entry session.
    - Weekends, exchange holidays, and in-progress/pre-close sessions are never counted.
    """
    now_utc = asof_dt or datetime.datetime.now(datetime.timezone.utc)
    tz_name = "Asia/Kolkata" if market.upper() in ("IN", "NSE") else "America/New_York"
    local_now = now_utc.astimezone(ZoneInfo(tz_name))
    today_local = local_now.date()

    if today_local <= entry_date:
        return 0

    all_open_days = get_expected_trading_days(market, entry_date, today_local)
    post_entry_days = [d for d in all_open_days if d > entry_date]
    if not post_entry_days:
        return 0

    # If today is in post_entry_days, it only counts as completed AFTER market close
    if today_local in post_entry_days:
        if not is_session_completed(market, now_utc):
            post_entry_days.remove(today_local)

    return len(post_entry_days)

