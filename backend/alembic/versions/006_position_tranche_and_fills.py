"""Add position tranche accounting, high-water mark, and fill idempotency.

Revision ID: 006_position_tranche_and_fills
Revises: 005_universe_watchlists_funds
"""
from alembic import op
import sqlalchemy as sa


revision = "006_position_tranche_and_fills"
down_revision = "005_universe_watchlists_funds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add columns to positions table
    op.add_column("positions", sa.Column("initial_qty", sa.Integer(), nullable=True))
    op.add_column("positions", sa.Column("highest_price_since_entry", sa.Float(), nullable=True))
    op.add_column("positions", sa.Column("target_partial_completed", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("positions", sa.Column("target_partial_qty", sa.Integer(), server_default="0", nullable=False))
    op.add_column("positions", sa.Column("total_reduced_qty", sa.Integer(), server_default="0", nullable=False))
    op.add_column("positions", sa.Column("partial_exit_alerted_at", sa.DateTime(timezone=True), nullable=True))

    # Safe backfill:
    # 1. Reconstruct initial_qty from original BUY fill if present
    op.execute("""
        UPDATE positions
        SET initial_qty = (
            SELECT f.qty FROM fills f
            WHERE f.position_id = positions.id AND f.side = 'BUY'
            ORDER BY f.id ASC
            LIMIT 1
        )
        WHERE initial_qty IS NULL
        AND EXISTS (
            SELECT 1 FROM fills f
            WHERE f.position_id = positions.id AND f.side = 'BUY'
        )
    """)

    # 2. Reconstruct initial_qty from remaining qty + historical SELL fills if no BUY fill
    op.execute("""
        UPDATE positions
        SET initial_qty = qty + COALESCE((
            SELECT SUM(f.qty) FROM fills f
            WHERE f.position_id = positions.id AND f.side = 'SELL'
        ), 0)
        WHERE initial_qty IS NULL
    """)

    # 3. Backfill total_reduced_qty from historical SELL fills
    op.execute("""
        UPDATE positions
        SET total_reduced_qty = COALESCE((
            SELECT SUM(f.qty) FROM fills f
            WHERE f.position_id = positions.id AND f.side = 'SELL'
        ), 0)
        WHERE total_reduced_qty = 0
    """)

    # 4. Backfill highest_price_since_entry
    op.execute("UPDATE positions SET highest_price_since_entry = entry_price WHERE highest_price_since_entry IS NULL")

    # 2. Add columns to fills table
    op.add_column("fills", sa.Column("fill_reason", sa.String(length=50), server_default="MANUAL", nullable=True))
    op.add_column("fills", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.create_index("ix_fills_idempotency_key", "fills", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_fills_idempotency_key", table_name="fills")
    with op.batch_alter_table("fills") as batch_op:
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("fill_reason")

    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_column("partial_exit_alerted_at")
        batch_op.drop_column("total_reduced_qty")
        batch_op.drop_column("target_partial_qty")
        batch_op.drop_column("target_partial_completed")
        batch_op.drop_column("highest_price_since_entry")
        batch_op.drop_column("initial_qty")
