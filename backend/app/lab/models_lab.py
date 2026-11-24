"""Strategy Lab ORM Models — appended to backend/app/models.py via import."""
# This file is imported in models.py. All lab models live here.

import datetime
import json
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, Index, func,
)
from app.db import Base


class LabStrategy(Base):
    """Canonical strategy registry — synchronized from swing_registry.yaml."""
    __tablename__ = "lab_strategies"

    id = Column(String(10), primary_key=True)          # S01..S10
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    parameters_json = Column(Text, nullable=False)
    config_hash = Column(String(64), nullable=False)
    min_history_bars = Column(Integer, default=70, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    @property
    def parameters(self) -> dict:
        return json.loads(self.parameters_json) if self.parameters_json else {}


class LabRun(Base):
    """Backtest job queue entry."""
    __tablename__ = "lab_runs"

    id = Column(String(64), primary_key=True)          # UUID4
    strategy_id = Column(String(10), nullable=False, index=True)
    holding_days = Column(Integer, nullable=False)
    capital = Column(Float, nullable=False, default=500000.0)
    risk_pct = Column(Float, nullable=False, default=0.5)
    max_positions = Column(Integer, nullable=False, default=5)
    config_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    progress_pct = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    data_start_date = Column(Date, nullable=True)
    data_end_date = Column(Date, nullable=True)
    universe_symbols = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_lab_runs_strategy_holding", "strategy_id", "holding_days"),
        Index("ix_lab_runs_config_hash", "config_hash"),
    )


class LabResult(Base):
    """Summary metrics for a completed backtest run."""
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False, index=True)
    holding_days = Column(Integer, nullable=False)
    config_hash = Column(String(64), nullable=False)
    total_trades = Column(Integer, nullable=False, default=0)
    win_rate = Column(Float, nullable=True)
    expectancy_r = Column(Float, nullable=True)
    median_net_expectancy = Column(Float, nullable=True)
    avg_win_r = Column(Float, nullable=True)
    avg_loss_r = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    cagr_pct = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    total_pnl = Column(Float, nullable=True)
    total_costs = Column(Float, nullable=True)
    sample_ok = Column(Boolean, nullable=False, default=False)
    sample_label = Column(String(50), nullable=True)
    half1_expectancy = Column(Float, nullable=True)
    half2_expectancy = Column(Float, nullable=True)
    half_consistency = Column(Float, nullable=True)
    metrics_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    __table_args__ = (
        Index("ix_lab_results_strategy_holding", "strategy_id", "holding_days"),
    )

    @property
    def metrics(self) -> dict:
        return json.loads(self.metrics_json) if self.metrics_json else {}


class LabTrade(Base):
    """Individual backtest trade record."""
    __tablename__ = "lab_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False, index=True)
    holding_days = Column(Integer, nullable=False)
    symbol = Column(String(50), nullable=False, index=True)
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=True)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    qty = Column(Integer, nullable=False)
    gross_pnl = Column(Float, nullable=True)
    costs = Column(Float, nullable=True)
    net_pnl = Column(Float, nullable=True)
    r_multiple = Column(Float, nullable=True)
    exit_reason = Column(String(100), nullable=True)
    holding_days_actual = Column(Integer, nullable=True)
    # Fields added in migration 010
    signal_date = Column(Date, nullable=True)
    planned_exit_date = Column(Date, nullable=True)
    reason_text = Column(Text, nullable=True)
    signal_context_json = Column(Text, nullable=True)
    data_through_date = Column(Date, nullable=True)

    __table_args__ = (
        Index("ix_lab_trades_run_strategy", "run_id", "strategy_id"),
    )


class LabStudy(Base):
    """Forward paper trading study snapshot (frozen configuration)."""
    __tablename__ = "lab_studies"

    id = Column(String(64), primary_key=True)
    name = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    start_date = Column(Date, nullable=False)
    planned_end_date = Column(Date, nullable=True)
    capital = Column(Float, nullable=False, default=500000.0)
    risk_pct = Column(Float, nullable=False, default=0.5)
    max_positions = Column(Integer, nullable=False, default=5)
    strategies_json = Column(Text, nullable=False)
    kill_switch_threshold_pct = Column(Float, nullable=False, default=10.0)
    kill_switch_triggered = Column(Boolean, nullable=False, default=False)
    is_test = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    @property
    def strategies(self) -> list:
        return json.loads(self.strategies_json) if self.strategies_json else []


class LabStudyStrategy(Base):
    """Which strategies (with frozen config) belong to a study."""
    __tablename__ = "lab_study_strategies"

    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), primary_key=True)
    strategy_id = Column(String(10), primary_key=True)
    holding_days = Column(Integer, primary_key=True)
    config_hash = Column(String(64), nullable=False)
    parameters_json = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_lab_study_strategies_study", "study_id"),
    )


