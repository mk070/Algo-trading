"""
AI Research Agent Output Schemas
All outputs are strictly informational — no trading execution authority.
Disclaimer: AI Informational Research Only — Not a Trading Directive.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ResearchStatus(str, Enum):
    WATCH = "WATCH"
    MONITOR = "MONITOR"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MaterialityLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ROUTINE_IMMATERIAL = "ROUTINE_IMMATERIAL"


class SentimentLabel(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"


class EventCategory(str, Enum):
    EARNINGS = "EARNINGS"
    REGULATORY = "REGULATORY"
    MANAGEMENT = "MANAGEMENT"
    ACQUISITION = "ACQUISITION"
    LEGAL = "LEGAL"
    DIVIDEND = "DIVIDEND"
    RESTRUCTURING = "RESTRUCTURING"
    MACRO = "MACRO"
    ANALYST = "ANALYST"
    OTHER = "OTHER"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    RUMOR = "RUMOR"
    CONFLICTING = "CONFLICTING"


class AgentName(str, Enum):
    NEWS_INTELLIGENCE = "news_intelligence"
    COMPANY_RESEARCH = "company_research"
    MARKET_CONTEXT = "market_context"
    TECHNICAL_RESEARCH = "technical_research"
    RISK_REVIEW = "risk_review"
    FINAL_DECISION = "final_decision"


# ---------------------------------------------------------------------------
# Base models
# ---------------------------------------------------------------------------

class AgentResponse(BaseModel):
    """Base model for all AI agent outputs."""
    agent_name: AgentName
    symbol: str
    market: str = "IN"
    generated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    model_id: str
    provider: str
    latency_sec: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_valid: bool = True
    validation_warnings: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "AI Informational Research Only — Not a Trading Directive. "
        "Deterministic signals govern all trade recommendations for manual execution."
    )


class EvidenceRecord(BaseModel):
    """A single cited piece of evidence."""
    source_type: str  # NEWS_EVENT, FUNDAMENTAL, TECHNICAL, REGULATORY, MACRO
    source_title: str
    source_url: Optional[str] = None
    pub_timestamp: Optional[datetime.datetime] = None
    extracted_passage: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


# ---------------------------------------------------------------------------
# Agent 1: News Intelligence
# ---------------------------------------------------------------------------

class NewsIntelligenceOutput(AgentResponse):
    agent_name: AgentName = AgentName.NEWS_INTELLIGENCE
    news_event_id: int
    headline: str
    event_category: EventCategory
    sentiment: SentimentLabel
    materiality: MaterialityLevel
    affected_companies: List[str] = Field(default_factory=list)
    summary: str  # max ~150 words
    key_facts: List[str] = Field(default_factory=list)  # bullet-point facts
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    requires_follow_up: bool = False
    is_rumor: bool = False
    conflicting_sources: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 2: Company Research
# ---------------------------------------------------------------------------

class FundamentalCheck(BaseModel):
    metric: str
    value: Optional[str] = None  # always str to avoid fabricated numbers
    status: str  # GREEN | AMBER | RED | UNKNOWN
    note: str


class CompanyResearchOutput(AgentResponse):
    agent_name: AgentName = AgentName.COMPANY_RESEARCH
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    fundamental_checks: List[FundamentalCheck] = Field(default_factory=list)
    bull_points: List[str] = Field(default_factory=list)
    bear_points: List[str] = Field(default_factory=list)
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    data_completeness: str = "PARTIAL"  # COMPLETE | PARTIAL | NONE
    missing_metrics: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 3: Market Context
# ---------------------------------------------------------------------------

class MarketContextOutput(AgentResponse):
    agent_name: AgentName = AgentName.MARKET_CONTEXT
    index_regime: Optional[str] = None  # Bullish | Caution | Weak
    regime_detail: Optional[str] = None
    sector_trend: Optional[str] = None  # LEADING | NEUTRAL | LAGGING | UNKNOWN
    macro_flags: List[str] = Field(default_factory=list)
    data_as_of: Optional[datetime.datetime] = None
    data_staleness_warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent 4: Technical Research (explanation only — no new signals)
# ---------------------------------------------------------------------------

class TechnicalResearchOutput(AgentResponse):
    agent_name: AgentName = AgentName.TECHNICAL_RESEARCH
    setup_pattern: Optional[str] = None  # VCP | PULLBACK | NO_SETUP
    plain_english_explanation: str = ""
    key_levels_explained: List[str] = Field(default_factory=list)
    signal_state: Optional[str] = None
    # Explicit guard: no new price levels invented by the agent
    source_is_deterministic_engine: bool = True


# ---------------------------------------------------------------------------
# Agent 5: Risk Review
# ---------------------------------------------------------------------------

class RiskFlag(BaseModel):
    risk_type: str  # CONFLICTING_SOURCE | STALE_DATA | MISSING_DATA | DOWNSIDE_NEWS | REGULATORY | EARNINGS_PROXIMITY
    description: str
    severity: str  # HIGH | MEDIUM | LOW


class RiskReviewOutput(AgentResponse):
    agent_name: AgentName = AgentName.RISK_REVIEW
    risk_flags: List[RiskFlag] = Field(default_factory=list)
    contradictions_found: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    downgraded_from: Optional[str] = None  # e.g. WATCH → REJECT
    overall_risk_level: str = "MEDIUM"  # HIGH | MEDIUM | LOW


# ---------------------------------------------------------------------------
# Agent 6: Final Research Decision
# ---------------------------------------------------------------------------

class FinalResearchOutput(AgentResponse):
    agent_name: AgentName = AgentName.FINAL_DECISION
    final_status: ResearchStatus
    confidence_basis: str  # narrative explanation of confidence, NOT a numeric score
    supporting_evidence: List[EvidenceRecord] = Field(default_factory=list)
    what_would_change_assessment: List[str] = Field(default_factory=list)
    requires_human_review: bool = False
    human_review_reason: Optional[str] = None
    # Hard rule: no BUY/SELL/execution instruction ever
    is_execution_instruction: bool = False  # always False — enforced by validator


# ---------------------------------------------------------------------------
# Provider interface response
# ---------------------------------------------------------------------------

class AIResponse(BaseModel):
    """Raw response from an AI provider."""
    success: bool
    content: Optional[str] = None
    raw_text: Optional[str] = None
    model_id: str
    provider: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_sec: float = 0.0
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Quota status
# ---------------------------------------------------------------------------

class QuotaStatus(BaseModel):
    enabled: bool
    gemini_enabled: bool
    nvidia_research_enabled: bool
    zero_cost_only: bool
    daily_limit: int
    per_minute_limit: int
    used_today: int
    successful_today: int = 0
    failed_today: int = 0
    used_this_minute: int
    remaining_today: int
    quota_exhausted: bool
    exhausted_at: Optional[datetime.datetime] = None
    agent_flags: Dict[str, bool] = Field(default_factory=dict)
    provider_status: Dict[str, Any] = Field(default_factory=dict)
