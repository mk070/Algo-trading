import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.settings import settings

logger = logging.getLogger(__name__)

# Base declarative class for all SQLAlchemy ORM models
Base = declarative_base()


def get_neon_engine():
    """Builds and returns a resilient SQLAlchemy Engine configured specifically for
    Neon Serverless PostgreSQL.
    Key configurations:
    - pool_pre_ping=True: transparently reconnects after Neon autosuspend/idle timeouts.
    - pool_recycle=300: recycles sockets every 5 minutes to prevent stale PgBouncer/gateway connections.
    - QueuePool with controlled pool_size and max_overflow.
    """
    database_url = settings.normalized_database_url

    engine_kwargs = {
        "poolclass": QueuePool,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30.0,
        "pool_recycle": 300,  # 5 minutes for serverless compute idle windows
        "pool_pre_ping": True,  # Ping SELECT 1 before borrowing from pool
        "echo": False,
    }

    # Pass connect_args for sslmode if not already in URL query string
    if "sslmode" not in database_url and not database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"sslmode": "require"}

    return create_engine(database_url, **engine_kwargs)


# Initialize singleton engine and sessionmaker
engine = get_neon_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Transient connection error retry decorator
retry_db_operation = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=3.0),
    retry=retry_if_exception_type((OperationalError, DatabaseError, psycopg2.OperationalError)),
    reraise=True,
)


@contextmanager
def transaction_context(session: Optional[Session] = None) -> Generator[Session, None, None]:
    """Context manager providing clean transaction management with automatic
    commit on success and rollback on any exception.
    """
    sess = session or SessionLocal()
    try:
        yield sess
        sess.commit()
    except Exception as e:
        sess.rollback()
        logger.error(f"Transaction failed and was rolled back: {e}")
        raise
    finally:
        if session is None:
            sess.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database session lifecycle management with transactional safety."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db_health() -> Dict[str, Any]:
    """Checks database connectivity, latency, pool status, and PostgreSQL engine details."""
    t0 = time.time()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
            latency_ms = round((time.time() - t0) * 1000.0, 2)
            version_str = conn.execute(text("SELECT version();")).scalar()

        pool = engine.pool
        return {
            "status": "HEALTHY",
            "latency_ms": latency_ms,
            "database": "Neon PostgreSQL",
            "version": version_str.split(",")[0] if version_str else "PostgreSQL",
            "pool": {
                "size": pool.size() if hasattr(pool, "size") else 10,
                "checkedin": pool.checkedin() if hasattr(pool, "checkedin") else 0,
                "checkedout": pool.checkedout() if hasattr(pool, "checkedout") else 0,
                "overflow": pool.overflow() if hasattr(pool, "overflow") else 0,
            },
            "pre_ping": True,
            "recycle_sec": 300,
        }
    except Exception as e:
        return {
            "status": "DOWN",
            "latency_ms": round((time.time() - t0) * 1000.0, 2),
            "database": "Neon PostgreSQL",
            "error": str(e),
        }


def init_db():
    """Initializes PostgreSQL schema directly for the intended production environment."""
    from app import models  # noqa: F401
    logger.info("Initializing Neon PostgreSQL database schema...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Neon PostgreSQL schema created or verified successfully.")
    except Exception as e:
        logger.warning(f"Could not connect to Neon PostgreSQL during init_db: {e}")
