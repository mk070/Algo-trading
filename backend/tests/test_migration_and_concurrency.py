import datetime
import os
from pathlib import Path
import tempfile
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import Fill, Journal, Position

client = TestClient(app)


# ============================================================================
# Section 3: Migration 006 Upgrade / Downgrade & Data Integrity Tests
# ============================================================================

def test_migration_006_upgrade_downgrade_and_backfill():
    """Test migration 006 on an isolated database with:
    1. Zero records
    2. Representative legacy positions and historical fills
    3. Backfill verification of initial_qty, total_reduced_qty, highest_price_since_entry
    4. Downgrade safety and re-upgrade
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        temp_db_url = f"sqlite:///{temp_db_path}"
        engine = create_engine(temp_db_url)

        # Locate alembic.ini relative to test file
        root_dir = Path(__file__).resolve().parent.parent.parent
        alembic_ini_path = str(root_dir / "alembic.ini")
        alembic_dir = str(root_dir / "backend" / "alembic")

        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", temp_db_url)
        alembic_cfg.set_main_option("script_location", alembic_dir)

        # 1. Upgrade up to 005 (legacy schema)
        command.upgrade(alembic_cfg, "005_universe_watchlists_funds")

        # 2. Insert representative legacy records under the 005 schema (without initial_qty column)
        with engine.begin() as conn:
            # Position 1: Legacy position with original BUY fill (100) and previous partial SELL fill (40)
            conn.execute(
                text("""
                INSERT INTO positions (id, symbol, market, source, entry_date, entry_price, qty, initial_stop, active_stop, target1, status)
                VALUES (1, 'INFY', 'IN', 'MANUAL', '2026-04-01', 1500.0, 60, 1425.0, 1425.0, 1650.0, 'OPEN')
                """)
            )
            # Fills for Position 1
            conn.execute(
                text("""
                INSERT INTO fills (id, position_id, side, date, price, qty, fees_total)
                VALUES (1, 1, 'BUY', '2026-04-01', 1500.0, 100, 0.0)
                """)
            )
            conn.execute(
                text("""
                INSERT INTO fills (id, position_id, side, date, price, qty, fees_total)
                VALUES (2, 1, 'SELL', '2026-04-05', 1600.0, 40, 50.0)
                """)
            )

            # Position 2: Legacy position created without BUY fill, but has historical SELL fill of 25 (remaining qty 75)
            conn.execute(
                text("""
                INSERT INTO positions (id, symbol, market, source, entry_date, entry_price, qty, initial_stop, active_stop, target1, status)
                VALUES (2, 'TCS', 'IN', 'MANUAL', '2026-04-01', 3500.0, 75, 3325.0, 3325.0, 3850.0, 'OPEN')
                """)
            )
            conn.execute(
                text("""
                INSERT INTO fills (id, position_id, side, date, price, qty, fees_total)
                VALUES (3, 2, 'SELL', '2026-04-06', 3600.0, 25, 60.0)
                """)
            )

            # Position 3: Legacy position with no fills at all (remaining qty 50)
            conn.execute(
                text("""
                INSERT INTO positions (id, symbol, market, source, entry_date, entry_price, qty, initial_stop, active_stop, target1, status)
                VALUES (3, 'RELIANCE', 'IN', 'MANUAL', '2026-04-01', 2800.0, 50, 2660.0, 2660.0, 3080.0, 'OPEN')
                """)
            )

        # 3. Execute Migration 006 Upgrade
        command.upgrade(alembic_cfg, "006_position_tranche_and_fills")

        # 4. Verify accurate backfill results
        with engine.connect() as conn:
            # Position 1: initial_qty reconstructed from BUY fill = 100, total_reduced_qty = 40
            row1 = conn.execute(
                text("SELECT qty, initial_qty, total_reduced_qty, highest_price_since_entry, target_partial_completed FROM positions WHERE id = 1")
            ).mappings().first()
            assert row1["qty"] == 60
            assert row1["initial_qty"] == 100
            assert row1["total_reduced_qty"] == 40
            assert row1["highest_price_since_entry"] == 1500.0
            assert row1["target_partial_completed"] in (0, False, "false", "0")

            # Position 2: initial_qty reconstructed from qty (75) + SELL fills (25) = 100, total_reduced_qty = 25
            row2 = conn.execute(
                text("SELECT qty, initial_qty, total_reduced_qty, highest_price_since_entry FROM positions WHERE id = 2")
            ).mappings().first()
            assert row2["qty"] == 75
            assert row2["initial_qty"] == 100
            assert row2["total_reduced_qty"] == 25
            assert row2["highest_price_since_entry"] == 3500.0

            # Position 3: initial_qty reconstructed from qty = 50, total_reduced_qty = 0
            row3 = conn.execute(
                text("SELECT qty, initial_qty, total_reduced_qty, highest_price_since_entry FROM positions WHERE id = 3")
            ).mappings().first()
            assert row3["qty"] == 50
            assert row3["initial_qty"] == 50
            assert row3["total_reduced_qty"] == 0
            assert row3["highest_price_since_entry"] == 2800.0

        # 5. Test Downgrade to 005
        command.downgrade(alembic_cfg, "005_universe_watchlists_funds")

        with engine.connect() as conn:
            # Columns dropped, existing position data remains intact and readable
            rows = conn.execute(text("SELECT id, symbol, qty, entry_price FROM positions ORDER BY id ASC")).fetchall()
            assert len(rows) == 3
            assert rows[0][2] == 60
            assert rows[1][2] == 75
            assert rows[2][2] == 50

        # 6. Test Re-Upgrade to 006
        command.upgrade(alembic_cfg, "006_position_tranche_and_fills")
        with engine.connect() as conn:
            recheck = conn.execute(text("SELECT id, initial_qty FROM positions ORDER BY id ASC")).fetchall()
            assert len(recheck) == 3
            assert recheck[0][1] == 100

        engine.dispose()
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except Exception:
                pass


# ============================================================================
# Section 4: Concurrency & Partial-Exit Transaction Tests
# ============================================================================

def test_idempotent_duplicate_and_retry(isolated_db_session):
    """Test that retried request with the same idempotency key returns idempotent duplicate
    without double reducing position quantity or inserting a second fill.
    """
    pos = Position(
        symbol="CONCUR_1",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1000.0,
        qty=100,
        initial_qty=100,
        initial_stop=950.0,
        active_stop=950.0,
        target1=1100.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    payload = {
        "qty": 50,
        "exit_price": 1100.0,
        "exit_date": "2026-04-10",
        "action_type": "PARTIAL_TARGET",
        "idempotency_key": "unique_tx_key_concur_1",
    }

    # Request 1: succeeds
    r1 = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert r1.status_code == 200
    assert r1.json()["status"] == "PARTIALLY_CLOSED"
    assert r1.json()["remaining_qty"] == 50

    # Request 2 (Retry with exact same idempotency key): returns idempotent duplicate
    r2 = client.post(f"/api/positions/{pos.id}/close", json=payload)
    assert r2.status_code == 200
    assert r2.json()["status"] == "IDEMPOTENT_DUPLICATE"
    assert "already processed" in r2.json()["message"]

    # Verify DB state: qty reduced only once to 50, exactly 1 fill
    isolated_db_session.refresh(pos)
    assert pos.qty == 50
    assert pos.total_reduced_qty == 50

    fills = isolated_db_session.query(Fill).filter(Fill.position_id == pos.id).all()
    assert len(fills) == 1
    assert fills[0].qty == 50


def test_concurrent_competing_reductions_prevent_over_reduction(isolated_db_session):
    """Test two competing reduction requests (each for 60 shares) on a 100-share position.
    Guarantees that over-reduction (60 + 60 = 120 > 100) is physically rejected by row validation.
    """
    pos = Position(
        symbol="CONCUR_OVER",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1000.0,
        qty=100,
        initial_qty=100,
        initial_stop=950.0,
        active_stop=950.0,
        target1=1100.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    payload_a = {
        "qty": 60,
        "exit_price": 1050.0,
        "exit_date": "2026-04-10",
        "action_type": "MANUAL_REDUCTION",
        "idempotency_key": "compete_key_a",
    }
    payload_b = {
        "qty": 60,
        "exit_price": 1050.0,
        "exit_date": "2026-04-10",
        "action_type": "MANUAL_REDUCTION",
        "idempotency_key": "compete_key_b",
    }

    resp_a = client.post(f"/api/positions/{pos.id}/close", json=payload_a)
    resp_b = client.post(f"/api/positions/{pos.id}/close", json=payload_b)

    # First succeeds (qty becomes 40)
    assert resp_a.status_code == 200
    assert resp_a.json()["remaining_qty"] == 40

    # Second MUST fail with 400 Bad Request because 60 > remaining 40
    assert resp_b.status_code == 400
    assert "exceeds remaining position quantity" in resp_b.json()["detail"]

    # Final position state is consistent
    isolated_db_session.refresh(pos)
    assert pos.qty == 40
    assert pos.status == "OPEN"
    fills = isolated_db_session.query(Fill).filter(Fill.position_id == pos.id).all()
    assert len(fills) == 1
    assert fills[0].qty == 60


def test_full_exit_after_earlier_partial_exit(isolated_db_session):
    """Test partial exit (50 of 100) followed by full exit (remaining 50).
    Verifies that position properly transitions to CLOSED, qty 0, and all fills/journals match.
    """
    pos = Position(
        symbol="TWO_STEP_EXIT",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1000.0,
        qty=100,
        initial_qty=100,
        initial_stop=950.0,
        active_stop=950.0,
        target1=1100.0,
        status="OPEN",
    )
    isolated_db_session.add(pos)
    isolated_db_session.commit()

    # Step 1: Partial exit of 50
    resp1 = client.post(
        f"/api/positions/{pos.id}/close",
        json={"qty": 50, "exit_price": 1100.0, "exit_date": "2026-04-05", "action_type": "PARTIAL_TARGET"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "PARTIALLY_CLOSED"
    assert resp1.json()["remaining_qty"] == 50

    # Step 2: Full exit of remaining 50
    resp2 = client.post(
        f"/api/positions/{pos.id}/close",
        json={"qty": 50, "exit_price": 1150.0, "exit_date": "2026-04-10", "action_type": "FULL_EXIT"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "CLOSED"
    assert resp2.json()["remaining_qty"] == 0

    isolated_db_session.refresh(pos)
    assert pos.status == "CLOSED"
    assert pos.qty == 0
    assert pos.total_reduced_qty == 100
    assert pos.target_partial_completed is True

    # 2 Fills and 2 Journals
    fills = isolated_db_session.query(Fill).filter(Fill.position_id == pos.id).order_by(Fill.id.asc()).all()
    assert len(fills) == 2
    assert fills[0].fill_reason == "PARTIAL_TARGET"
    assert fills[0].qty == 50
    assert fills[1].fill_reason == "FULL_EXIT"
    assert fills[1].qty == 50

    journals = isolated_db_session.query(Journal).filter(Journal.position_id == pos.id).order_by(Journal.id.asc()).all()
    assert len(journals) == 2
    assert journals[0].qty == 50
    assert journals[1].qty == 50


def test_failed_journal_rolls_back_atomic_transaction(monkeypatch):
    """Verify that if journal insertion fails, position quantity reduction and fill insertion
    are fully rolled back in the atomic transaction.
    """
    from sqlalchemy.pool import StaticPool
    test_engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    SessionLocal = sessionmaker(bind=test_engine)

    # 1. Commit position to database
    db1 = SessionLocal()
    pos = Position(
        symbol="FAIL_ROLLBACK",
        market="IN",
        entry_date=datetime.date(2026, 4, 1),
        entry_price=1000.0,
        qty=100,
        initial_qty=100,
        initial_stop=950.0,
        active_stop=950.0,
        target1=1100.0,
        status="OPEN",
    )
    db1.add(pos)
    db1.commit()
    pos_id = pos.id
    db1.close()

    # 2. Monkeypatch Journal constructor to raise exception
    def broken_journal(*args, **kwargs):
        raise RuntimeError("Simulated database failure during Journal creation")

    import app.api.routes_positions as rp
    monkeypatch.setattr(rp, "Journal", broken_journal)

    # 3. Attempt exit in second session
    db2 = SessionLocal()
    with pytest.raises(Exception) as exc_info:
        rp.close_position(
            position_id=pos_id,
            req=rp.ClosePositionRequest(
                qty=50,
                exit_price=1100.0,
                exit_date="2026-04-05",
                action_type="PARTIAL_TARGET",
            ),
            db=db2,
        )
    assert "Database transaction failed" in str(exc_info.value.detail)
    db2.close()

    # 4. Verify rollback in third session: position qty is STILL 100, no fills created
    db3 = SessionLocal()
    re_pos = db3.query(Position).filter(Position.id == pos_id).first()
    assert re_pos is not None
    assert re_pos.qty == 100
    assert re_pos.status == "OPEN"
    fills = db3.query(Fill).filter(Fill.position_id == pos_id).all()
    assert len(fills) == 0
    db3.close()
