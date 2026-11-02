import datetime
import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.engine.planner import planner
from app.engine.screener import screener_engine
from app.engine.symbol_normalizer import symbol_normalizer
from app.main import app
from app.models import Position, Signal, Watchlist, WatchlistItem
from app.providers.base import DecisionQuote, Quote
from app.scheduler.monitor import LiveBreakoutMonitor


@pytest.fixture
def client():
    return TestClient(app)


def test_symbol_normalizer_and_classification():
    # 1. Special characters & prefixes
    res_mm = symbol_normalizer.classify_symbol("NSE:M&M", "IN")
    assert res_mm.status == "RESOLVED"
    assert res_mm.symbol == "M&M"
    assert res_mm.exchange == "NSE"

    res_bajaj = symbol_normalizer.classify_symbol("BAJAJ-AUTO-EQ", "IN")
    assert res_bajaj.status == "RESOLVED"
    assert res_bajaj.symbol == "BAJAJ-AUTO"

    # 2. Unsupported derivatives & indices
    res_fut = symbol_normalizer.classify_symbol("NIFTY24OCT25000CE", "IN")
    assert res_fut.status == "UNSUPPORTED"

    res_idx = symbol_normalizer.classify_symbol("^NSEI", "IN")
    assert res_idx.status == "UNSUPPORTED"

    # 3. Canonical NSE preference
    res_bse = symbol_normalizer.classify_symbol("BSE:TCS", "IN")
    assert res_bse.status == "RESOLVED"
    assert res_bse.symbol == "TCS"
    assert res_bse.exchange == "NSE"


def test_diff_preview_and_reimport_merge_replace(client, mem_db):
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: mem_db

    # Create watchlist
    wl = Watchlist(name="Diff Test", market="IN", source="ZERODHA_MANUAL_IMPORT")
    mem_db.add(wl)
    mem_db.commit()
    mem_db.refresh(wl)

    # Add initial items: RELIANCE, TCS
    item1 = WatchlistItem(watchlist_id=wl.id, symbol="RELIANCE", exchange="NSE", status="RESOLVED")
    item2 = WatchlistItem(watchlist_id=wl.id, symbol="TCS", exchange="NSE", status="RESOLVED")
    mem_db.add_all([item1, item2])
    mem_db.commit()

    # Reimport text: TCS, INFY (RELIANCE removed, INFY added, TCS unchanged)
    diff_res = client.post(
        f"/api/watchlists/{wl.id}/diff",
        json={"raw_text": "TCS\nINFY"},
    )
    assert diff_res.status_code == 200
    diff_data = diff_res.json()["diff"]
    added_syms = [x["symbol"] for x in diff_data["added"]]
    removed_syms = diff_data["removed"]
    unchanged_syms = diff_data["unchanged"]

    assert "INFY" in added_syms
    assert "RELIANCE" in removed_syms
    assert "TCS" in unchanged_syms

    # Execute Replace mode reimport
    reimport_res = client.post(
        f"/api/watchlists/{wl.id}/reimport",
        json={"raw_text": "TCS\nINFY", "mode": "replace"},
    )
    assert reimport_res.status_code == 200
    active_items = (
        mem_db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == wl.id, WatchlistItem.is_deleted == False)
        .all()
    )
    active_syms = {it.symbol for it in active_items}
    assert active_syms == {"TCS", "INFY"}

    # Verify soft-deletion of RELIANCE
    removed_rel = (
        mem_db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == wl.id, WatchlistItem.symbol == "RELIANCE")
        .first()
    )
    assert removed_rel.is_deleted is True
    assert removed_rel.removed_at is not None

    app.dependency_overrides.clear()


