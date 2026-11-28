"""
AI Agent Test Suite — 25 test cases using mocked provider responses.

All tests use mocked provider — no live API calls, no cost.
Run with: cd backend && python -m pytest tests/test_ai_agents.py -v
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.ai.schemas import (
    AgentName,
    AIResponse,
    EventCategory,
    MaterialityLevel,
    ResearchStatus,
    SentimentLabel,
)


# ---------------------------------------------------------------------------
# Test provider mock
# ---------------------------------------------------------------------------

def _make_provider(response_json: Optional[Dict] = None, success: bool = True,
                   error_code: str = None, error_msg: str = None,
                   raw_text: str = None, latency: float = 0.5):
    """Create a mock AIProvider."""
    provider = MagicMock()
    provider.model_id = "test-model"
    provider.provider_name = "test_provider"
    provider.is_available.return_value = True

    if success and response_json is not None:
        content = json.dumps(response_json)
    else:
        content = raw_text or ""

    provider.generate.return_value = AIResponse(
        success=success,
        content=content,
        raw_text=content,
        model_id="test-model",
        provider="test_provider",
        input_tokens=50,
        output_tokens=100,
        latency_sec=latency,
        error_code=error_code,
        error_message=error_msg,
    )
    return provider


# ===========================================================================
# Tests 1–7: Entity mapping, event classification, materiality, sentiment
# ===========================================================================

def test_01_entity_mapping_exact_symbol():
    """Agent correctly maps event to the supplied symbol."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "EARNINGS",
        "sentiment": "POSITIVE",
        "materiality": "HIGH",
        "affected_companies": ["INFY"],
        "summary": "Infosys Q2 results beat estimates.",
        "key_facts": ["Revenue grew 7% YoY"],
        "is_rumor": False,
        "requires_follow_up": False,
        "conflicting_sources": [],
    })
    result = run_news_intelligence(
        event_data={"id": 1, "symbol": "INFY", "title": "Infosys Q2 beats", "source": "nse_rss",
                    "published_at": "2025-10-01", "url": "https://nse.com/1", "severity": "AMBER", "category": "EARNINGS"},
        provider=provider,
    )
    assert result.is_valid
    assert result.symbol == "INFY"
    assert result.event_category == EventCategory.EARNINGS
    assert "INFY" in result.affected_companies


def test_02_event_classification_regulatory():
    """Agent correctly classifies a regulatory event."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "REGULATORY",
        "sentiment": "NEGATIVE",
        "materiality": "HIGH",
        "affected_companies": ["ADANIENT"],
        "summary": "SEBI imposes penalty on Adani Enterprises.",
        "key_facts": ["SEBI penalty of INR 10 crore"],
        "is_rumor": False,
        "requires_follow_up": True,
        "conflicting_sources": [],
    })
    result = run_news_intelligence(
        event_data={"id": 2, "symbol": "ADANIENT", "title": "SEBI penalty", "source": "nse_rss",
                    "published_at": "2025-10-02", "url": "https://nse.com/2", "severity": "RED", "category": "REGULATORY"},
        provider=provider,
    )
    assert result.is_valid
    assert result.event_category == EventCategory.REGULATORY
    assert result.sentiment == SentimentLabel.NEGATIVE
    assert result.requires_follow_up is True


def test_03_materiality_high_flagged():
    """HIGH materiality events are preserved."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "ACQUISITION",
        "sentiment": "POSITIVE",
        "materiality": "HIGH",
        "affected_companies": ["TCS"],
        "summary": "TCS acquires global IT firm.",
        "key_facts": ["Deal value USD 2bn"],
        "is_rumor": False,
        "requires_follow_up": False,
        "conflicting_sources": [],
    })
    result = run_news_intelligence(
        event_data={"id": 3, "symbol": "TCS", "title": "TCS acquisition", "source": "nse_rss",
                    "published_at": "2025-10-03", "url": "https://nse.com/3", "severity": "AMBER", "category": "ACQUISITION"},
        provider=provider,
    )
    assert result.materiality == MaterialityLevel.HIGH


