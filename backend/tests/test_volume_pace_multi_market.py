import datetime
from zoneinfo import ZoneInfo
from unittest import mock
import pandas as pd
import pytest

from app.engine.volume_pace import VolumePaceCalculator
from app.models import Signal
from app.providers.angelone_provider import AngelOneProvider
from app.providers.base import Quote
from app.scheduler.monitor import LiveBreakoutMonitor


def test_volume_pace_excludes_in_progress_today_candle():
    """Verify that when today's market is open, today's incomplete candle is excluded from 20-day baseline."""
    dates = pd.date_range("2024-10-01", periods=21, freq="B")
    # First 20 completed days have volume 1,000,000; today's partial day has volume 50,000
    vols = [1_000_000.0] * 20 + [50_000.0]
    df = pd.DataFrame({"volume": vols, "date": dates}, index=dates)

    tz_in = ZoneInfo("Asia/Kolkata")
    # In-session on day 21 at 11:00 AM IST
    now_dt = datetime.datetime.combine(dates[-1].date(), datetime.time(11, 0), tzinfo=tz_in)

    baseline = VolumePaceCalculator.calculate_baseline_avg_volume(
        df_daily=df,
        market="IN",
        asof_dt=now_dt,
        lookback_bars=20,
    )
    # Baseline must be 1,000,000 (excluding today's incomplete 50,000)
    assert baseline == 1_000_000.0


def test_volume_pace_us_market_dst_and_fraction():
    """Verify US session timing (390 min total) during EST and EDT."""
    tz_ny = ZoneInfo("America/New_York")
    
    # 10:30 AM in NY: exactly 60 minutes elapsed out of 390 (15.385% expected)
    # Jan 16, 2024 is Tuesday (open session, Jan 15 was MLK Day)
    t_10_30_winter = datetime.datetime(2024, 1, 16, 10, 30, tzinfo=tz_ny)  # EST
    t_10_30_summer = datetime.datetime(2024, 7, 16, 10, 30, tzinfo=tz_ny)  # EDT

    # If 20d avg volume is 3,900,000, expected volume after 60 min is 600,000
    # If actual volume is 900,000, pace is exactly 1.5x
    pace_winter = VolumePaceCalculator.calculate_volume_pace(
        symbol="AAPL",
        avg_volume_20d=3_900_000.0,
        current_day_volume=900_000.0,
        market="US",
        current_time=t_10_30_winter,
    )
    pace_summer = VolumePaceCalculator.calculate_volume_pace(
        symbol="AAPL",
        avg_volume_20d=3_900_000.0,
        current_day_volume=900_000.0,
        market="US",
        current_time=t_10_30_summer,
    )
    assert pace_winter == 1.5
    assert pace_summer == 1.5


def test_invalid_volume_returns_none_never_one():
    """Verify that invalid baseline or off-market volume returns None, never 1.0."""
    res = VolumePaceCalculator.calculate_volume_pace(
        symbol="TCS",
        avg_volume_20d=0.0,
        current_day_volume=100000.0,
        market="IN",
    )
    assert res is None

    res_neg = VolumePaceCalculator.calculate_volume_pace(
        symbol="TCS",
        avg_volume_20d=-500.0,
        current_day_volume=100000.0,
        market="IN",
    )
    assert res_neg is None


def test_low_volume_pace_blocks_buy_confirmed(mem_db, monkeypatch):
    """Verify that even with 15m candle close confirmed, low volume pace blocks BUY_CONFIRMED."""
    monitor = LiveBreakoutMonitor()
    provider = AngelOneProvider()
    ws_mgr = provider.ws_manager
    from app.providers.manager import provider_manager
    provider_manager.angelone = provider

    sig = Signal(
        symbol="RELIANCE",
        market="IN",
        state="WATCHLIST",
        setup="VCP",
        trigger=2500.0,
        stop=2400.0,
        entry_zone_high=2537.5,
        target1=2700.0,
        qty=20,
        risk_amount=2000.0,
        cost_estimate=15.0,
        cost_in_r=0.007,
        rs_rank=90.0,
        score=92.0,
        atr=30.0,
    )
    mem_db.add(sig)
    mem_db.commit()

    tz_in = ZoneInfo("Asia/Kolkata")
    t_10_00 = datetime.datetime(2026, 4, 10, 10, 0, tzinfo=tz_in)

    # Inject 15m candle close confirmed above trigger 2500.0
    ws_mgr.candle_builder.completed_15m["RELIANCE"] = [{"close": 2510.0, "high": 2515.0, "low": 2495.0, "volume": 10000}]

    # Mock get_daily_bars to return baseline volume of 1,000,000
    dates = pd.date_range("2026-03-01", periods=25, freq="B")
    df_daily = pd.DataFrame({"volume": [1_000_000.0] * 25, "date": dates}, index=dates)
    monkeypatch.setattr(provider_manager, "get_daily_bars", lambda *args, **kwargs: {"RELIANCE": df_daily})

    # At 10:00 AM (45 min elapsed), expected fraction is 45/375 = 12% = 120,000 shares.
    # Day volume is only 12,000 shares -> pace is 0.1x (< required 1.0x)
    ws_mgr.live_quotes["RELIANCE"] = Quote(
        symbol="RELIANCE",
        market="IN",
        price=2505.0,
        provider="angelone",
        exchange_ts=t_10_00,
        received_ts=t_10_00,
        day_volume=12000.0,
        freshness="FRESH",
        realtime=True,
    )

    monitor.tick_market("IN", mem_db, current_time=t_10_00)
    mem_db.refresh(sig)

    # Must NOT be BUY_CONFIRMED: held in TRIGGERED_PROVISIONAL due to low volume pace!
    assert sig.state == "TRIGGERED_PROVISIONAL"
