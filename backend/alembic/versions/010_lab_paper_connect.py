"""Migration 010: Add missing trade fields, is_test column, lab_tomorrow_orders, lab_evaluations.

Revision ID: 010_lab_paper_connect
Revises: 009_lab_tables
"""
from alembic import op
import sqlalchemy as sa


revision = "010_lab_paper_connect"
down_revision = "009_lab_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. lab_studies: add is_test flag ──────────────────────────────────────
    op.add_column("lab_studies", sa.Column("is_test", sa.Boolean, nullable=False, server_default="false"))

    # ── 2. lab_trades: add missing fields ─────────────────────────────────────
    # signal_date, reason_text, signal_context_json, planned_exit_date, data_through_date
    op.add_column("lab_trades", sa.Column("signal_date", sa.Date, nullable=True))
    op.add_column("lab_trades", sa.Column("planned_exit_date", sa.Date, nullable=True))
    op.add_column("lab_trades", sa.Column("reason_text", sa.Text, nullable=True))
    op.add_column("lab_trades", sa.Column("signal_context_json", sa.Text, nullable=True))
    op.add_column("lab_trades", sa.Column("data_through_date", sa.Date, nullable=True))

    # ── 3. lab_paper_trades: add all required fields ───────────────────────────
    # Deterministic trade key, signal fields, entry/exit enrichment, context
    op.add_column("lab_paper_trades", sa.Column(
        "trade_key", sa.String(128), nullable=True,
        comment="SHA-256(study_id|strategy_id|config_hash|symbol|entry_date)"
    ))
    op.add_column("lab_paper_trades", sa.Column("config_hash", sa.String(64), nullable=True))
    op.add_column("lab_paper_trades", sa.Column("signal_date", sa.Date, nullable=True))
    op.add_column("lab_paper_trades", sa.Column("stop_price", sa.Float, nullable=True))
    op.add_column("lab_paper_trades", sa.Column("planned_exit_date", sa.Date, nullable=True))
    op.add_column("lab_paper_trades", sa.Column("gross_pnl", sa.Float, nullable=True, server_default="0"))
    op.add_column("lab_paper_trades", sa.Column("net_pnl", sa.Float, nullable=True, server_default="0"))
    op.add_column("lab_paper_trades", sa.Column("reason_text", sa.Text, nullable=True))
    op.add_column("lab_paper_trades", sa.Column("signal_context_json", sa.Text, nullable=True))
    op.add_column("lab_paper_trades", sa.Column("data_through_date", sa.Date, nullable=True))
    op.add_column("lab_paper_trades", sa.Column("holding_days_target", sa.Integer, nullable=True))

    # Unique index on trade_key (partial — only for non-null keys)
    op.create_index(
        "ix_lab_paper_trades_trade_key",
        "lab_paper_trades",
        ["trade_key"],
        unique=True,
        postgresql_where=sa.text("trade_key IS NOT NULL"),
    )

    # ── 4. lab_paper_holdings: add uniqueness constraint ──────────────────────
    op.create_unique_constraint(
        "uq_lab_paper_holdings_study_strategy_symbol",
        "lab_paper_holdings",
        ["study_id", "strategy_id", "symbol"],
    )

    # ── 5. lab_paper_daily: add uniqueness constraint ─────────────────────────
    op.create_unique_constraint(
        "uq_lab_paper_daily_study_strategy_date",
        "lab_paper_daily",
        ["study_id", "strategy_id", "session_date"],
    )

    # ── 6. lab_tomorrow_orders: planned next-session orders ───────────────────
    op.create_table(
        "lab_tomorrow_orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("order_key", sa.String(128), nullable=False),   # deterministic
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("signal_date", sa.Date, nullable=False),
        sa.Column("signal_reason", sa.Text, nullable=True),
        sa.Column("signal_context_json", sa.Text, nullable=True),
        sa.Column("planned_entry", sa.Float, nullable=False),     # next-open est
        sa.Column("stop_price", sa.Float, nullable=True),
        sa.Column("research_qty", sa.Integer, nullable=True),     # ₹500k capital
        sa.Column("practical_qty", sa.Integer, nullable=True),    # ₹17,500 capital
        sa.Column("planned_exit_date", sa.Date, nullable=True),
        sa.Column("holding_days_target", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="PENDING"),
        sa.Column("data_through_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_lab_tomorrow_orders_key", "lab_tomorrow_orders", ["order_key"])
    op.create_index("ix_lab_tomorrow_orders_study", "lab_tomorrow_orders", ["study_id"])

    # ── 7. lab_evaluations: audit log ─────────────────────────────────────────
    op.create_table(
        "lab_evaluations",
        sa.Column("id", sa.String(64), primary_key=True),         # UUID
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_through_date", sa.Date, nullable=True),
        sa.Column("registry_hash", sa.String(64), nullable=True),
        sa.Column("engine_version", sa.String(32), nullable=True),
        sa.Column("trade_count", sa.Integer, nullable=True),
        sa.Column("open_count", sa.Integer, nullable=True),
        sa.Column("equity_row_count", sa.Integer, nullable=True),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_lab_evaluations_study_started", "lab_evaluations", ["study_id", "started_at"])

    # ── 8. lab_paper_benchmarks: random control + NIFTYBEES ───────────────────
    op.create_table(
        "lab_paper_benchmarks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("benchmark_type", sa.String(30), nullable=False),   # RANDOM_CONTROL | NIFTYBEES
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("equity", sa.Float, nullable=False),
        sa.Column("cumulative_return_pct", sa.Float, nullable=True),
        sa.Column("benchmark_close", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_unique_constraint(
        "uq_lab_benchmarks_study_type_date",
        "lab_paper_benchmarks",
        ["study_id", "benchmark_type", "session_date"],
    )


def downgrade() -> None:
    op.drop_table("lab_paper_benchmarks")
    op.drop_table("lab_evaluations")
    op.drop_index("ix_lab_tomorrow_orders_study", table_name="lab_tomorrow_orders")
    op.drop_constraint("uq_lab_tomorrow_orders_key", "lab_tomorrow_orders", type_="unique")
    op.drop_table("lab_tomorrow_orders")
    op.drop_constraint("uq_lab_paper_daily_study_strategy_date", "lab_paper_daily", type_="unique")
    op.drop_constraint("uq_lab_paper_holdings_study_strategy_symbol", "lab_paper_holdings", type_="unique")
    op.drop_index("ix_lab_paper_trades_trade_key", table_name="lab_paper_trades")
    for col in ["trade_key", "config_hash", "signal_date", "stop_price", "planned_exit_date",
                "gross_pnl", "net_pnl", "reason_text", "signal_context_json", "data_through_date",
                "holding_days_target"]:
        op.drop_column("lab_paper_trades", col)
    for col in ["signal_date", "planned_exit_date", "reason_text", "signal_context_json", "data_through_date"]:
        op.drop_column("lab_trades", col)
    op.drop_column("lab_studies", "is_test")