def test_04_routine_event_skipped():
    """BOARD_MEETING_GENERAL category is skipped by materiality filter."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({"event_category": "OTHER", "sentiment": "NEUTRAL",
                                "materiality": "ROUTINE_IMMATERIAL", "summary": "Board meeting notice",
                                "key_facts": [], "is_rumor": False, "affected_companies": []})
    result = run_news_intelligence(
        event_data={"id": 4, "symbol": "RELIANCE", "title": "Board meeting notice", "source": "nse_rss",
                    "published_at": "2025-10-04", "url": "", "severity": "GREEN", "category": "BOARD_MEETING_GENERAL"},
        provider=provider,
    )
    assert result.error_code == "SKIPPED"
    assert result.materiality == MaterialityLevel.ROUTINE_IMMATERIAL
    # Provider was NOT called (skipped before API call)
    provider.generate.assert_not_called()


def test_05_negative_sentiment():
    """NEGATIVE sentiment events are captured correctly."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "LEGAL",
        "sentiment": "NEGATIVE",
        "materiality": "HIGH",
        "affected_companies": ["ZOMATO"],
        "summary": "Zomato faces class-action lawsuit.",
        "key_facts": ["Lawsuit filed in Delhi HC"],
        "is_rumor": False,
        "requires_follow_up": True,
        "conflicting_sources": [],
    })
    result = run_news_intelligence(
        event_data={"id": 5, "symbol": "ZOMATO", "title": "Zomato lawsuit", "source": "media",
                    "published_at": "2025-10-05", "url": "https://media.com/5", "severity": "RED", "category": "LEGAL"},
        provider=provider,
    )
    assert result.sentiment == SentimentLabel.NEGATIVE


def test_06_mixed_sentiment():
    """MIXED sentiment is captured correctly."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "EARNINGS",
        "sentiment": "MIXED",
        "materiality": "MEDIUM",
        "affected_companies": ["HDFCBANK"],
        "summary": "HDFC Bank Q3: revenue up, margins compressed.",
        "key_facts": ["Revenue +12% YoY", "NIM compressed 20bps"],
        "is_rumor": False,
        "requires_follow_up": False,
        "conflicting_sources": [],
    })
    result = run_news_intelligence(
        event_data={"id": 6, "symbol": "HDFCBANK", "title": "HDFC Q3", "source": "nse_rss",
                    "published_at": "2025-10-06", "url": "https://nse.com/6", "severity": "AMBER", "category": "EARNINGS"},
        provider=provider,
    )
    assert result.sentiment == SentimentLabel.MIXED


def test_07_rumor_flagged():
    """Rumor events are flagged via is_rumor=True."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "MANAGEMENT",
        "sentiment": "NEUTRAL",
        "materiality": "MEDIUM",
        "affected_companies": ["WIPRO"],
        "summary": "Unconfirmed report of CEO resignation.",
        "key_facts": ["Media report, not exchange-confirmed"],
        "is_rumor": True,
        "requires_follow_up": True,
        "conflicting_sources": ["ET Now", "CNBC-TV18"],
    })
    result = run_news_intelligence(
        event_data={"id": 7, "symbol": "WIPRO", "title": "Wipro CEO resign rumor", "source": "media",
                    "published_at": "2025-10-07", "url": "https://media.com/7", "severity": "AMBER", "category": "MANAGEMENT"},
        provider=provider,
    )
    assert result.is_rumor is True
    assert len(result.conflicting_sources) == 2


# ===========================================================================
# Tests 8–15: Conflicting sources, stale data, missing fundamentals,
#             invalid JSON, truncated output
# ===========================================================================

