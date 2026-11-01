import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.settings import settings, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
db_path = DATA_DIR / "swing_algo.db"
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Automatic SQLite migration for new columns on existing tables
    try:
        with engine.connect() as conn:
            # Check news_events columns
            result = conn.execute(text("PRAGMA table_info(news_events)"))
            existing_cols = {row[1] for row in result.fetchall()}
            if existing_cols:
                if "match_confidence" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN match_confidence VARCHAR(20) DEFAULT 'EXACT_NAME'"))
                if "is_unverified" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN is_unverified BOOLEAN DEFAULT 0"))
                if "syndication_cluster_id" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN syndication_cluster_id VARCHAR(100)"))
                if "materiality" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN materiality VARCHAR(20) DEFAULT 'LOW'"))
                if "summary" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN summary TEXT"))
                if "price_change_day_pct" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN price_change_day_pct FLOAT"))
                if "price_atr_multiple" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN price_atr_multiple FLOAT"))
                if "analyst_action_json" not in existing_cols:
                    conn.execute(text("ALTER TABLE news_events ADD COLUMN analyst_action_json TEXT"))

            # Check alerts columns
            result = conn.execute(text("PRAGMA table_info(alerts)"))
            alert_cols = {row[1] for row in result.fetchall()}
            if alert_cols:
                if "retry_count" not in alert_cols:
                    conn.execute(text("ALTER TABLE alerts ADD COLUMN retry_count INTEGER DEFAULT 0"))
                if "last_reminder_ts" not in alert_cols:
                    conn.execute(text("ALTER TABLE alerts ADD COLUMN last_reminder_ts DATETIME"))
            conn.commit()
    except Exception:
        pass

