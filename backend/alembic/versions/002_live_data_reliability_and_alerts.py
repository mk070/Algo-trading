"""Live data reliability, latest quotes, and custom price alerts

Revision ID: 002_live_data_alerts
Revises: 001_initial_neon_pg
Create Date: 2026-11-02 10:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_live_data_alerts'
down_revision: Union[str, Sequence[str], None] = '001_initial_neon_pg'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. latest_quotes (shared multi-worker cache)
    op.create_table(
        'latest_quotes',
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('exchange_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('received_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('freshness', sa.String(20), nullable=False, server_default='FRESH'),
        sa.Column('realtime', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('day_volume', sa.Float(), server_default='0.0'),
        sa.Column('open', sa.Float(), nullable=True),
        sa.Column('high', sa.Float(), nullable=True),
        sa.Column('low', sa.Float(), nullable=True),
        sa.Column('close', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('symbol', 'market', name='pk_latest_quotes'),
    )

    # 2. custom_price_alerts
    op.create_table(
        'custom_price_alerts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('target_price', sa.Float(), nullable=False),
        sa.Column('condition', sa.String(10), nullable=False),
        sa.Column('notes', sa.String(200), nullable=True),
        sa.Column('triggered', sa.Boolean(), server_default='false'),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggered_price', sa.Float(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_custom_price_alerts_symbol', 'custom_price_alerts', ['symbol'])


def downgrade() -> None:
    op.drop_index('ix_custom_price_alerts_symbol', table_name='custom_price_alerts')
    op.drop_table('custom_price_alerts')
    op.drop_table('latest_quotes')

