import datetime
from typing import Optional
from zoneinfo import ZoneInfo
import pandas as pd
from app.engine.calendars import is_exchange_holiday, is_session_completed


class VolumePaceCalculator:
    """Calculates intraday volume pace ratio against expected time-of-day baseline
    for Indian (NSE) and US (NYSE/NASDAQ) markets, strictly respecting exchange hours,
    holidays, timezones, and daylight saving time (EST/EDT).
    """

    @staticmethod
    def get_session_parameters(market: str, asof_date: Optional[datetime.date] = None):
        from app.engine.calendars import get_session_hours
        m = market.upper()
        start_t, end_t, total_mins = get_session_hours(m, asof_date)
        if m in ("IN", "NSE"):
            tz = ZoneInfo("Asia/Kolkata")
        elif m == "US":
            tz = ZoneInfo("America/New_York")
        else:
            tz = ZoneInfo("UTC")

        return {
            "tz": tz,
            "start_hour": start_t.hour,
            "start_minute": start_t.minute,
            "end_hour": end_t.hour,
            "end_minute": end_t.minute,
            "total_minutes": total_mins,
        }

    @classmethod
    def calculate_baseline_avg_volume(
        cls,
        df_daily: pd.DataFrame,
        market: str = "IN",
        asof_dt: Optional[datetime.datetime] = None,
        lookback_bars: int = 20,
    ) -> Optional[float]:
        """Calculates historical average volume strictly excluding any uncompleted/in-progress daily bar,
        and excluding anomalous short Muhurat sessions from normal baseline."""
        if df_daily is None or df_daily.empty or "volume" not in df_daily.columns:
            return None

        now_utc = asof_dt or datetime.datetime.now(datetime.timezone.utc)
        tz = ZoneInfo("Asia/Kolkata") if market.upper() in ("IN", "NSE") else ZoneInfo("America/New_York")
        local_now = now_utc.astimezone(tz)
        today_local = local_now.date()

        # Check if the latest row represents today's in-progress session
        df = df_daily.copy()
        last_date: Optional[datetime.date] = None
        if isinstance(df.index, pd.DatetimeIndex):
            last_date = df.index[-1].date()
        elif "date" in df.columns:
            val = df["date"].iloc[-1]
            last_date = val.date() if isinstance(val, (datetime.datetime, pd.Timestamp)) else datetime.date.fromisoformat(str(val)[:10])

        if last_date == today_local and not is_session_completed(market, now_utc):
            # Exclude today's incomplete candle
            df = df.iloc[:-1]

        # Exclude Diwali Muhurat sessions from standard 375-min average daily volume
        from app.engine.calendars import NSE_MUHURAT_SESSIONS
        if market.upper() in ("IN", "NSE") and "date" in df.columns:
            df = df[~df["date"].apply(lambda d: (d.date() if isinstance(d, (datetime.datetime, pd.Timestamp)) else d) in NSE_MUHURAT_SESSIONS)]

        if len(df) < lookback_bars:
            return None

        vol_series = df["volume"].iloc[-lookback_bars:]
        valid_vols = vol_series.dropna()
        if len(valid_vols) < lookback_bars or (valid_vols <= 0).any():
            return None

        return float(valid_vols.mean())

    @classmethod
    def calculate_volume_pace(
        cls,
        symbol: str,
        avg_volume_20d: Optional[float],
        current_day_volume: Optional[float],
        market: str = "IN",
        current_time: Optional[datetime.datetime] = None,
    ) -> Optional[float]:
        """Calculates volume pace ratio against expected time-of-day baseline.
        Returns:
            - float: pace ratio (e.g. 1.25 for 125% of expected baseline)
            - None: if outside market hours, holiday, or if baseline volume is invalid (Rule 6 & 11)
        """
        if avg_volume_20d is None or avg_volume_20d <= 0:
            return None

        now_utc = current_time or datetime.datetime.now(datetime.timezone.utc)
        tz = ZoneInfo("Asia/Kolkata") if market.upper() in ("IN", "NSE") else ZoneInfo("America/New_York")
        local_now = now_utc.astimezone(tz)
        today_local = local_now.date()
        params = cls.get_session_parameters(market, today_local)

        # Closed on holidays or weekends
        if is_exchange_holiday(market, today_local):
            return None

        start_min = params["start_hour"] * 60 + params["start_minute"]
        end_min = params["end_hour"] * 60 + params["end_minute"]
        cur_min = local_now.hour * 60 + local_now.minute

        # Before market open: pace is undefined
        if cur_min < start_min:
            return None

        # Clamp elapsed minutes between 5 and total session minutes
        total_session = params["total_minutes"]
        elapsed_min = max(5, min(int(total_session), cur_min - start_min))

        expected_fraction = elapsed_min / total_session
        expected_vol = avg_volume_20d * expected_fraction
        if expected_vol <= 0:
            return None

        actual_vol = float(current_day_volume) if current_day_volume is not None and current_day_volume > 0 else 0.0
        return round(actual_vol / expected_vol, 3)
