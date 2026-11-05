import datetime
from typing import List, Set
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    USFederalHolidayCalendar,
    GoodFriday,
    nearest_workday,
)


class USEchangeCalendar(AbstractHolidayCalendar):
    """NYSE / NASDAQ Trading Holidays (US Federal Holidays + Good Friday)."""
    rules = USFederalHolidayCalendar.rules + [GoodFriday]


# Precompute US exchange holidays 2020 - 2030
_us_cal = USEchangeCalendar()
_us_holidays_series = _us_cal.holidays(start="2020-01-01", end="2030-12-31")
US_EXCHANGE_HOLIDAYS: Set[datetime.date] = set(_us_holidays_series.date)

# Official NSE (National Stock Exchange of India) Trading Holidays (2020 - 2027)
# Compiled from official NSE circulars and exchange trading schedules
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
    datetime.date(2021, 10, 15),  # Dussehra
    datetime.date(2021, 11, 5),   # Diwali Balipratipada
    datetime.date(2021, 11, 19),  # Gurunanak Jayanti
    # 2022
    datetime.date(2022, 1, 26),   # Republic Day
    datetime.date(2022, 3, 1),    # Mahashivratri
    datetime.date(2022, 3, 18),   # Holi
    datetime.date(2022, 4, 14),   # Dr. Ambedkar Jayanti / Mahavir Jayanti
    datetime.date(2022, 4, 15),   # Good Friday
    datetime.date(2022, 5, 3),    # Id-Ul-Fitr
    datetime.date(2022, 8, 9),    # Muharram
    datetime.date(2022, 8, 15),   # Independence Day
    datetime.date(2022, 8, 31),   # Ganesh Chaturthi
    datetime.date(2022, 10, 5),   # Dussehra
    datetime.date(2022, 10, 24),  # Diwali (Laxmi Pujan)
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
    datetime.date(2023, 6, 29),   # Bakri Id
    datetime.date(2023, 8, 15),   # Independence Day
    datetime.date(2023, 9, 19),   # Ganesh Chaturthi
    datetime.date(2023, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2023, 10, 24),  # Dussehra
    datetime.date(2023, 11, 14),  # Diwali Balipratipada
    datetime.date(2023, 11, 27),  # Gurunanak Jayanti
    datetime.date(2023, 12, 25),  # Christmas
    # 2024
    datetime.date(2024, 1, 22),   # Special Holiday
    datetime.date(2024, 1, 26),   # Republic Day
    datetime.date(2024, 3, 8),    # Mahashivratri
    datetime.date(2024, 3, 25),   # Holi
    datetime.date(2024, 3, 29),   # Good Friday
    datetime.date(2024, 4, 11),   # Id-Ul-Fitr
    datetime.date(2024, 4, 17),   # Ram Navami
    datetime.date(2024, 5, 1),    # Maharashtra Day
    datetime.date(2024, 5, 20),   # Parliamentary Elections (Mumbai)
    datetime.date(2024, 6, 17),   # Bakri Id
    datetime.date(2024, 7, 17),   # Muharram
    datetime.date(2024, 8, 15),   # Independence Day
    datetime.date(2024, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2024, 11, 1),   # Diwali Laxmi Pujan
    datetime.date(2024, 11, 15),  # Gurunanak Jayanti
    datetime.date(2024, 11, 20),  # Maharashtra Assembly Elections
    datetime.date(2024, 12, 25),  # Christmas
    # 2025
    datetime.date(2025, 2, 26),   # Mahashivratri
    datetime.date(2025, 3, 14),   # Holi
    datetime.date(2025, 3, 31),   # Id-Ul-Fitr
    datetime.date(2025, 4, 10),   # Mahavir Jayanti
    datetime.date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2025, 4, 18),   # Good Friday
    datetime.date(2025, 5, 1),    # Maharashtra Day
    datetime.date(2025, 6, 6),    # Bakri Id
    datetime.date(2025, 8, 15),   # Independence Day
    datetime.date(2025, 8, 27),   # Ganesh Chaturthi
    datetime.date(2025, 10, 2),   # Mahatma Gandhi Jayanti / Dussehra
    datetime.date(2025, 10, 21),  # Diwali (Laxmi Pujan)
    datetime.date(2025, 10, 22),  # Diwali Balipratipada
    datetime.date(2025, 11, 5),   # Gurunanak Jayanti
    datetime.date(2025, 12, 25),  # Christmas
    # 2026
    datetime.date(2026, 1, 26),   # Republic Day
    datetime.date(2026, 2, 16),   # Mahashivratri
    datetime.date(2026, 3, 3),    # Holi
    datetime.date(2026, 3, 20),   # Id-Ul-Fitr
    datetime.date(2026, 3, 31),   # Mahavir Jayanti
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    datetime.date(2026, 5, 1),    # Maharashtra Day
    datetime.date(2026, 5, 27),   # Bakri Id
    datetime.date(2026, 6, 26),   # Muharram
    datetime.date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    datetime.date(2026, 10, 20),  # Dussehra
    datetime.date(2026, 11, 10),  # Diwali Balipratipada
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


def is_exchange_holiday(market: str, d: datetime.date) -> bool:
    """Returns True if date is an official exchange holiday for the specified market."""
    # Weekends are market closures
    if d.weekday() >= 5:
        return True
    m = market.upper()
    if m == "US":
        return d in US_EXCHANGE_HOLIDAYS
    return d in NSE_TRADING_HOLIDAYS


def get_expected_trading_days(market: str, start_date: datetime.date, end_date: datetime.date) -> List[datetime.date]:
    """Returns all expected open trading sessions between start and end date (inclusive)."""
    if start_date > end_date:
        return []
    b_days = pd.bdate_range(start_date, end_date)
    return [d.date() for d in b_days if not is_exchange_holiday(market, d.date())]

