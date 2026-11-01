import datetime
import pytest

from app.models import Position, Signal
from app.providers.angelone_provider import AngelOneProvider, CandleBuilder
from app.providers.base import Quote
from app.scheduler.monitor import LiveBreakoutMonitor


def test_candle_builder_15m_aggregation_and_confirmation():
    builder = CandleBuilder()
    sym = "TCS"
    t1 = datetime.datetime(2026, 4, 10, 9, 15, 0)
    t2 = datetime.datetime(2026, 4, 10, 9, 20, 0)
    t3 = datetime.datetime(2026, 4, 10, 9, 29, 0)
    t4 = datetime.datetime(2026, 4, 10, 9, 30, 0)  # Next 15m bucket

    builder.process_tick(sym, price=3500.0, volume=1000, timestamp=t1)
    builder.process_tick(sym, price=3520.0, volume=500, timestamp=t2)
    builder.process_tick(sym, price=3515.0, volume=700, timestamp=t3)

    # Incomplete bar: 9:15-9:30 is still in progress
    assert builder.get_latest_completed_15m(sym) is None
    assert builder.is_confirmed_15m(sym, trigger_price=3510.0) is False

    # New tick in 9:30 bucket triggers completion of 9:15 bar
    completed = builder.process_tick(sym, price=3518.0, volume=200, timestamp=t4)
    assert completed is not None
    assert completed["open"] == 3500.0
    assert completed["high"] == 3520.0
    assert completed["close"] == 3515.0
    assert completed["volume"] == 2200

    # Now 9:15 bar is completed with close 3515.0 >= trigger 3510.0
    assert builder.is_confirmed_15m(sym, trigger_price=3510.0) is True
    assert builder.is_confirmed_15m(sym, trigger_price=3525.0) is False


def test_volume_pace_calculation():
    builder = CandleBuilder()
    avg_vol20 = 1_000_000.0

    # At 10:15 IST: 60 minutes elapsed out of 375 minutes (16.0% expected)
    t_10_15 = datetime.datetime(2026, 4, 10, 10, 15, 0)
    # Expected volume ~ 160,000. If current volume is 320,000, pace is ~ 2.0x
    pace = builder.calculate_volume_pace(
        symbol="RELIANCE",
        avg_volume_20d=avg_vol20,
        current_time=t_10_15,
        day_volume=320_000.0,
    )
    assert pace >= 1.9 and pace <= 2.1

    # If current volume is only 80,000, pace is ~ 0.5x
    pace_slow = builder.calculate_volume_pace(
        symbol="RELIANCE",
        avg_volume_20d=avg_vol20,
        current_time=t_10_15,
        day_volume=80_000.0,
    )
    assert pace_slow >= 0.45 and pace_slow <= 0.55


def test_stale_and_delayed_feeds_never_trigger_alerts(mem_db):
    monitor = LiveBreakoutMonitor()
    sig = Signal(
        symbol="INFY",
        market="IN",
        state="WATCHLIST",
        setup="VCP",
        trigger=1500.0,
        stop=1450.0,
        entry_zone_high=1522.5,
        target1=1600.0,
        qty=50,
        risk_amount=2500.0,
        cost_estimate=15.0,
        cost_in_r=0.006,
        rs_rank=85.0,
        score=88.0,
        atr=25.0,
    )
    mem_db.add(sig)
    mem_db.commit()

    # Provider WS Manager has no quote yet
    provider = AngelOneProvider()
    ws_mgr = provider.ws_manager

    # 1. Stale quote (older than 20s)
    stale_time = datetime.datetime.utcnow() - datetime.timedelta(seconds=45)
    ws_mgr.inject_tick("INFY", price=1510.0, volume=1000, timestamp=stale_time)
    monitor.tick_market("IN", mem_db)

    # State should remain WATCHLIST because quote is stale
    mem_db.refresh(sig)
    assert sig.state == "WATCHLIST"

    # 2. Quote marked as not realtime (delayed)
    ws_mgr.live_quotes["INFY"].is_realtime = False
    ws_mgr.live_quotes["INFY"].timestamp = datetime.datetime.utcnow()
    ws_mgr.live_quotes["INFY"].is_stale = False
    monitor.tick_market("IN", mem_db)

    mem_db.refresh(sig)
    assert sig.state == "WATCHLIST"


