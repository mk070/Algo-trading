import datetime
from unittest.mock import MagicMock
import pytest

from app.engine.newsfilter import news_engine, SymbolNewsCoverage
from app.engine.pipeline import decision_pipeline
from tests.test_decision_pipeline import make_clean_breakout_df


def test_news_check_symbol_coverage_no_db_returns_unknown():
    """Verify Rule 11: check_symbol_coverage without db context returns UNKNOWN."""
    cov = news_engine.check_symbol_coverage("RELIANCE", market="IN", db=None)
    assert cov.status == "UNKNOWN"
    assert "db" in cov.source_health
    assert cov.source_health["db"] == "NO_DATABASE_CONTEXT"


def test_pipeline_stage3_unknown_evaluates_to_wait(monkeypatch):
    """Verify that when news coverage is UNKNOWN, Stage 3 evaluates to WAIT, never PASS."""
    fake_cov = SymbolNewsCoverage(
        symbol="TCS",
        market="IN",
        status="UNKNOWN",
        checked_at=datetime.datetime.utcnow(),
    )
    monkeypatch.setattr(news_engine, "check_symbol_coverage", lambda *args, **kwargs: fake_cov)
    df = make_clean_breakout_df(70)

    decision = decision_pipeline.evaluate(
        symbol="TCS",
        df=df,
        market="IN",
        mode="EOD_CANDIDATE",
        db=None,
    )
    stage3 = next((s for s in decision.stages if s.stage_name == "News/Event Analyst"), None)
    assert stage3 is not None
    assert stage3.status == "WAIT"
    assert decision.final_decision != "PASS"


def test_pipeline_stage3_review_evaluates_to_wait(monkeypatch):
    """Verify that when news coverage is REVIEW, Stage 3 evaluates to WAIT."""
    fake_cov = SymbolNewsCoverage(
        symbol="INFY",
        market="IN",
        status="REVIEW",
        checked_at=datetime.datetime.utcnow(),
    )
    monkeypatch.setattr(news_engine, "check_symbol_coverage", lambda *args, **kwargs: fake_cov)
    df = make_clean_breakout_df(70)

    decision = decision_pipeline.evaluate(
        symbol="INFY",
        df=df,
        market="IN",
        mode="EOD_CANDIDATE",
        db=None,
    )
    stage3 = next((s for s in decision.stages if s.stage_name == "News/Event Analyst"), None)
    assert stage3 is not None
    assert stage3.status == "WAIT"


def test_pipeline_stage3_blocked_evaluates_to_block(monkeypatch):
    """Verify that when news coverage is BLOCKED, Stage 3 evaluates to BLOCK."""
    fake_cov = SymbolNewsCoverage(
        symbol="SBIN",
        market="IN",
        status="BLOCKED",
        red_events_count=1,
        checked_at=datetime.datetime.utcnow(),
    )
    monkeypatch.setattr(news_engine, "check_symbol_coverage", lambda *args, **kwargs: fake_cov)
    df = make_clean_breakout_df(70)

    decision = decision_pipeline.evaluate(
        symbol="SBIN",
        df=df,
        market="IN",
        mode="EOD_CANDIDATE",
        db=None,
    )
    stage3 = next((s for s in decision.stages if s.stage_name == "News/Event Analyst"), None)
    assert stage3 is not None
    assert stage3.status == "BLOCK"
    assert decision.final_decision == "BLOCK"
