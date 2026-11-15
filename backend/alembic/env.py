import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# Ensure backend directory is in python path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.settings import settings
from app.models import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate support
target_metadata = Base.metadata


def get_url() -> str:
    """Retrieve normalized PostgreSQL database URL for migrations.
    Priority:
    1. MIGRATION_DATABASE_URL environment variable (direct unpooled connection for new project migration).
    2. settings.normalized_unpooled_database_url (active configuration).
    3. Fallback to alembic.ini config or placeholder.
    """
    migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    if migration_url:
        # Strip pooler and channel_binding if present for transactional DDL
        import re
        clean_url = re.sub(r"[?&]channel_binding=[^&]+", "", migration_url.strip())
        if "-pooler" in clean_url:
            clean_url = clean_url.replace("-pooler", "")
        if clean_url.startswith("postgres://"):
            clean_url = clean_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif clean_url.startswith("postgresql://") and not clean_url.startswith("postgresql+"):
            clean_url = clean_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return clean_url

    cfg_url = config.get_main_option("sqlalchemy.url")
    if cfg_url and ("sqlite" in cfg_url or "test" in cfg_url):
        return cfg_url

    try:
        return settings.normalized_unpooled_database_url
    except Exception:
        # Fallback to configured URL in alembic.ini or placeholder if settings fail
        return config.get_main_option(
            "sqlalchemy.url",
            "postgresql+psycopg2://neondb_owner:YOUR_PASSWORD@ep-sample-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
        )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    Emits SQL statements directly to stdout or script without connecting to engine.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    Connects to Neon PostgreSQL and executes migrations within a transaction.
    """
    url = get_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=(connection.dialect.name == "sqlite"),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