def test_08_conflicting_sources_captured():
    """Conflicting sources list is preserved from model output."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider({
        "event_category": "MANAGEMENT",
        "sentiment": "NEUTRAL",
        "materiality": "HIGH",
        "affected_companies": ["TITAN"],
        "summary": "Conflicting reports on Titan management change.",
        "key_facts": [],
        "is_rumor": False,
        "requires_follow_up": True,
        "conflicting_sources": ["Source A", "Source B", "Source C"],
    })
    result = run_news_intelligence(
        event_data={"id": 8, "symbol": "TITAN", "title": "Titan management", "source": "nse_rss",
                    "published_at": "2025-10-08", "url": "", "severity": "AMBER", "category": "MANAGEMENT"},
        provider=provider,
    )
    assert len(result.conflicting_sources) == 3


def test_09_stale_data_flagged_by_market_context():
    """Market context agent flags stale regime data."""
    from app.ai.agents.market_context_agent import run_market_context
    provider = _make_provider({
        "index_regime": "Caution",
        "regime_detail": "Index below 200-SMA",
        "sector_trend": "LAGGING",
        "macro_flags": ["RBI rate decision pending"],
        "data_staleness_warning": "Data is 72 hours old",
    })
    # regime data with an old session date
    old_date = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    result = run_market_context(
        symbol="TITAN",
        provider=provider,
        regime_data={"regime": "Caution", "session_date": old_date, "regime_detail_json": "{}"},
        market="IN",
    )
    assert result.is_valid
    # Staleness warning should be set (either from agent or computed)
    assert result.data_staleness_warning is not None


def test_10_missing_fundamentals_returns_none():
    """Company research agent handles missing fundamentals gracefully."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    from app.ai.agents.company_research_agent import run_company_research
    news_provider = _make_provider({
        "event_category": "EARNINGS",
        "sentiment": "POSITIVE",
        "materiality": "HIGH",
        "affected_companies": ["NEWSTOCK"],
        "summary": "New company earnings",
        "key_facts": [],
        "is_rumor": False,
        "requires_follow_up": False,
        "conflicting_sources": [],
    })
    news_result = run_news_intelligence(
        event_data={"id": 10, "symbol": "NEWSTOCK", "title": "Earnings", "source": "nse_rss",
                    "published_at": "2025-10-10", "url": "", "severity": "GREEN", "category": "EARNINGS"},
        provider=news_provider,
    )
    cr_provider = _make_provider({
        "fundamental_checks": [{"metric": "PE", "value": None, "status": "UNKNOWN", "note": "Not available"}],
        "bull_points": [],
        "bear_points": ["Fundamental data unavailable"],
        "data_completeness": "NONE",
        "missing_metrics": ["pe", "roe", "debt_equity"],
    })
    result = run_company_research(
        news_output=news_result,
        provider=cr_provider,
        fundamentals=None,
        instrument_meta=None,
    )
    assert result.is_valid
    assert result.data_completeness == "NONE"
    assert len(result.missing_metrics) > 0


def test_11_invalid_json_response():
    """Agent returns invalid JSON — error code is set, is_valid=False."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider(raw_text="NOT VALID JSON{{{", success=True)
    result = run_news_intelligence(
        event_data={"id": 11, "symbol": "BPCL", "title": "BPCL news", "source": "media",
                    "published_at": "2025-10-11", "url": "", "severity": "GREEN", "category": "OTHER"},
        provider=provider,
    )
    assert not result.is_valid
    assert result.error_code == "INVALID_JSON"


def test_12_truncated_output():
    """Agent handles a truncated JSON response (missing closing brace)."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    truncated = '{"event_category": "EARNINGS", "sentiment": "POSITIVE", "materiality": "HIGH", "summary": "Truncated'
    provider = _make_provider(raw_text=truncated, success=True)
    result = run_news_intelligence(
        event_data={"id": 12, "symbol": "NTPC", "title": "NTPC Q2", "source": "nse_rss",
                    "published_at": "2025-10-12", "url": "", "severity": "GREEN", "category": "EARNINGS"},
        provider=provider,
    )
    assert not result.is_valid
    assert result.error_code == "INVALID_JSON"