def test_no_chase_and_invalidation(mem_db):
    monitor = LiveBreakoutMonitor()
    provider = AngelOneProvider()
    ws_mgr = provider.ws_manager
    from app.providers.manager import provider_manager
    provider_manager.angelone = provider

    # Test Invalidation (price <= stop)
    sig_inv = Signal(
        symbol="SBIN",
        market="IN",
        state="WATCHLIST",
        setup="VCP",
        trigger=800.0,
        stop=780.0,
        entry_zone_high=812.0,
        target1=840.0,
        qty=100,
        risk_amount=2000.0,
        cost_estimate=12.0,
        cost_in_r=0.006,
        rs_rank=82.0,
        score=84.0,
        atr=12.0,
    )
    mem_db.add(sig_inv)
    mem_db.commit()

    ws_mgr.inject_tick("SBIN", price=775.0, volume=5000, timestamp=datetime.datetime.utcnow())
    monitor.tick_market("IN", mem_db)
    mem_db.refresh(sig_inv)
    assert sig_inv.state == "INVALIDATED"

    # Test Extended / No Chase (price > entry_zone_high)
    sig_ext = Signal(
        symbol="HDFCBANK",
        market="IN",
        state="WATCHLIST",
        setup="VCP",
        trigger=1600.0,
        stop=1560.0,
        entry_zone_high=1624.0,  # 1.5% zone
        target1=1700.0,
        qty=50,
        risk_amount=2000.0,
        cost_estimate=14.0,
        cost_in_r=0.007,
        rs_rank=88.0,
        score=90.0,
        atr=20.0,
    )
    mem_db.add(sig_ext)
    mem_db.commit()

    ws_mgr.inject_tick("HDFCBANK", price=1630.0, volume=5000, timestamp=datetime.datetime.utcnow())
    monitor.tick_market("IN", mem_db)
    mem_db.refresh(sig_ext)
    assert sig_ext.state == "EXTENDED"


def test_reconnect_and_gap_backfill():
    provider = AngelOneProvider()
    ws_mgr = provider.ws_manager
    ws_mgr.sync_subscriptions(["RELIANCE"])

    disc_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
    ws_mgr.on_disconnect()
    ws_mgr.disconnected_at = disc_time
    assert ws_mgr.connection_status == "RECONNECTING"

    # Simulate backfill candle insertion
    sample_bar = {
        "bucket": disc_time + datetime.timedelta(minutes=15),
        "open": 2500.0,
        "high": 2520.0,
        "low": 2495.0,
        "close": 2515.0,
        "volume": 50000.0,
    }
    ws_mgr.candle_builder.backfill_candle("RELIANCE", sample_bar)

    assert len(ws_mgr.candle_builder.completed_15m["RELIANCE"]) == 1
    assert ws_mgr.candle_builder.completed_15m["RELIANCE"][0]["close"] == 2515.0

    ws_mgr.on_reconnect_success()
    assert ws_mgr.connection_status == "CONNECTED"
    assert ws_mgr.disconnected_at is None


def test_completed_15m_trigger_reevaluates_pipeline_to_buy_confirmed(mem_db, monkeypatch):
    monitor = LiveBreakoutMonitor()
    provider = AngelOneProvider()
    ws_mgr = provider.ws_manager
    from app.providers.manager import provider_manager
    provider_manager.angelone = provider

    sig = Signal(
        symbol="TCS",
        market="IN",
        state="WATCHLIST",
        setup="VCP",
        trigger=3500.0,
        stop=3400.0,
        entry_zone_high=3552.5,
        target1=3700.0,
        qty=20,
        risk_amount=2000.0,
        cost_estimate=15.0,
        cost_in_r=0.007,
        rs_rank=90.0,
        score=92.0,
        atr=50.0,
    )
    mem_db.add(sig)
    mem_db.commit()

    # Step 1: Price crosses trigger at 9:20 (15m bar not complete yet)
    t_9_20 = datetime.datetime(2026, 4, 10, 9, 20, 0)
    ws_mgr.inject_tick("TCS", price=3510.0, volume=1000, timestamp=t_9_20)
    monitor.tick_market("IN", mem_db, current_time=t_9_20)
    mem_db.refresh(sig)
    # Should be provisional
    assert sig.state == "TRIGGERED_PROVISIONAL"

    # Step 2: 15m bar completes at 9:30 with close above trigger 3500.0
    t_9_30 = datetime.datetime(2026, 4, 10, 9, 30, 0)
    ws_mgr.inject_tick("TCS", price=3515.0, volume=5000, timestamp=t_9_30)

    # Mock decision_pipeline to return PASS
    from app.engine.pipeline import PipelineDecision, StageResult
    mock_decision = PipelineDecision(
        symbol="TCS",
        market="IN",
        asof_date=t_9_30.date(),
        mode="LIVE",
        final_decision="PASS",
        setup="VCP",
        trigger=3500.0,
        entry_zone_high=3552.5,
        stop=3400.0,
        target1=3700.0,
        qty=20,
        risk_amount=2000.0,
        cost_in_r=0.007,
        stages=[],
        all_rejection_reasons=[],
        config_hash="abc",
        code_version="2.3",
        data_source="ANGEL_ONE",
    )
    from app.engine.pipeline import decision_pipeline
    monkeypatch.setattr(decision_pipeline, "evaluate", lambda **kwargs: mock_decision)
    monkeypatch.setattr(provider_manager, "get_daily_bars", lambda *args, **kwargs: {"TCS": None})

    monitor.tick_market("IN", mem_db, current_time=t_9_30)
    mem_db.refresh(sig)
    assert sig.state == "BUY_CONFIRMED"

