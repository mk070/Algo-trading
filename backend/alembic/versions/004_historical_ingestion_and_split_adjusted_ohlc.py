"""Add historical ingestion checkpoints, runs, and split-adjusted OHLC columns to bars_daily.

Revision ID: 004_historical_ingestion
Revises: 003_signal_fundamentals
"""
from alembic import op
import sqlalchemy as sa

revision = "004_historical_ingestion"
down_revision = "003_signal_fundamentals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add split-adjusted OHLC and provenance tracking to bars_daily
    op.add_column("bars_daily", sa.Column("split_adj_open", sa.Float(), nullable=True))
    op.add_column("bars_daily", sa.Column("split_adj_high", sa.Float(), nullable=True))
    op.add_column("bars_daily", sa.Column("split_adj_low", sa.Float(), nullable=True))
    op.add_column("bars_daily", sa.Column("split_adj_close", sa.Float(), nullable=True))
    op.add_column("bars_daily", sa.Column("dividend_factor", sa.Float(), server_default="1.0", nullable=True))
    op.add_column("bars_daily", sa.Column("is_split_adjusted", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("bars_daily", sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))

    # 2. Create ingestion_runs table
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("target_sessions", sa.Integer(), server_default="1250", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="RUNNING", nullable=False),
        sa.Column("total_symbols", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_symbols", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_symbols", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # 3. Create ingestion_checkpoints table
    op.create_table(
        "ingestion_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("expected_sessions", sa.Integer(), server_default="1250", nullable=False),
        sa.Column("available_sessions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_sessions_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("earliest_date", sa.Date(), nullable=True),
        sa.Column("latest_date", sa.Date(), nullable=True),
        sa.Column("meets_300", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("meets_750", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("meets_1250", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("split_adjusted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_ingest_sym_mkt", "ingestion_checkpoints", ["symbol", "market"])
    op.create_index("idx_ingest_run_id", "ingestion_checkpoints", ["run_id"])


def downgrade() -> None:
    op.drop_index("idx_ingest_run_id", table_name="ingestion_checkpoints")
    op.drop_index("idx_ingest_sym_mkt", table_name="ingestion_checkpoints")
    op.drop_table("ingestion_checkpoints")
    op.drop_table("ingestion_runs")
    op.drop_column("bars_daily", "ingested_at")
    op.drop_column("bars_daily", "is_split_adjusted")
    op.drop_column("bars_daily", "dividend_factor")
    op.drop_column("bars_daily", "split_adj_close")
    op.drop_column("bars_daily", "split_adj_low")
    op.drop_column("bars_daily", "split_adj_high")
    op.drop_column("bars_daily", "split_adj_open")