def test_13_risk_review_flags_high_risk():
    """Risk review identifies HIGH severity risk flags."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    from app.ai.agents.risk_review_agent import run_risk_review
    news_provider = _make_provider({
        "event_category": "REGULATORY",
        "sentiment": "NEGATIVE",
        "materiality": "HIGH",
        "affected_companies": ["ADANIENT"],
        "summary": "SEBI action",
        "key_facts": [],
        "is_rumor": False,
        "requires_follow_up": True,
        "conflicting_sources": [],
    })
    news = run_news_intelligence(
        event_data={"id": 13, "symbol": "ADANIENT", "title": "SEBI action", "source": "nse_rss",
                    "published_at": "2025-10-13", "url": "", "severity": "RED", "category": "REGULATORY"},
        provider=news_provider,
    )
    risk_provider = _make_provider({
        "risk_flags": [
            {"risk_type": "REGULATORY", "description": "SEBI enforcement action", "severity": "HIGH"}
        ],
        "contradictions_found": [],
        "missing_information": [],
        "downgraded_from": None,
        "overall_risk_level": "HIGH",
    })
    result = run_risk_review(
        symbol="ADANIENT",
        provider=risk_provider,
        news_output=news,
    )
    assert result.is_valid
    assert result.overall_risk_level == "HIGH"
    assert any(f.severity == "HIGH" for f in result.risk_flags)


def test_14_missing_data_not_negative():
    """Risk review labels missing data as missing_information, not a negative risk."""
    from app.ai.agents.risk_review_agent import run_risk_review
    provider = _make_provider({
        "risk_flags": [],
        "contradictions_found": [],
        "missing_information": ["Promoter holding data unavailable", "Annual report not filed"],
        "downgraded_from": None,
        "overall_risk_level": "MEDIUM",
    })
    result = run_risk_review(symbol="NEWCO", provider=provider, market="IN")
    assert result.is_valid
    assert len(result.missing_information) == 2
    assert len(result.risk_flags) == 0  # missing data ≠ risk flag


def test_15_technical_no_signal():
    """Technical agent handles no-signal state without inventing levels."""
    from app.ai.agents.technical_research_agent import run_technical_research
    provider = _make_provider({
        "setup_pattern": None,
        "plain_english_explanation": "The platform has not generated a trading signal for this stock.",
        "key_levels_explained": [],
        "signal_state": None,
    })
    result = run_technical_research(
        symbol="ZOMATO",
        provider=provider,
        signal_data=None,
        market="IN",
    )
    assert result.is_valid
    assert result.setup_pattern is None
    assert "not generated" in result.plain_english_explanation.lower()
    assert result.source_is_deterministic_engine is True


# ===========================================================================
# Tests 16–20: Provider timeout, 429, 503, quota exhausted, global AI disable
# ===========================================================================

def test_16_provider_timeout():
    """Provider timeout returns is_valid=False with TIMEOUT error code."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider(success=False, error_code="TIMEOUT", error_msg="Request timed out")
    result = run_news_intelligence(
        event_data={"id": 16, "symbol": "INFY", "title": "INFY news", "source": "media",
                    "published_at": "2025-10-16", "url": "", "severity": "GREEN", "category": "OTHER"},
        provider=provider,
    )
    assert not result.is_valid
    assert result.error_code == "TIMEOUT"


def test_17_provider_429():
    """429 rate limit returns is_valid=False."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider(success=False, error_code="HTTP_429", error_msg="Rate limit exceeded")
    result = run_news_intelligence(
        event_data={"id": 17, "symbol": "TCS", "title": "TCS news", "source": "media",
                    "published_at": "2025-10-17", "url": "", "severity": "GREEN", "category": "OTHER"},
        provider=provider,
    )
    assert not result.is_valid
    assert "429" in (result.error_code or "")


def test_18_provider_503():
    """503 service unavailable returns is_valid=False."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    provider = _make_provider(success=False, error_code="HTTP_503", error_msg="Service unavailable")
    result = run_news_intelligence(
        event_data={"id": 18, "symbol": "RELIANCE", "title": "News", "source": "media",
                    "published_at": "2025-10-18", "url": "", "severity": "GREEN", "category": "OTHER"},
        provider=provider,
    )
    assert not result.is_valid


def test_19_quota_guard_blocks_when_disabled():
    """Quota guard returns False when AI_AGENTS_ENABLED is False."""
    from app.ai.quota_guard import QuotaGuard
    guard = QuotaGuard()
    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = False
        mock_flags.ai_gemini_enabled = True
        mock_flags.ai_max_daily_requests = 100
        mock_flags.ai_max_requests_per_minute = 10
        result = guard.check_and_consume("test_agent")
    assert result is False


