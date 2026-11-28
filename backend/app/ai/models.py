"""
AI Agent DB Models

Three new tables:
  ai_agent_executions     — raw per-agent execution log
  ai_research_assessments — final synthesized research assessments
  ai_provider_usage       — daily API quota accounting (conservative local tracking)

Imported from app/models.py so Alembic and Base.metadata discover them.
"""

from __future__ import annotations

import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Date,
    ForeignKey,
    Index,
    func,
)
from app.db import Base


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class AiAgentExecution(Base):
    """
    One row per agent invocation.
    output_json stores the full Pydantic model serialized as JSON.
    """
    __tablename__ = "ai_agent_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String(50), nullable=False, index=True)
    # e.g. news_intelligence, company_research, market_context,
    #      technical_research, risk_review, final_decision

    symbol = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="IN")
    input_hash = Column(String(64), nullable=False, index=True)
    # sha256 of the key inputs — used for cache deduplication

    provider = Column(String(50), nullable=False)  # google_gemini | nvidia (dev only)
    model_id = Column(String(100), nullable=False)
    prompt_version = Column(String(20), nullable=False, default="1.0")
    input_record_ids = Column(Text, nullable=True)  # JSON array of NewsEvent IDs etc.
    output_json = Column(Text, nullable=True)        # Full Pydantic model JSON
    validation_status = Column(String(20), nullable=False, default="PENDING")
    # VALID | INVALID | SCHEMA_ERROR | PROVIDER_ERROR | SKIPPED

    generated_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now())
    latency_sec = Column(Float, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    error_code = Column(String(50), nullable=True)
    is_valid = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("idx_ai_exec_agent_sym", "agent_name", "symbol"),
        Index("idx_ai_exec_hash", "input_hash"),
        Index("idx_ai_exec_generated", "generated_at"),
    )


class AiResearchAssessment(Base):
    """
    Final synthesized research assessment for a symbol.
    One active assessment per symbol at any time; prior ones are superseded.
    """
    __tablename__ = "ai_research_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    market = Column(String(10), nullable=False, default="IN")
    final_status = Column(String(30), nullable=False)
    # WATCH | MONITOR | REJECT | INSUFFICIENT_DATA

    summary = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=True)   # JSON array of EvidenceRecord
    risks_json = Column(Text, nullable=True)       # JSON array of what_would_change
    confidence = Column(Float, nullable=True)      # None by design — no numeric score
    requires_human_review = Column(Boolean, nullable=False, default=False)
    generated_at = Column(DateTime(timezone=True), default=utc_now, server_default=func.now())
    agent_execution_id = Column(Integer, ForeignKey("ai_agent_executions.id"), nullable=True)
    superseded_by = Column(Integer, ForeignKey("ai_research_assessments.id"), nullable=True)

    __table_args__ = (
        Index("idx_ai_assess_sym_mkt", "symbol", "market"),
        Index("idx_ai_assess_status", "final_status"),
        Index("idx_ai_assess_generated", "generated_at"),
    )


class AiProviderUsage(Base):
    """
    Conservative local daily accounting of API requests.
    Not authoritative vs. provider billing. Used for quota guard.
    """
    __tablename__ = "ai_provider_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    model_id = Column(String(100), nullable=False)
    reserved_count = Column(Integer, nullable=False, default=0)
    request_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    total_input_tokens = Column(Integer, nullable=False, default=0)
    total_output_tokens = Column(Integer, nullable=False, default=0)
    quota_exhausted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_ai_usage_date_provider", "date", "provider"),
        Index("uq_ai_usage_date_prov_model", "date", "provider", "model_id", unique=True),
    )
