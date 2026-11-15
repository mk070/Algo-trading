"""Add universe coverage columns, fundamental snapshots, and watchlists tables.

Revision ID: 005_universe_watchlists_funds
Revises: 004_historical_ingestion
"""
from alembic import op
import sqlalchemy as sa


revision = "005_universe_watchlists_funds"
down_revision = "004_historical_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create fundamental_snapshots table
    op.create_table(
        "fundamental_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("market", sa.String(length=10), server_default="IN", nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("period_end", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=50), server_default="yfinance", nullable=False),
        sa.Column("revenue_yoy", sa.Float(), nullable=True),
        sa.Column("profit_yoy", sa.Float(), nullable=True),
        sa.Column("op_margin", sa.Float(), nullable=True),
        sa.Column("roce", sa.Float(), nullable=True),
        sa.Column("roe", sa.Float(), nullable=True),
        sa.Column("debt_equity", sa.Float(), nullable=True),
        sa.Column("interest_coverage", sa.Float(), nullable=True),
        sa.Column("pe", sa.Float(), nullable=True),
        sa.Column("sector_median_pe", sa.Float(), nullable=True),
        sa.Column("promoter_holding", sa.Float(), nullable=True),
        sa.Column("pledge_pct", sa.Float(), nullable=True),
        sa.Column("completeness", sa.String(length=20), server_default="NONE", nullable=False),
        sa.Column("lights_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_fundamental_snapshots_symbol", "fundamental_snapshots", ["symbol"])

    # 2. Add universe coverage columns to instruments table
    op.add_column("instruments", sa.Column("series", sa.String(length=10), server_default="EQ", nullable=True))
    op.add_column("instruments", sa.Column("universe_tier", sa.String(length=20), server_default="Small", nullable=True))
    op.add_column("instruments", sa.Column("is_higher_risk", sa.Boolean(), server_default=sa.text("false"), nullable=True))
    op.add_column("instruments", sa.Column("status", sa.String(length=50), server_default="SCANNED", nullable=True))
    op.add_column("instruments", sa.Column("status_reason", sa.String(length=255), nullable=True))
    op.add_column("instruments", sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("instruments", sa.Column("avg_turnover_20d", sa.Float(), nullable=True))
    op.add_column("instruments", sa.Column("last_price", sa.Float(), nullable=True))
    op.add_column("instruments", sa.Column("atr_pct", sa.Float(), nullable=True))

    # 3. Add sources_json to signals table
    op.add_column("signals", sa.Column("sources_json", sa.Text(), server_default='["AUTO"]', nullable=True))

    # 4. Create watchlists table
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("market", sa.String(length=10), server_default="IN", nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="APP_MANUAL", nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reimported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )

    # 5. Create watchlist_items table
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("raw_input", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="RESOLVED", nullable=True),
        sa.Column("exchange", sa.String(length=20), server_default="NSE", nullable=True),
        sa.Column("notes", sa.String(length=250), nullable=True),
        sa.Column("source", sa.String(length=50), server_default="APP_MANUAL", nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_watchlist_items_watchlist_id", "watchlist_items", ["watchlist_id"])
    op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"])

    # 6. Expand news_events text columns to match models.py
    with op.batch_alter_table("news_events") as batch_op:
        batch_op.alter_column("source_id", type_=sa.Text())
        batch_op.alter_column("title", type_=sa.Text())
        batch_op.alter_column("url", type_=sa.Text())


def downgrade() -> None:
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
    op.drop_column("signals", "sources_json")
    op.drop_column("instruments", "atr_pct")
    op.drop_column("instruments", "last_price")
    op.drop_column("instruments", "avg_turnover_20d")
    op.drop_column("instruments", "last_scanned_at")
    op.drop_column("instruments", "status_reason")
    op.drop_column("instruments", "status")
    op.drop_column("instruments", "is_higher_risk")
    op.drop_column("instruments", "universe_tier")
    op.drop_column("instruments", "series")
    op.drop_table("fundamental_snapshots")