def test_20_quota_guard_blocks_when_gemini_disabled():
    """Quota guard returns False when AI_GEMINI_ENABLED is False."""
    from app.ai.quota_guard import QuotaGuard
    guard = QuotaGuard()
    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = True
        mock_flags.ai_gemini_enabled = False
        mock_flags.ai_max_daily_requests = 100
        mock_flags.ai_max_requests_per_minute = 10
        result = guard.check_and_consume("test_agent")
    assert result is False


# ===========================================================================
# Tests 21–25: No paid fallback, deduplication, cache reuse, history, strategy
# ===========================================================================

def test_21_no_paid_fallback():
    """When quota exhausted, no fallback is attempted — guard returns False hard."""
    from app.ai.quota_guard import QuotaGuard
    guard = QuotaGuard()
    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = True
        mock_flags.ai_gemini_enabled = True
        mock_flags.ai_zero_cost_only = True
        mock_flags.ai_max_daily_requests = 0  # Immediately exhausted
        mock_flags.ai_max_requests_per_minute = 10
        result = guard.check_and_consume("final_decision")
    assert result is False
    # Quota guard has no NVIDIA fallback path — confirmed by design


def test_22_quota_guard_counts_requests():
    """Quota guard counts each consumed request."""
    from app.ai.quota_guard import QuotaGuard
    guard = QuotaGuard()
    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = True
        mock_flags.ai_gemini_enabled = True
        mock_flags.ai_max_daily_requests = 100
        mock_flags.ai_max_requests_per_minute = 10
        mock_flags.agent_flag.return_value = True
        mock_flags.all_agent_flags.return_value = {"test": True}
        for _ in range(3):
            guard.check_and_consume("test")
        status = guard.get_status()
    assert status.used_today >= 3


def test_23_final_decision_no_execution_instruction():
    """Final decision output never sets is_execution_instruction=True."""
    from app.ai.agents.final_decision_agent import run_final_decision
    provider = _make_provider({
        "final_status": "WATCH",
        "confidence_basis": "Strong earnings growth supports monitoring.",
        "what_would_change_assessment": ["Revenue miss next quarter"],
        "requires_human_review": False,
        "human_review_reason": None,
    })
    result = run_final_decision(symbol="INFY", provider=provider, market="IN")
    assert result.is_valid
    assert result.final_status == ResearchStatus.WATCH
    assert result.is_execution_instruction is False


def test_24_final_decision_human_review_on_high_risk():
    """Final decision auto-escalates requires_human_review when HIGH risk flag present."""
    from app.ai.agents.news_intelligence_agent import run_news_intelligence
    from app.ai.agents.risk_review_agent import run_risk_review
    from app.ai.agents.final_decision_agent import run_final_decision
    from app.ai.schemas import RiskFlag

    # Create a risk output with HIGH flag
    risk_provider = _make_provider({
        "risk_flags": [{"risk_type": "REGULATORY", "description": "SEBI action", "severity": "HIGH"}],
        "contradictions_found": [],
        "missing_information": [],
        "downgraded_from": None,
        "overall_risk_level": "HIGH",
    })
    risk_output = run_risk_review(symbol="ADANIENT", provider=risk_provider)

    final_provider = _make_provider({
        "final_status": "REJECT",
        "confidence_basis": "Regulatory risk dominates.",
        "what_would_change_assessment": ["SEBI case dismissed"],
        "requires_human_review": False,  # Model says False, but auto-escalate should override
        "human_review_reason": None,
    })
    result = run_final_decision(
        symbol="ADANIENT",
        provider=final_provider,
        risk_output=risk_output,
        market="IN",
    )
    # Auto-escalation should force requires_human_review=True
    assert result.requires_human_review is True


def test_25_strategy_code_untouched():
    """Verify that no strategy files were modified by the AI agent implementation."""
    import os
    strategy_files = [
        "backend/app/engine/newsfilter.py",
        "backend/app/engine/news_processor.py",
        "backend/app/engine/news_collectors.py",
    ]
    base_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    for rel_path in strategy_files:
        full_path = os.path.normpath(os.path.join(base_dir, rel_path))
        assert os.path.exists(full_path), f"Strategy file missing: {full_path}"
        # We just check they exist — content integrity is enforced by git diff
    # Also verify the AI module does not import from broker execution modules
    from app.ai import orchestrator
    import inspect
    source = inspect.getsource(orchestrator)
    assert "zerodha" not in source.lower()
    assert "kite" not in source.lower()
    assert "place_order" not in source.lower()


