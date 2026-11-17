"""Add run_type column to paper trading tables for replay vs forward isolation.

Revision ID: 008_paper_run_type
Revises: 007_cycle4_paper_trading
"""
from alembic import op
import sqlalchemy as sa


revision = "008_paper_run_type"
down_revision = "007_cycle4_paper_trading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add run_type to paper_daily_history
    op.add_column(
        "paper_daily_history",
        sa.Column("run_type", sa.String(length=20), server_default="FORWARD", nullable=False),
    )
    op.create_index("ix_paper_daily_history_run_type", "paper_daily_history", ["run_type"])

    # 2. Add run_type to paper_orders
    op.add_column(
        "paper_orders",
        sa.Column("run_type", sa.String(length=20), server_default="FORWARD", nullable=False),
    )
    op.create_index("ix_paper_orders_run_type", "paper_orders", ["run_type"])

    # 3. Add run_type to paper_trades
    op.add_column(
        "paper_trades",
        sa.Column("run_type", sa.String(length=20), server_default="FORWARD", nullable=False),
    )
    op.create_index("ix_paper_trades_run_type", "paper_trades", ["run_type"])

    # 4. Add run_type to paper_holdings
    op.add_column(
        "paper_holdings",
        sa.Column("run_type", sa.String(length=20), server_default="FORWARD", nullable=False),
    )
    op.create_index("ix_paper_holdings_run_type", "paper_holdings", ["run_type"])

    # 5. Backfill existing seed records as 'REPLAY' so they never contaminate forward paper calculations
    op.execute("UPDATE paper_trades SET run_type = 'REPLAY';")
    op.execute("UPDATE paper_orders SET run_type = 'REPLAY';")
    op.execute("UPDATE paper_holdings SET run_type = 'REPLAY';")
    op.execute("UPDATE paper_daily_history SET run_type = 'REPLAY';")


def downgrade() -> None:
    op.drop_index("ix_paper_holdings_run_type", table_name="paper_holdings")
    op.drop_column("paper_holdings", "run_type")

    op.drop_index("ix_paper_trades_run_type", table_name="paper_trades")
    op.drop_column("paper_trades", "run_type")

    op.drop_index("ix_paper_orders_run_type", table_name="paper_orders")
    op.drop_column("paper_orders", "run_type")

    op.drop_index("ix_paper_daily_history_run_type", table_name="paper_daily_history")
    op.drop_column("paper_daily_history", "run_type")
