import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    Text,
    PrimaryKeyConstraint,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from app.db import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="IN")  # IN or US
    name = Column(String(200), nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    provider_token = Column(String(50), nullable=True)  # Angel One token, etc.
    active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)


class DailyBar(Base):
    __tablename__ = "bars_daily"

    symbol = Column(String(50), primary_key=True)
    date = Column(Date, primary_key=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    adj_close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    source = Column(String(50), nullable=False)  # angelone, yfinance, alpaca

    __table_args__ = (
        PrimaryKeyConstraint("symbol", "date"),
        Index("idx_bars_symbol_date", "symbol", "date"),
    )


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(10), nullable=False)  # IN, US
    run_at = Column(DateTime, default=datetime.datetime.utcnow)
    session_date = Column(Date, nullable=False)
    regime = Column(String(20), nullable=False)  # Bullish, Caution, Weak
    regime_detail_json = Column(Text, nullable=True)
    universe_size = Column(Integer, default=0)
    passed_filters = Column(Integer, default=0)
    data_warnings_json = Column(Text, nullable=True)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=True)
    symbol = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False)
    setup = Column(String(20), nullable=False)  # VCP, PULLBACK
    trigger = Column(Float, nullable=False)
    entry_zone_high = Column(Float, nullable=False)
    stop = Column(Float, nullable=False)
    target1 = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    risk_amount = Column(Float, nullable=False)
    cost_estimate = Column(Float, nullable=False)
    cost_in_r = Column(Float, nullable=False)
    rs_rank = Column(Float, nullable=False)
    score = Column(Float, nullable=False)
    atr = Column(Float, nullable=False)
    gap95 = Column(Float, nullable=True)
    reasons_json = Column(Text, nullable=True)
    news_flags_json = Column(Text, nullable=True)
    state = Column(
        String(30),
        default="WATCHLIST",
    )  # WATCHLIST, APPROACHING, TRIGGERED_PROVISIONAL, TRIGGERED_CONFIRMED, INVALIDATED, EXTENDED, EXPIRED, SKIPPED
    valid_until = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="IN")
    source = Column(String(20), default="MANUAL")  # MANUAL, KITE
    tracked_as_swing = Column(Boolean, default=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    mode = Column(String(20), default="LIVE")  # LIVE, PAPER
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    initial_stop = Column(Float, nullable=False)
    active_stop = Column(Float, nullable=False)
    target1 = Column(Float, nullable=False)
    status = Column(String(20), default="OPEN")  # OPEN, CLOSED
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Fill(Base):
    __tablename__ = "fills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    side = Column(String(10), nullable=False)  # BUY, SELL
    date = Column(Date, nullable=False)
    price = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    fees_total = Column(Float, default=0.0)
    fees_json = Column(Text, nullable=True)


class Journal(Base):
    __tablename__ = "journal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True)
    symbol = Column(String(50), nullable=False)
    market = Column(String(10), default="IN")
    entry_date = Column(Date, nullable=True)
    entry_price = Column(Float, nullable=True)
    exit_date = Column(Date, nullable=False)
    exit_price = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    exit_reason = Column(String(100), nullable=False)
    pnl_amount = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    r_multiple = Column(Float, nullable=False)
    holding_days = Column(Integer, default=0)
    fees_total = Column(Float, default=0.0)
    mae = Column(Float, nullable=True)
    mfe = Column(Float, nullable=True)
    tags = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.datetime.utcnow)
    type = Column(
        String(30), nullable=False
    )  # BUY, SELL, SELL_HALF, CANCEL, SKIP, NEWS, DATA, SYSTEM
    symbol = Column(String(50), nullable=True)
    market = Column(String(10), default="IN")
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=True)
    delivered_telegram = Column(Boolean, default=False)
    acknowledged = Column(Boolean, default=False)