class LabPaperHolding(Base):
    """Live forward paper position per strategy."""
    __tablename__ = "lab_paper_holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    qty = Column(Integer, nullable=False)
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=True)
    avg_cost = Column(Float, nullable=False)
    invested_cost = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=True, default=0.0)

    __table_args__ = (
        Index("ix_lab_paper_holdings_study_strategy", "study_id", "strategy_id"),
    )


class LabPaperTrade(Base):
    """Immutable forward paper trade execution record."""
    __tablename__ = "lab_paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    side = Column(String(10), nullable=False)
    qty = Column(Integer, nullable=False)
    exec_date = Column(Date, nullable=False)
    fill_price = Column(Float, nullable=False)
    gross_turnover = Column(Float, nullable=False)
    costs_json = Column(Text, nullable=True)
    net_cash_delta = Column(Float, nullable=False)
    realized_pnl = Column(Float, nullable=True, default=0.0)
    r_multiple = Column(Float, nullable=True)
    exit_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    # Fields added in migration 010
    trade_key = Column(String(128), nullable=True)
    config_hash = Column(String(64), nullable=True)
    signal_date = Column(Date, nullable=True)
    stop_price = Column(Float, nullable=True)
    planned_exit_date = Column(Date, nullable=True)
    gross_pnl = Column(Float, nullable=True, default=0.0)
    net_pnl = Column(Float, nullable=True, default=0.0)
    reason_text = Column(Text, nullable=True)
    signal_context_json = Column(Text, nullable=True)
    data_through_date = Column(Date, nullable=True)
    holding_days_target = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_lab_paper_trades_study_strategy", "study_id", "strategy_id"),
    )


class LabPaperDaily(Base):
    """Daily equity curve per strategy in a study."""
    __tablename__ = "lab_paper_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False, index=True)
    session_date = Column(Date, nullable=False)
    cash = Column(Float, nullable=False)
    invested_value = Column(Float, nullable=False)
    total_equity = Column(Float, nullable=False)
    peak_equity = Column(Float, nullable=False)
    drawdown_pct = Column(Float, nullable=False, default=0.0)
    cumulative_return_pct = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    open_positions = Column(Integer, nullable=False, default=0)
    trades_today = Column(Integer, nullable=False, default=0)
    cumulative_costs = Column(Float, nullable=False, default=0.0)
    benchmark_close = Column(Float, nullable=True)
    benchmark_return_pct = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_lab_paper_daily_study_strategy_date", "study_id", "strategy_id", "session_date"),
    )


class LabPlanItem(Base):
    """Daily manual trading plan item."""
    __tablename__ = "lab_plan_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_date = Column(Date, nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False)
    symbol = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)
    suggested_entry = Column(Float, nullable=True)
    suggested_stop = Column(Float, nullable=True)
    suggested_qty = Column(Integer, nullable=True)
    rationale = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    executed_price = Column(Float, nullable=True)
    executed_qty = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())


# ── New models added in migration 010 ────────────────────────────────────────

class LabTomorrowOrder(Base):
    """Planned next-session entry orders from the paper evaluator."""
    __tablename__ = "lab_tomorrow_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_key = Column(String(128), nullable=False)
    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(String(10), nullable=False)
    config_hash = Column(String(64), nullable=False)
    symbol = Column(String(50), nullable=False)
    signal_date = Column(Date, nullable=False)
    signal_reason = Column(Text, nullable=True)
    signal_context_json = Column(Text, nullable=True)
    planned_entry = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=True)
    research_qty = Column(Integer, nullable=True)
    practical_qty = Column(Integer, nullable=True)
    planned_exit_date = Column(Date, nullable=True)
    holding_days_target = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    data_through_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), server_default=func.now())

    __table_args__ = (
        Index("ix_lab_tomorrow_orders_study", "study_id"),
    )


class LabEvaluation(Base):
    """Audit log of each paper evaluation run."""
    __tablename__ = "lab_evaluations"

    id = Column(String(64), primary_key=True)
    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="RUNNING")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    data_through_date = Column(Date, nullable=True)
    registry_hash = Column(String(64), nullable=True)
    engine_version = Column(String(32), nullable=True)
    trade_count = Column(Integer, nullable=True)
    open_count = Column(Integer, nullable=True)
    equity_row_count = Column(Integer, nullable=True)
    error_detail = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_lab_evaluations_study_started", "study_id", "started_at"),
    )


class LabPaperBenchmark(Base):
    """Daily benchmark equity rows (NIFTYBEES / random control)."""
    __tablename__ = "lab_paper_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    study_id = Column(String(64), ForeignKey("lab_studies.id", ondelete="CASCADE"), nullable=False, index=True)
    benchmark_type = Column(String(30), nullable=False)
    session_date = Column(Date, nullable=False)
    equity = Column(Float, nullable=False)
    cumulative_return_pct = Column(Float, nullable=True)
    benchmark_close = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_lab_paper_benchmarks_study", "study_id"),
    )
