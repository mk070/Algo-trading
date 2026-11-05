"""Store the fundamental light snapshot associated with a signal.

Revision ID: 003_signal_fundamentals
Revises: 002_live_data_alerts
"""
from alembic import op
import sqlalchemy as sa

revision = "003_signal_fundamentals"
down_revision = "002_live_data_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("fundamentals_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "fundamentals_json")