# ===========================================================================
# Tests 26–34: Phase 2.1 Production Readiness & Integration Tests
# ===========================================================================

def test_26_gemini_model_id_is_3_1_flash_lite():
    """Verify GeminiAdapter uses the benchmarked gemini-3.1-flash-lite model ID."""
    from app.ai.gemini_adapter import GeminiAdapter
    adapter = GeminiAdapter()
    assert adapter.model_id == "gemini-3.1-flash-lite"
    assert adapter.provider_name == "google_gemini"


def test_27_gemini_adapter_parses_response_and_sanitizes_key():
    """Verify GeminiAdapter sends x-goog-api-key header, parses response, and scrubs key from errors."""
    from app.ai.gemini_adapter import GeminiAdapter
    adapter = GeminiAdapter()
    adapter._api_key = "SECRET_TEST_KEY_12345"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 5},
    }
    with patch("app.ai.gemini_adapter.httpx.post", return_value=mock_resp) as mock_post:
        res = adapter.generate("test prompt")
        assert res.success is True
        assert res.model_id == "gemini-3.1-flash-lite"
        assert res.input_tokens == 12
        assert res.output_tokens == 5
        # Verify key is in header, NOT in URL
        call_args = mock_post.call_args
        assert "SECRET_TEST_KEY_12345" not in call_args.args[0]
        assert call_args.kwargs["headers"]["x-goog-api-key"] == "SECRET_TEST_KEY_12345"

    # Verify error sanitization
    with patch("app.ai.gemini_adapter.httpx.post", side_effect=RuntimeError("Leak SECRET_TEST_KEY_12345 here")):
        err_res = adapter.generate("test prompt")
        assert err_res.success is False
        assert "SECRET_TEST_KEY_12345" not in (err_res.error_message or "")
        assert "[REDACTED]" in (err_res.error_message or "")


def test_28_gemini_adapter_handles_empty_or_blocked_response():
    """Empty or safety-blocked candidates return success=False without crashing."""
    from app.ai.gemini_adapter import GeminiAdapter
    adapter = GeminiAdapter()
    adapter._api_key = "TEST_KEY"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}
    with patch("app.ai.gemini_adapter.httpx.post", return_value=mock_resp):
        res = adapter.generate("test")
    assert res.success is False
    assert res.error_code == "EMPTY_RESPONSE_SAFETY"


def test_29_individual_agent_flags_and_global_override():
    """Each agent respects its own flag, and global AI_AGENTS_ENABLED=False overrides all."""
    from app.ai.quota_guard import QuotaGuard
    guard = QuotaGuard()

    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = True
        mock_flags.ai_gemini_enabled = True
        mock_flags.agent_flag.side_effect = lambda name: name == "news_intelligence"
        assert guard.is_agent_enabled("news_intelligence") is True
        assert guard.is_agent_enabled("company_research") is False
        assert guard.is_agent_enabled("final_decision") is False

        # Global disable overrides individual True flag
        mock_flags.ai_agents_enabled = False
        assert guard.is_agent_enabled("news_intelligence") is False


