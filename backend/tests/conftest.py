import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend root is always on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db import Base, get_db
from app.main import app
from app.settings import settings


def _is_real_postgres_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    if "your_neon_password" in lower or "placeholder" in lower or "sample" in lower:
        return False
    return lower.startswith("postgresql://") or lower.startswith("postgres://") or lower.startswith("postgresql+psycopg2://")


@pytest.fixture(scope="session")
def db_engine():
    """
    Session-scoped engine fixture.
    Prefers TEST_DATABASE_URL or valid Neon DATABASE_URL.
    If no reachable PostgreSQL is configured, falls back to isolated in-memory test database.
    """
    pg_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    engine = None

    if pg_url and _is_real_postgres_url(pg_url):
        try:
            from app.db import get_neon_engine
            test_engine = get_neon_engine()
            with test_engine.connect() as conn:
                conn.execute(Base.metadata.tables.get("signals") is not None)
            engine = test_engine
        except Exception:
            engine = None

    if engine is None:
        # Isolated in-memory engine for local testing with multi-thread FastAPI support
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def isolated_db_session(db_engine):
    """
    Function-scoped isolated transaction fixture.
    Ensures tests run inside a transaction that is ALWAYS rolled back on teardown.
    Never deletes, mutates, or modifies actual trading records in any environment.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def mem_db(isolated_db_session):
    """Centralized alias for backwards compatibility with existing test suites."""
    yield isolated_db_session


@pytest.fixture(autouse=True)
def override_app_db(isolated_db_session):
    """
    Automatically overrides FastAPI's get_db dependency with the isolated test session.
    Guarantees all API calls during testing execute against the isolated transaction.
    """
    app.dependency_overrides[get_db] = lambda: isolated_db_session
    yield isolated_db_session
    app.dependency_overrides.clear()