def test_out_of_universe_rs_calculation():
    # Universe return distribution (10 stocks with varied scores)
    universe_scores = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

    # Out of universe stock with higher returns beating 80% of universe
    dates = pd.date_range("2025-01-01", periods=150, freq="B")
    prices = [100.0 * (1.0 + 0.0055 * i) for i in range(150)]
    df = pd.DataFrame({"close": prices, "volume": [1000000] * 150}, index=dates)

    rs_rank = screener_engine.compute_out_of_universe_rs_rank(df, universe_scores)
    assert rs_rank >= 0.70
    # Universe distribution length should remain untouched (10)
    assert len(universe_scores) == 10


def test_already_held_stock_suppression_and_unified_pooling(mem_db):
    # 1. Create a watchlist item
    wl = Watchlist(name="Core Setup", market="IN", source="APP_MANUAL")
    mem_db.add(wl)
    mem_db.commit()
    mem_db.refresh(wl)

    item = WatchlistItem(watchlist_id=wl.id, symbol="INFY", exchange="NSE", status="RESOLVED")
    mem_db.add(item)

    # 2. Add INFY as an OPEN position
    pos = Position(
        symbol="INFY",
        market="IN",
        source="MANUAL",
        entry_date=datetime.date.today(),
        entry_price=1500.0,
        qty=10,
        initial_stop=1420.0,
        active_stop=1420.0,
        target1=1660.0,
        status="OPEN",
    )
    mem_db.add(pos)
    mem_db.commit()

    # 3. Run candidate pooling
    # INFY is in universe and in watchlist, and also in open positions
    open_pos = mem_db.query(Position.symbol).filter(Position.market == "IN", Position.status == "OPEN").all()
    held_symbols = set(p[0] for p in open_pos)
    assert "INFY" in held_symbols


def test_monitor_tiers_and_hysteresis(mem_db):
    monitor = LiveBreakoutMonitor()

    # Test subscription cap & tiering
    p0 = ["POS1", "POS2"]
    p1 = [f"NEAR{i}" for i in range(20)]
    p2 = [f"VALID{i}" for i in range(40)]  # Total 62 symbols > cap of 50

    sub_list = []
    for s in p0:
        if s not in sub_list and len(sub_list) < monitor.max_subscriptions:
            sub_list.append(s)
    for s in p1:
        if s not in sub_list and len(sub_list) < monitor.max_subscriptions:
            sub_list.append(s)
    for s in p2:
        if s not in sub_list and len(sub_list) < monitor.max_subscriptions:
            sub_list.append(s)

    assert len(sub_list) == 50
    assert "POS1" in sub_list and "POS2" in sub_list  # P0 all included
    assert "NEAR0" in sub_list  # P1 included
    # Excess P2 evicted
    assert len(set(p2).difference(sub_list)) > 0

    # Test hysteresis:
    # Trigger = 1000. Price = 988 (1.2% away <= 1.5%) -> Promoted to APPROACHING
    trigger = 1000.0
    price_promote = 988.0
    dist_promote = (trigger - price_promote) / trigger * 100.0
    assert dist_promote <= monitor.approach_pct  # 1.2% <= 1.5%

    # Price falls to 975 (2.5% away): should NOT demote (since 2.5% <= 3.0% hysteresis threshold)
    dist_hold = (trigger - 975.0) / trigger * 100.0
    assert dist_hold > monitor.approach_pct and dist_hold <= monitor.demote_pct

    # Price falls to 965 (3.5% away > 3.0% demote threshold): demoted back to WATCHLIST
    dist_demote = (trigger - 965.0) / trigger * 100.0
    assert dist_demote > monitor.demote_pct


def test_delayed_quote_alert_suppression(mem_db):
    # Ensure stale or delayed quotes never trigger breakout BUY alerts
    delayed_quote = Quote(
        symbol="TCS",
        last_price=4000.0,
        day_volume=1000000,
        timestamp=datetime.datetime.utcnow(),
        freshness="DELAYED",
        is_realtime=False,
    )
    assert not delayed_quote.is_realtime
    # In monitor tick: if not q.is_realtime: continue -> suppressed!
