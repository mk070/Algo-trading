"""Tests for Neon Free-Plan Egress and Compute Optimizations."""

import datetime
from zoneinfo import ZoneInfo
import pytest

from app.cache import SharedMemoryCache, cached_json_response
from app.engine.calendars import is_market_open, is_exchange_holiday
from app.telemetry import tracker, EgressTracker


def test_cache_single_flight_and_ttl():
    cache = SharedMemoryCache()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"data": 123}

    # 1. First call: miss & compute
    data1, etag1, stale1, _ = cache.get_or_compute("test_key", compute, ttl_sec=5.0)
    assert data1 == {"data": 123}
    assert etag1 is not None
    assert stale1 is False
    assert calls == 1

    # 2. Second call within TTL: hit (no compute)
    data2, etag2, stale2, _ = cache.get_or_compute("test_key", compute, ttl_sec=5.0)
    assert data2 == {"data": 123}
    assert etag2 == etag1
    assert calls == 1

    # 3. Invalidation
    cache.invalidate("test_key")
    data3, etag3, stale3, _ = cache.get_or_compute("test_key", compute, ttl_sec=5.0)
    assert calls == 2


def test_cached_json_response_etag_304():
    data = {"symbols": ["RELIANCE", "TCS"]}
    etag = '"abcd1234efgh5678"'

    # When client sends matching If-None-Match: return 304 Not Modified
    res_304 = cached_json_response(data, etag=etag, if_none_match=etag, max_age_sec=60)
    assert res_304.status_code == 304
    assert res_304.headers["ETag"] == etag
    assert "public, max-age=60" in res_304.headers["Cache-Control"]

    # When client sends different or no If-None-Match: return 200 JSON
    res_200 = cached_json_response(data, etag=etag, if_none_match='"other"', max_age_sec=60)
    assert res_200.status_code == 200
    assert res_200.headers["ETag"] == etag


def test_market_hours_gating():
    # Indian market: Mon-Fri 09:15-15:30 IST
    sat_kol = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not is_market_open("IN", sat_kol)

    sun_kol = datetime.datetime(2026, 11, 15, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not is_market_open("IN", sun_kol)

    mon_open_kol = datetime.datetime(2026, 11, 16, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert is_market_open("IN", mon_open_kol)

    mon_pre_kol = datetime.datetime(2026, 11, 16, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not is_market_open("IN", mon_pre_kol)

    mon_post_kol = datetime.datetime(2026, 11, 16, 16, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not is_market_open("IN", mon_post_kol)

    # US market: Mon-Fri 09:30-16:00 EST/EDT
    sat_ny = datetime.datetime(2026, 11, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    assert not is_market_open("US", sat_ny)

    mon_open_ny = datetime.datetime(2026, 11, 16, 11, 0, tzinfo=ZoneInfo("America/New_York"))
    assert is_market_open("US", mon_open_ny)

    mon_post_ny = datetime.datetime(2026, 11, 16, 17, 0, tzinfo=ZoneInfo("America/New_York"))
    assert not is_market_open("US", mon_post_ny)


def test_telemetry_tracker():
    t = EgressTracker()
    t.record_query(duration_sec=0.01, row_count=50, row_bytes=1024, route="/api/plan", tag="trade_plan")
    t.record_http(route="/api/plan", status_code=200, bytes_sent=2048, duration_sec=0.02)
    t.record_cache_hit(route="/api/plan")
    t.record_cache_miss(route="/api/plan")

    summary = t.get_summary()
    assert summary["total_sql_queries"] == 1
    assert summary["total_sql_rows"] == 50
    assert summary["total_estimated_sql_bytes"] == 1024
    assert summary["total_http_bytes_sent"] == 2048
    assert summary["total_cache_hits"] == 1
    assert summary["total_cache_misses"] == 1
    assert len(summary["top_10_by_sql_bytes"]) == 1