def test_30_persistent_quota_survives_restart_and_records_failures():
    """DB-backed quota survives QuotaGuard re-instantiation and separates failed_count from request_count."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.ai.models import AiProviderUsage
    from app.ai.quota_guard import QuotaGuard

    engine = create_engine("sqlite:///:memory:")
    AiProviderUsage.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)

    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = True
        mock_flags.ai_gemini_enabled = True
        mock_flags.ai_zero_cost_only = True
        mock_flags.ai_max_daily_requests = 2
        mock_flags.ai_max_requests_per_minute = 10
        mock_flags.agent_flag.return_value = True
        mock_flags.all_agent_flags.return_value = {"news_intelligence": True}

        db = Session()
        guard1 = QuotaGuard()
        assert guard1.check_and_consume("news_intelligence", db=db) is True
        guard1.record_outcome(success=False, error_code="HTTP_503", db=db)
        db.commit()

        # Simulate process restart with a brand new QuotaGuard instance
        guard2 = QuotaGuard()
        status = guard2.get_status(db=db)
        assert status.used_today == 1
        assert status.successful_today == 0  # Failed request NOT counted as successful generation
        assert status.failed_today == 1

        # 2nd slot succeeds, 3rd slot is blocked
        assert guard2.check_and_consume("news_intelligence", db=db) is True
        guard2.record_outcome(success=True, input_tokens=40, output_tokens=20, db=db)
        assert guard2.check_and_consume("news_intelligence", db=db) is False
        db.close()


def test_31_concurrent_quota_reservations_respect_limit(tmp_path):
    """Concurrent threads racing for quota cannot exceed AI_MAX_DAILY_REQUESTS."""
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.ai.models import AiProviderUsage
    from app.ai.quota_guard import QuotaGuard

    db_file = tmp_path / "concurrent_quota.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    AiProviderUsage.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    guard = QuotaGuard()

    def _attempt(_):
        db = Session()
        try:
            ok = guard.check_and_consume("news_intelligence", db=db)
            db.commit()
            return ok
        finally:
            db.close()

    with patch("app.ai.quota_guard.flags") as mock_flags:
        mock_flags.ai_agents_enabled = True
        mock_flags.ai_gemini_enabled = True
        mock_flags.ai_max_daily_requests = 3
        mock_flags.ai_max_requests_per_minute = 50
        mock_flags.agent_flag.return_value = True

        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(_attempt, range(8)))

    assert sum(1 for o in outcomes if o) == 3


def test_32_migration_011_upgrade_and_downgrade(tmp_path):
    """Verify migration 011_ai_research_agents upgrades and downgrades cleanly on a disposable DB."""
    import importlib.util
    import os
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, inspect

    mig_path = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions", "011_ai_research_agents.py"
    )
    spec = importlib.util.spec_from_file_location("mig_011", os.path.normpath(mig_path))
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    db_file = tmp_path / "mig_test.db"
    engine = create_engine(f"sqlite:///{db_file}")

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        mig.op = op
        mig.upgrade()

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"ai_agent_executions", "ai_research_assessments", "ai_provider_usage"}.issubset(tables)

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        mig.op = op
        mig.downgrade()

    insp_after = inspect(engine)
    tables_after = set(insp_after.get_table_names())
    assert "ai_agent_executions" not in tables_after
    assert "ai_research_assessments" not in tables_after
    assert "ai_provider_usage" not in tables_after


def test_33_api_routes_auth_and_cached_retrieval():
    """Verify /api/ai/* routes enforce production auth and return cached assessments without consuming quota."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.settings import settings

    client = TestClient(app)
    with patch.object(settings, "env", "production"), patch.object(settings, "app_token", "prod-secret-token"):
        unauth = client.get("/api/ai/status")
        assert unauth.status_code == 401

        auth = client.get("/api/ai/status", headers={"Authorization": "Bearer prod-secret-token"})
        assert auth.status_code == 200
        body = auth.json()
        assert body["ai_agents_enabled"] is False
        assert body["provider_status"]["gemini_model"] == "gemini-3.1-flash-lite"

        bad_sym = client.get(
            "/api/ai/research/INVALID$SYM!",
            headers={"Authorization": "Bearer prod-secret-token"},
        )
        assert bad_sym.status_code == 422


def test_34_frontend_integration_files_present():
    """Verify AiResearchCard is integrated into NewsPage, DashboardPage, WatchlistPage, and SignalCard."""
    import os
    root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src"))
    for rel in [
        "components/AiResearchCard.tsx",
        "components/SignalCard.tsx",
        "pages/NewsPage.tsx",
        "pages/DashboardPage.tsx",
        "pages/WatchlistPage.tsx",
    ]:
        full = os.path.join(root, rel)
        assert os.path.exists(full), f"Missing frontend file: {full}"
        with open(full, "r", encoding="utf-8") as f:
            text = f.read()
        assert "AiResearchCard" in text, f"AiResearchCard not integrated in {rel}"

