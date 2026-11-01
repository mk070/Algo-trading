"""Initial Neon PostgreSQL schema for Swing Trading Platform

Revision ID: 001_initial_neon_pg
Revises: 
Create Date: 2026-11-01 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001_initial_neon_pg'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. instruments
    op.create_table(
        'instruments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('sector', sa.String(100), nullable=True),
        sa.Column('industry', sa.String(100), nullable=True),
        sa.Column('provider_token', sa.String(50), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true'),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_instruments_symbol', 'instruments', ['symbol'])

    # 2. bars_daily
    op.create_table(
        'bars_daily',
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('adj_close', sa.Float(), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.PrimaryKeyConstraint('symbol', 'date'),
    )
    op.create_index('idx_bars_symbol_date', 'bars_daily', ['symbol', 'date'])

    # 3. scans
    op.create_table(
        'scans',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('market', sa.String(10), nullable=False),
        sa.Column('run_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('session_date', sa.Date(), nullable=False),
        sa.Column('regime', sa.String(20), nullable=False),
        sa.Column('regime_detail_json', sa.Text(), nullable=True),
        sa.Column('universe_size', sa.Integer(), server_default='0'),
        sa.Column('passed_filters', sa.Integer(), server_default='0'),
        sa.Column('data_warnings_json', sa.Text(), nullable=True),
    )

    # 4. signals
    op.create_table(
        'signals',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scan_id', sa.Integer(), sa.ForeignKey('scans.id'), nullable=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False),
        sa.Column('setup', sa.String(20), nullable=False),
        sa.Column('trigger', sa.Float(), nullable=False),
        sa.Column('entry_zone_high', sa.Float(), nullable=False),
        sa.Column('stop', sa.Float(), nullable=False),
        sa.Column('target1', sa.Float(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('risk_amount', sa.Float(), nullable=False),
        sa.Column('cost_estimate', sa.Float(), nullable=False),
        sa.Column('cost_in_r', sa.Float(), nullable=False),
        sa.Column('rs_rank', sa.Float(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('atr', sa.Float(), nullable=False),
        sa.Column('gap95', sa.Float(), nullable=True),
        sa.Column('reasons_json', sa.Text(), nullable=True),
        sa.Column('news_flags_json', sa.Text(), nullable=True),
        sa.Column('state', sa.String(30), server_default='WATCHLIST'),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_signals_symbol', 'signals', ['symbol'])

    # 5. positions
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('source', sa.String(20), server_default='MANUAL'),
        sa.Column('tracked_as_swing', sa.Boolean(), server_default='true'),
        sa.Column('signal_id', sa.Integer(), sa.ForeignKey('signals.id'), nullable=True),
        sa.Column('mode', sa.String(20), server_default='LIVE'),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('initial_stop', sa.Float(), nullable=False),
        sa.Column('active_stop', sa.Float(), nullable=False),
        sa.Column('target1', sa.Float(), nullable=False),
        sa.Column('status', sa.String(20), server_default='OPEN'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_positions_symbol', 'positions', ['symbol'])

    # 6. fills
    op.create_table(
        'fills',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id'), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('fees_total', sa.Float(), server_default='0.0'),
        sa.Column('fees_json', sa.Text(), nullable=True),
    )

    # 7. journal
    op.create_table(
        'journal',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('position_id', sa.Integer(), sa.ForeignKey('positions.id'), nullable=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), server_default='IN'),
        sa.Column('entry_date', sa.Date(), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('exit_date', sa.Date(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('exit_reason', sa.String(100), nullable=False),
        sa.Column('pnl_amount', sa.Float(), nullable=False),
        sa.Column('pnl_pct', sa.Float(), nullable=False),
        sa.Column('r_multiple', sa.Float(), nullable=False),
        sa.Column('holding_days', sa.Integer(), server_default='0'),
        sa.Column('fees_total', sa.Float(), server_default='0.0'),
        sa.Column('mae', sa.Float(), nullable=True),
        sa.Column('mfe', sa.Float(), nullable=True),
        sa.Column('tags', sa.String(200), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
    )

    # 8. alerts
    op.create_table(
        'alerts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=True),
        sa.Column('market', sa.String(10), server_default='IN'),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=True),
        sa.Column('delivered_telegram', sa.Boolean(), server_default='false'),
        sa.Column('acknowledged', sa.Boolean(), server_default='false'),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('last_reminder_ts', sa.DateTime(timezone=True), nullable=True),
    )

    # 9. news_events
    op.create_table(
        'news_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('source_id', sa.String(100), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('url', sa.String(500), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('severity', sa.String(20), server_default='GREEN'),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('dedupe_key', sa.String(100), nullable=False),
        sa.Column('canonical_event_id', sa.String(100), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('raw_json', sa.Text(), nullable=True),
        sa.Column('match_confidence', sa.String(20), server_default='EXACT_NAME'),
        sa.Column('is_unverified', sa.Boolean(), server_default='false'),
        sa.Column('syndication_cluster_id', sa.String(100), nullable=True),
        sa.Column('materiality', sa.String(20), server_default='LOW'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('price_change_day_pct', sa.Float(), nullable=True),
        sa.Column('price_atr_multiple', sa.Float(), nullable=True),
        sa.Column('analyst_action_json', sa.Text(), nullable=True),
    )
    op.create_index('ix_news_events_symbol', 'news_events', ['symbol'])
    op.create_index('ix_news_events_dedupe_key', 'news_events', ['dedupe_key'])
    op.create_index('ix_news_events_cluster', 'news_events', ['syndication_cluster_id'])

    # 10. news_source_state
    op.create_table(
        'news_source_state',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False, unique=True),
        sa.Column('latency_class', sa.String(30), nullable=False, server_default='near-real-time'),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('etag', sa.String(100), nullable=True),
        sa.Column('last_modified', sa.String(100), nullable=True),
        sa.Column('backoff_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('items_last_poll', sa.Integer(), server_default='0'),
        sa.Column('median_latency_sec', sa.Float(), server_default='0.0'),
        sa.Column('status', sa.String(20), server_default='HEALTHY'),
    )
    op.create_index('ix_news_source_state_source', 'news_source_state', ['source'])

    # 11. company_relationships
    op.create_table(
        'company_relationships',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('watched_symbol', sa.String(50), nullable=False),
        sa.Column('related_entity', sa.String(100), nullable=False),
        sa.Column('relationship_type', sa.String(30), nullable=False),
        sa.Column('evidence_url', sa.String(500), nullable=True),
        sa.Column('evidence_note', sa.Text(), nullable=True),
        sa.Column('last_reviewed', sa.Date(), nullable=False),
        sa.Column('confidence', sa.Float(), server_default='1.0'),
        sa.Column('status', sa.String(20), server_default='ACTIVE'),
    )
    op.create_index('ix_company_rel_watched', 'company_relationships', ['watched_symbol'])

    # 12. news_coverage_gaps
    op.create_table(
        'news_coverage_gaps',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('gap_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('gap_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_sec', sa.Float(), server_default='0.0'),
        sa.Column('status', sa.String(20), server_default='RECORDED'),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_index('ix_news_gaps_source', 'news_coverage_gaps', ['source'])

    # 13. earnings_filings
    op.create_table(
        'earnings_filings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('period_type', sa.String(20), nullable=False),
        sa.Column('period_ended', sa.Date(), nullable=False),
        sa.Column('filing_date', sa.Date(), nullable=False),
        sa.Column('revenue', sa.Float(), nullable=False),
        sa.Column('operating_profit', sa.Float(), nullable=True),
        sa.Column('net_profit', sa.Float(), nullable=False),
        sa.Column('eps', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(10), server_default='INR'),
        sa.Column('source_name', sa.String(50), nullable=False),
        sa.Column('source_url', sa.String(500), nullable=False),
        sa.Column('consensus_eps', sa.Float(), nullable=True),
        sa.Column('consensus_source', sa.String(50), nullable=True),
        sa.Column('severity', sa.String(20), server_default='CLEAR'),
        sa.Column('flags_json', sa.Text(), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_earnings_filings_symbol', 'earnings_filings', ['symbol'])

    # 14. news_coverage
    op.create_table(
        'news_coverage',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scan_id', sa.Integer(), sa.ForeignKey('scans.id'), nullable=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), server_default='UNKNOWN'),
        sa.Column('sources_checked_json', sa.Text(), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_news_coverage_symbol', 'news_coverage', ['symbol'])

    # 15. macro_events
    op.create_table(
        'macro_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('region', sa.String(10), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('importance', sa.String(20), server_default='HIGH'),
        sa.Column('source', sa.String(50), nullable=True),
    )

    # 16. imported_reports
    op.create_table(
        'imported_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('file_hash', sa.String(100), unique=True, nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('row_count', sa.Integer(), server_default='0'),
    )

    # 17. report_trades
    op.create_table(
        'report_trades',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('report_id', sa.Integer(), sa.ForeignKey('imported_reports.id'), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('charges_json', sa.Text(), nullable=True),
    )

    # 18. backtest_runs
    op.create_table(
        'backtest_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('universe', sa.String(100), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('metrics_json', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='PENDING'),
    )

    # 19. backtest_trades
    op.create_table(
        'backtest_trades',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('backtest_runs.id'), nullable=False),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('setup', sa.String(20), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('exit_date', sa.Date(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=False),
        sa.Column('exit_reason', sa.String(50), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('pnl', sa.Float(), nullable=False),
        sa.Column('r_multiple', sa.Float(), nullable=False),
        sa.Column('costs', sa.Float(), server_default='0.0'),
    )

    # 20. broker_snapshots
    op.create_table(
        'broker_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('broker', sa.String(50), nullable=False),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
    )

    # 21. settings_kv
    op.create_table(
        'settings_kv',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value_json', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 22. job_runs
    op.create_table(
        'job_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('job', sa.String(100), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), server_default='RUNNING'),
        sa.Column('detail', sa.Text(), nullable=True),
    )

    # 23. decision_audits
    op.create_table(
        'decision_audits',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(50), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('asof_date', sa.Date(), nullable=False),
        sa.Column('mode', sa.String(20), nullable=False, server_default='LIVE'),
        sa.Column('final_decision', sa.String(20), nullable=False),
        sa.Column('setup', sa.String(30), nullable=True),
        sa.Column('trigger', sa.Float(), nullable=True),
        sa.Column('stop', sa.Float(), nullable=True),
        sa.Column('target1', sa.Float(), nullable=True),
        sa.Column('qty', sa.Integer(), nullable=True),
        sa.Column('risk_amount', sa.Float(), nullable=True),
        sa.Column('cost_in_r', sa.Float(), nullable=True),
        sa.Column('config_hash', sa.String(64), nullable=True),
        sa.Column('code_version', sa.String(20), server_default='2.3'),
        sa.Column('data_source', sa.String(50), server_default='ANGEL_ONE'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_decision_audits_symbol', 'decision_audits', ['symbol'])

    # 24. decision_stage_results
    op.create_table(
        'decision_stage_results',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('audit_id', sa.Integer(), sa.ForeignKey('decision_audits.id'), nullable=False),
        sa.Column('stage_name', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('checks_json', sa.Text(), nullable=False),
        sa.Column('rejection_reasons_json', sa.Text(), nullable=True),
    )
    op.create_index('ix_stage_results_audit', 'decision_stage_results', ['audit_id'])


def downgrade() -> None:
    tables = [
        'decision_stage_results', 'decision_audits', 'job_runs', 'settings_kv',
        'broker_snapshots', 'backtest_trades', 'backtest_runs', 'report_trades',
        'imported_reports', 'macro_events', 'news_coverage', 'earnings_filings',
        'news_coverage_gaps', 'company_relationships', 'news_source_state',
        'news_events', 'alerts', 'journal', 'fills', 'positions', 'signals',
        'scans', 'bars_daily', 'instruments',
    ]
    for table in tables:
        op.drop_table(table)
