import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Watchlist, WatchlistItem


@pytest.fixture
def client():
    return TestClient(app)


def test_watchlist_lifecycle_and_import(client, mem_db, monkeypatch):
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: mem_db

    # 1. Fetch watchlists (should auto-create Default Focus)
    res = client.get("/api/watchlists?market=IN")
    assert res.status_code == 200
    lists = res.json()
    assert len(lists) >= 1
    default_wl = lists[0]
    assert default_wl["name"] == "Default Focus"
    wl_id = default_wl["id"]

    # 2. Add single symbol
    add_res = client.post(
        f"/api/watchlists/{wl_id}/items",
        json={"symbol": "TATAMOTORS", "notes": "Test swing candidate", "source": "APP_MANUAL"},
    )
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "ADDED"
    assert add_res.json()["symbol"] == "TATAMOTORS"

    # Duplicate check
    dup_res = client.post(
        f"/api/watchlists/{wl_id}/items",
        json={"symbol": "TATAMOTORS"},
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "ALREADY_EXISTS"

    # 3. Create new named watchlist
    create_res = client.post(
        "/api/watchlists",
        json={"name": "High Momentum", "market": "IN"},
    )
    assert create_res.status_code == 200
    new_wl_id = create_res.json()["watchlist"]["id"]

    # 4. Import batch symbols (Paste/CSV with resolution report)
    raw_payload = "NSE:RELIANCE, SBIN\nINFY\n^NSEI\nNIFTY24OCTFUT\nINVALID$$$TICKER"
    import_res = client.post(
        f"/api/watchlists/{new_wl_id}/import",
        json={"raw_text": raw_payload, "source_tag": "TEST_IMPORT"},
    )
    assert import_res.status_code == 200
    import_data = import_res.json()
    assert import_data["status"] == "COMPLETED"
    assert import_data["added_count"] >= 2  # RELIANCE, SBIN, INFY

    statuses = {r["status"] for r in import_data["report"]}
    assert "RESOLVED" in statuses
    assert "UNSUPPORTED" in statuses  # ^NSEI, FUT

    # 5. Fetch items for new watchlist
    items_res = client.get(f"/api/watchlists/{new_wl_id}/items")
    assert items_res.status_code == 200
    items_data = items_res.json()
    assert len(items_data["items"]) >= 2
    syms = [it["symbol"] for it in items_data["items"]]
    assert "RELIANCE" in syms

    # Clean overrides
    app.dependency_overrides.clear()

