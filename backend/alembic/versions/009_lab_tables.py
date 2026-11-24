"""Strategy Lab tables: strategies, runs, results, trades, studies, paper tracking.

Revision ID: 009_lab_tables
Revises: 008_paper_run_type
"""
from alembic import op
import sqlalchemy as sa


revision = "009_lab_tables"
down_revision = "008_paper_run_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Strategy Registry (sync copy of swing_registry.yaml) ---
    op.create_table(
        "lab_strategies",
        sa.Column("id", sa.String(10), primary_key=True),          # S01..S10
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("parameters_json", sa.Text, nullable=False),      # JSON blob
        sa.Column("config_hash", sa.String(64), nullable=False),    # SHA-256 of params
        sa.Column("min_history_bars", sa.Integer, default=70, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # --- Backtest Runs (job queue) ---
    op.create_table(
        "lab_runs",
        sa.Column("id", sa.String(64), primary_key=True),          # UUID
        sa.Column("strategy_id", sa.String(10), nullable=False, index=True),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("capital", sa.Float, nullable=False, default=500000.0),
        sa.Column("risk_pct", sa.Float, nullable=False, default=0.5),
        sa.Column("max_positions", sa.Integer, nullable=False, default=5),
        sa.Column("config_hash", sa.String(64), nullable=False),    # hash of strategy + run params
        sa.Column("status", sa.String(20), nullable=False, default="PENDING"),  # PENDING|RUNNING|DONE|FAILED
        sa.Column("progress_pct", sa.Integer, nullable=False, default=0),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_start_date", sa.Date, nullable=True),
        sa.Column("data_end_date", sa.Date, nullable=True),
        sa.Column("universe_symbols", sa.Integer, nullable=True),
    )
    op.create_index("ix_lab_runs_strategy_holding", "lab_runs", ["strategy_id", "holding_days"])
    op.create_index("ix_lab_runs_config_hash", "lab_runs", ["config_hash"])

    # --- Backtest Results (per strategy/holding summary) ---
    op.create_table(
        "lab_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False, index=True),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        # Core metrics
        sa.Column("total_trades", sa.Integer, nullable=False, default=0),
        sa.Column("win_rate", sa.Float, nullable=True),
        sa.Column("expectancy_r", sa.Float, nullable=True),          # median net expectancy in R
        sa.Column("median_net_expectancy", sa.Float, nullable=True), # explicit median column
        sa.Column("avg_win_r", sa.Float, nullable=True),
        sa.Column("avg_loss_r", sa.Float, nullable=True),
        sa.Column("profit_factor", sa.Float, nullable=True),
        sa.Column("cagr_pct", sa.Float, nullable=True),
        sa.Column("max_drawdown_pct", sa.Float, nullable=True),
        sa.Column("sharpe_ratio", sa.Float, nullable=True),
        sa.Column("total_pnl", sa.Float, nullable=True),
        sa.Column("total_costs", sa.Float, nullable=True),
        # Sample sufficiency
        sa.Column("sample_ok", sa.Boolean, nullable=False, default=False),  # >= 100 trades
        sa.Column("sample_label", sa.String(50), nullable=True),    # SUFFICIENT|INSUFFICIENT_SAMPLE
        # Half-consistency (tie-break)
        sa.Column("half1_expectancy", sa.Float, nullable=True),
        sa.Column("half2_expectancy", sa.Float, nullable=True),
        sa.Column("half_consistency", sa.Float, nullable=True),     # min(h1,h2)/max(h1,h2)
        # Full metrics JSON for display
        sa.Column("metrics_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lab_results_strategy_holding", "lab_results", ["strategy_id", "holding_days"])

    # --- Backtest Trades (individual trade records) ---
    op.create_table(
        "lab_trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False, index=True),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False, index=True),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("exit_date", sa.Date, nullable=True),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("stop_price", sa.Float, nullable=True),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("gross_pnl", sa.Float, nullable=True),
        sa.Column("costs", sa.Float, nullable=True),
        sa.Column("net_pnl", sa.Float, nullable=True),
        sa.Column("r_multiple", sa.Float, nullable=True),
        sa.Column("exit_reason", sa.String(100), nullable=True),
        sa.Column("holding_days_actual", sa.Integer, nullable=True),
    )
    op.create_index("ix_lab_trades_run_strategy", "lab_trades", ["run_id", "strategy_id"])

    # --- Forward Paper Studies (frozen snapshots) ---
    op.create_table(
        "lab_studies",
        sa.Column("id", sa.String(64), primary_key=True),          # UUID
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="ACTIVE"),  # ACTIVE|PAUSED|COMPLETED
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("planned_end_date", sa.Date, nullable=True),
        sa.Column("capital", sa.Float, nullable=False, default=500000.0),
        sa.Column("risk_pct", sa.Float, nullable=False, default=0.5),
        sa.Column("max_positions", sa.Integer, nullable=False, default=5),
        sa.Column("strategies_json", sa.Text, nullable=False),      # frozen config snapshot
        sa.Column("kill_switch_threshold_pct", sa.Float, nullable=False, default=10.0),
        sa.Column("kill_switch_triggered", sa.Boolean, nullable=False, default=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Study Strategies (which strategies are in which study) ---
    op.create_table(
        "lab_study_strategies",
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", sa.String(10), nullable=False),
        sa.Column("holding_days", sa.Integer, nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),    # frozen config
        sa.Column("parameters_json", sa.Text, nullable=False),      # frozen params at study start
    )
    op.create_index("ix_lab_study_strategies_study", "lab_study_strategies", ["study_id"])

    # --- Forward Paper Holdings (per-strategy live positions) ---
    op.create_table(
        "lab_paper_holdings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False, index=True),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("stop_price", sa.Float, nullable=True),
        sa.Column("avg_cost", sa.Float, nullable=False),
        sa.Column("invested_cost", sa.Float, nullable=False),
        sa.Column("unrealized_pnl", sa.Float, nullable=True, default=0.0),
    )
    op.create_index("ix_lab_paper_holdings_study_strategy", "lab_paper_holdings", ["study_id", "strategy_id"])

    # --- Forward Paper Trades (immutable execution log) ---
    op.create_table(
        "lab_paper_trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False, index=True),
        sa.Column("symbol", sa.String(50), nullable=False, index=True),
        sa.Column("side", sa.String(10), nullable=False),           # BUY|SELL
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("exec_date", sa.Date, nullable=False),
        sa.Column("fill_price", sa.Float, nullable=False),
        sa.Column("gross_turnover", sa.Float, nullable=False),
        sa.Column("costs_json", sa.Text, nullable=True),
        sa.Column("net_cash_delta", sa.Float, nullable=False),
        sa.Column("realized_pnl", sa.Float, nullable=True, default=0.0),
        sa.Column("r_multiple", sa.Float, nullable=True),
        sa.Column("exit_reason", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lab_paper_trades_study_strategy", "lab_paper_trades", ["study_id", "strategy_id"])

    # --- Forward Paper Daily History (equity curve, per strategy per day) ---
    op.create_table(
        "lab_paper_daily",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("study_id", sa.String(64), sa.ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False, index=True),
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("cash", sa.Float, nullable=False),
        sa.Column("invested_value", sa.Float, nullable=False),
        sa.Column("total_equity", sa.Float, nullable=False),
        sa.Column("peak_equity", sa.Float, nullable=False),
        sa.Column("drawdown_pct", sa.Float, nullable=False, default=0.0),
        sa.Column("cumulative_return_pct", sa.Float, nullable=False, default=0.0),
        sa.Column("realized_pnl", sa.Float, nullable=False, default=0.0),
        sa.Column("unrealized_pnl", sa.Float, nullable=False, default=0.0),
        sa.Column("open_positions", sa.Integer, nullable=False, default=0),
        sa.Column("trades_today", sa.Integer, nullable=False, default=0),
        sa.Column("cumulative_costs", sa.Float, nullable=False, default=0.0),
        sa.Column("benchmark_close", sa.Float, nullable=True),
        sa.Column("benchmark_return_pct", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_lab_paper_daily_study_strategy_date", "lab_paper_daily", ["study_id", "strategy_id", "session_date"])

    # --- Manual Promotion Plan (daily trading plan items) ---
    op.create_table(
        "lab_plan_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("plan_date", sa.Date, nullable=False, index=True),
        sa.Column("strategy_id", sa.String(10), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),         # BUY|SELL|WATCH
        sa.Column("suggested_entry", sa.Float, nullable=True),
        sa.Column("suggested_stop", sa.Float, nullable=True),
        sa.Column("suggested_qty", sa.Integer, nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="PENDING"),  # PENDING|EXECUTED|SKIPPED
        sa.Column("executed_price", sa.Float, nullable=True),
        sa.Column("executed_qty", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lab_plan_items")
    op.drop_index("ix_lab_paper_daily_study_strategy_date", table_name="lab_paper_daily")
    op.drop_table("lab_paper_daily")
    op.drop_index("ix_lab_paper_trades_study_strategy", table_name="lab_paper_trades")
    op.drop_table("lab_paper_trades")
    op.drop_index("ix_lab_paper_holdings_study_strategy", table_name="lab_paper_holdings")
    op.drop_table("lab_paper_holdings")
    op.drop_index("ix_lab_study_strategies_study", table_name="lab_study_strategies")
    op.drop_table("lab_study_strategies")
    op.drop_table("lab_studies")
    op.drop_index("ix_lab_trades_run_strategy", table_name="lab_trades")
    op.drop_table("lab_trades")
    op.drop_index("ix_lab_results_strategy_holding", table_name="lab_results")
    op.drop_table("lab_results")
    op.drop_index("ix_lab_runs_config_hash", table_name="lab_runs")
    op.drop_index("ix_lab_runs_strategy_holding", table_name="lab_runs")
    op.drop_table("lab_runs")
    op.drop_table("lab_strategies")
