"""Add Cycle 4 forward paper-trading persistence tables.

Revision ID: 007_cycle4_paper_trading
Revises: 006_position_tranche_and_fills
"""
from alembic import op
import sqlalchemy as sa


revision = "007_cycle4_paper_trading"
down_revision = "006_position_tranche_and_fills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. paper_accounts table
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("initial_capital", sa.Float(), server_default="17500.0", nullable=False),
        sa.Column("cash", sa.Float(), server_default="17500.0", nullable=False),
        sa.Column("total_equity", sa.Float(), server_default="17500.0", nullable=False),
        sa.Column("peak_equity", sa.Float(), server_default="17500.0", nullable=False),
        sa.Column("realized_pnl", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("cumulative_costs_paid", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("last_processed_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("strategy_id", name="uq_paper_accounts_strategy_id"),
    )
    op.create_index("ix_paper_accounts_strategy_id", "paper_accounts", ["strategy_id"])

    # 2. paper_daily_history table
    op.create_table(
        "paper_daily_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("invested_value", sa.Float(), nullable=False),
        sa.Column("total_equity", sa.Float(), nullable=False),
        sa.Column("peak_equity", sa.Float(), nullable=False),
        sa.Column("drawdown_pct", sa.Float(), nullable=False),
        sa.Column("cumulative_return_pct", sa.Float(), nullable=False),
        sa.Column("cumulative_costs", sa.Float(), nullable=False),
        sa.Column("cost_pct_of_capital", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("holdings_count", sa.Integer(), nullable=False),
        sa.Column("benchmark_close", sa.Float(), nullable=True),
        sa.Column("benchmark_daily_return", sa.Float(), nullable=True),
        sa.Column("regime_status", sa.String(length=100), nullable=True),
        sa.Column("valuation_status", sa.String(length=100), nullable=True),
        sa.Column("is_complete_valuation", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("missing_price_symbols", sa.Text(), nullable=True),
        sa.Column("stale_price_carry_forwards", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("strategy_id", "session_date", name="uq_paper_daily_strategy_date"),
    )
    op.create_index("idx_paper_daily_strat_date", "paper_daily_history", ["strategy_id", "session_date"])
    op.create_index("ix_paper_daily_history_strategy_id", "paper_daily_history", ["strategy_id"])
    op.create_index("ix_paper_daily_history_session_date", "paper_daily_history", ["session_date"])

    # 3. paper_orders table
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("order_type", sa.String(length=20), server_default="MARKET", nullable=False),
        sa.Column("requested_shares", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("exec_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("order_id", name="uq_paper_orders_order_id"),
    )
    op.create_index("ix_paper_orders_order_id", "paper_orders", ["order_id"])
    op.create_index("ix_paper_orders_strategy_id", "paper_orders", ["strategy_id"])
    op.create_index("ix_paper_orders_symbol", "paper_orders", ["symbol"])

    # 4. paper_trades table
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trade_id", sa.String(length=100), nullable=False),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("exec_date", sa.Date(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("ref_open", sa.Float(), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=False),
        sa.Column("gross_turnover", sa.Float(), nullable=False),
        sa.Column("costs_json", sa.Text(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("net_cash_delta", sa.Float(), nullable=False),
        sa.Column("realized_pnl", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("regime_pass", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("trade_id", name="uq_paper_trades_trade_id"),
    )
    op.create_index("ix_paper_trades_trade_id", "paper_trades", ["trade_id"])
    op.create_index("ix_paper_trades_order_id", "paper_trades", ["order_id"])
    op.create_index("ix_paper_trades_strategy_id", "paper_trades", ["strategy_id"])
    op.create_index("ix_paper_trades_symbol", "paper_trades", ["symbol"])
    op.create_index("ix_paper_trades_exec_date", "paper_trades", ["exec_date"])

    # 5. paper_holdings table
    op.create_table(
        "paper_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("avg_cost", sa.Float(), nullable=False),
        sa.Column("invested_cost", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("strategy_id", "symbol", name="uq_paper_holding_strat_symbol"),
    )
    op.create_index("ix_paper_holdings_strategy_id", "paper_holdings", ["strategy_id"])
    op.create_index("ix_paper_holdings_symbol", "paper_holdings", ["symbol"])

    # 6. paper_rebalance_audits table
    op.create_table(
        "paper_rebalance_audits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("is_bull_regime", sa.Boolean(), nullable=False),
        sa.Column("nsei_close", sa.Float(), nullable=False),
        sa.Column("nsei_sma200", sa.Float(), nullable=False),
        sa.Column("candidate_targets_json", sa.Text(), nullable=False),
        sa.Column("control_targets_json", sa.Text(), nullable=False),
        sa.Column("candidate_top5_json", sa.Text(), nullable=True),
        sa.Column("control_top5_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_paper_rebalance_audits_signal_date", "paper_rebalance_audits", ["signal_date"])


def downgrade() -> None:
    op.drop_table("paper_rebalance_audits")
    op.drop_table("paper_holdings")
    op.drop_table("paper_trades")
    op.drop_table("paper_orders")
    op.drop_table("paper_daily_history")
    op.drop_table("paper_accounts")