class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False)  # NSE, BSE, SEC_EDGAR, RSS
    source_id = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=True)
    published_at = Column(DateTime, nullable=False)
    ingested_at = Column(DateTime, default=datetime.datetime.utcnow)
    severity = Column(String(20), default="GREEN")  # RED, AMBER, GREEN
    category = Column(String(50), nullable=True)
    dedupe_key = Column(String(100), nullable=False, index=True)
    canonical_event_id = Column(String(100), nullable=True)
    ai_summary = Column(Text, nullable=True)
    raw_json = Column(Text, nullable=True)


class NewsCoverage(Base):
    __tablename__ = "news_coverage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=True)
    symbol = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="UNKNOWN")  # CLEAR, REVIEW, BLOCKED, UNKNOWN
    sources_checked_json = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=datetime.datetime.utcnow)


class MacroEvent(Base):
    __tablename__ = "macro_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False)
    region = Column(String(10), nullable=False)  # IN, US
    title = Column(String(200), nullable=False)
    importance = Column(String(20), default="HIGH")  # HIGH, MEDIUM, LOW
    source = Column(String(50), nullable=True)


class ImportedReport(Base):
    __tablename__ = "imported_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(50), nullable=False)  # TRADEBOOK, PNL, CHARGES
    file_hash = Column(String(100), unique=True, nullable=False)
    imported_at = Column(DateTime, default=datetime.datetime.utcnow)
    row_count = Column(Integer, default=0)


class ReportTrade(Base):
    __tablename__ = "report_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("imported_reports.id"), nullable=False)
    symbol = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    trade_date = Column(Date, nullable=False)
    charges_json = Column(Text, nullable=True)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    config_json = Column(Text, nullable=True)
    universe = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    metrics_json = Column(Text, nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=False)
    symbol = Column(String(50), nullable=False)
    setup = Column(String(20), nullable=False)
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_date = Column(Date, nullable=False)
    exit_price = Column(Float, nullable=False)
    exit_reason = Column(String(50), nullable=False)
    qty = Column(Integer, nullable=False)
    pnl = Column(Float, nullable=False)
    r_multiple = Column(Float, nullable=False)
    costs = Column(Float, default=0.0)


class BrokerSnapshot(Base):
    __tablename__ = "broker_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.datetime.utcnow)
    broker = Column(String(50), nullable=False)  # ZERODHA_KITE, ANGEL_ONE
    kind = Column(String(50), nullable=False)  # HOLDINGS, POSITIONS, MARGINS, TRADES, ORDERS
    payload_json = Column(Text, nullable=False)


class SettingKV(Base):
    __tablename__ = "settings_kv"

    key = Column(String(100), primary_key=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job = Column(String(100), nullable=False)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="RUNNING")  # RUNNING, SUCCESS, FAILED
    detail = Column(Text, nullable=True)


class DecisionAudit(Base):
    __tablename__ = "decision_audits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="IN")
    asof_date = Column(Date, nullable=False)
    mode = Column(String(20), nullable=False, default="LIVE")  # LIVE, PAPER, BACKTEST
    final_decision = Column(String(20), nullable=False)  # PASS, BLOCK, WAIT
    setup = Column(String(30), nullable=True)
    trigger = Column(Float, nullable=True)
    stop = Column(Float, nullable=True)
    target1 = Column(Float, nullable=True)
    qty = Column(Integer, nullable=True)
    risk_amount = Column(Float, nullable=True)
    cost_in_r = Column(Float, nullable=True)
    config_hash = Column(String(64), nullable=True)
    code_version = Column(String(20), default="2.3")
    data_source = Column(String(50), default="ANGEL_ONE")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class DecisionStageResult(Base):
    __tablename__ = "decision_stage_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(Integer, ForeignKey("decision_audits.id"), nullable=False, index=True)
    stage_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)  # PASS, BLOCK, WAIT
    checks_json = Column(Text, nullable=False)
    rejection_reasons_json = Column(Text, nullable=True)


