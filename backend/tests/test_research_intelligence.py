"""
Tests for Phase 3.1 & Phase 3.2: Research Intelligence, Evidence Provenance Linking,
and 4-Factor Explainable Opportunity Scoring.
"""

import datetime
from fastapi.testclient import TestClient
import pytest

from app.engine.planner import (
    EvidenceProvenance,
    FactorScoreBreakdown,
    NewsCatalystItem,
    PlannedSignal,
    compute_factor_score_breakdown,
    planner,
)
from app.main import app
from app.models import (
    DecisionAudit,
    DecisionStageResult,
    FundamentalSnapshot,
    Instrument,
    NewsEvent,
    NewsSourceState,
    Scan,
    Signal,
)

client = TestClient(app)


def test_factor_score_breakdown_bounds_and_weights():
    """Verify that compute_factor_score_breakdown respects mathematical boundaries (0-100)
    and weights: 40% Technical, 25% Sector RS, 20% Fundamentals, 15% Catalyst.
    """
    # 1. High-quality candidate (Tight VCP, 90th RS rank, all-green fundamentals, clear news)
    fund_all_green = {"green_count": 8, "yellow_count": 0, "red_count": 0}
    res_high = compute_factor_score_breakdown(
        symbol="TCS",
        setup="VCP",
        trigger=3500.0,
        stop=3350.0,  # ~4.28% risk (tight)
        rs_rank=0.92,
        sector_name="Information Technology",
        news_cov={"status": "CLEAR", "has_earnings_warning": False},
        fund_dict=fund_all_green,
        catalyst_count=2,
    )

    assert 0.0 <= res_high.technical_score <= 100.0
    assert 0.0 <= res_high.sector_score <= 100.0
    assert 0.0 <= res_high.fundamental_score <= 100.0
    assert 0.0 <= res_high.catalyst_score <= 100.0
    assert 0.0 <= res_high.composite_score <= 100.0

    # High tech score due to tight risk <= 5%
    assert res_high.technical_score >= 85.0
    assert res_high.sector_score == 92.0
    assert res_high.fundamental_score == 100.0
    # Clean news (50.0) + 2 verified catalysts (30.0) = 80.0
    assert res_high.catalyst_score == 80.0

    expected_composite = round(
        0.40 * res_high.technical_score +
        0.25 * res_high.sector_score +
        0.20 * res_high.fundamental_score +
        0.15 * res_high.catalyst_score,
        1,
    )
    assert res_high.composite_score == expected_composite
    assert "TCS" in res_high.summary_rationale or "VCP" in res_high.summary_rationale

    # 2. Distressed / High-Risk candidate (Weak monitoring, low RS rank, RED news, RED fundamentals)
    fund_heavy_red = {"green_count": 1, "yellow_count": 1, "red_count": 4}
    res_distressed = compute_factor_score_breakdown(
        symbol="WEAKCO",
        setup="MONITORING",
        trigger=100.0,
        stop=80.0,
        rs_rank=0.15,
        sector_name="Metals",
        news_cov={"status": "NEWS_RED", "has_earnings_warning": True},
        fund_dict=fund_heavy_red,
        catalyst_count=0,
    )

    assert res_distressed.technical_score <= 25.0
    assert res_distressed.sector_score == 15.0
    assert res_distressed.fundamental_score == 0.0
    assert res_distressed.catalyst_score == 0.0
    assert res_distressed.composite_score < 20.0


def test_evidence_provenance_linking_in_scan(isolated_db_session):
    """Verify that scan candidate execution attaches primary evidence:
    - FundamentalSnapshot metadata
    - Verified NewsEvent primary sources and URLs
    - Sector metadata
    """
    db = isolated_db_session
    today = datetime.date.today()

    # 1. Seed instrument with explicit sector
    inst = Instrument(
        symbol="PROV_SYM",
        market="IN",
        name="Provenance Test Corp",
        sector="Pharmaceuticals",
        universe_tier="Mid",
        last_price=500.0,
    )
    db.add(inst)

    # 2. Seed fundamental snapshot
    snap = FundamentalSnapshot(
        symbol="PROV_SYM",
        market="IN",
        as_of=today - datetime.timedelta(days=10),
        source="screener_in",
        revenue_yoy=25.0,
        profit_yoy=30.0,
        op_margin=22.0,
        roce=18.0,
        roe=16.0,
        debt_equity=0.2,
        interest_coverage=8.0,
        completeness="FULL",
        lights_json='{"green_count": 6, "yellow_count": 1, "red_count": 0}',
    )
    db.add(snap)

    # 3. Seed recent verified news catalyst and healthy news source state
    src_state = NewsSourceState(
        source="nse_rss",
        status="HEALTHY",
        last_success_at=datetime.datetime.utcnow(),
    )
    db.add(src_state)

    news = NewsEvent(
        symbol="PROV_SYM",
        source="Exchange Filing",
        source_id="bse_filing_9981",
        title="USFDA Inspection Closed with EIR for Formulations Facility",
        url="https://bseindia.com/filings/doc_9981.pdf",
        published_at=datetime.datetime.now() - datetime.timedelta(days=2),
        severity="CLEAR",
        category="MATERIAL_EVENT",
        dedupe_key="prov_dedupe_key_9981",
        materiality="HIGH",
        match_confidence=1.0,
    )
    db.add(news)
    db.commit()

    # 4. Query dossier endpoint to verify evidence provenance assembly
    resp = client.get("/api/opportunities/PROV_SYM/dossier?market=IN")
    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "PROV_SYM"
    assert data["sector"] == "Pharmaceuticals"
    assert data["tier"] == "Mid"

    # Verify Evidence Provenance
    ev = data["evidence"]
    assert ev["fundamental_snapshot_id"] == snap.id
    assert ev["fundamental_source"] == "screener_in"
    assert ev["sector_name"] == "Pharmaceuticals"
    assert len(ev["catalysts"]) >= 1

    top_cat = ev["catalysts"][0]
    assert top_cat["id"] == news.id
    assert "USFDA Inspection Closed" in top_cat["title"]
    assert top_cat["source_url"] == "https://bseindia.com/filings/doc_9981.pdf"
    assert top_cat["severity"] == "CLEAR"
    assert top_cat["materiality"] == "HIGH"

    # Verify Factors
    factors = data["factors"]
    assert factors["composite_score"] > 0
    assert factors["fundamental_score"] > 50.0  # from green lights
    assert factors["catalyst_score"] >= 65.0    # CLEAR (50.0) + 1 verified material catalyst (+15.0)
    assert "PROV_SYM" in factors["summary_rationale"] or "Pharmaceuticals" in factors["summary_rationale"]


def test_opportunity_dossier_invalidation_and_firewall(isolated_db_session):
    """Verify that opportunity dossier exposes explicit thesis invalidation rules
    and mandatory non-directive compliance disclaimers.
    """
    db = isolated_db_session
    today = datetime.date.today()
    sig = Signal(
        symbol="DOSSIER_TEST",
        market="IN",
        setup="VCP",
        trigger=1200.0,
        entry_zone_high=1215.0,
        stop=1140.0,
        target1=1350.0,
        qty=50,
        risk_amount=3000.0,
        cost_estimate=25.0,
        cost_in_r=0.05,
        rs_rank=0.85,
        score=82.0,
        atr=25.0,
        valid_until=today + datetime.timedelta(days=2),
        state="VALID_SETUP",
        reasons_json='["Minervini VCP breakout structure", "Volume contraction 0.42x"]',
        news_flags_json='{"status": "CLEAR", "has_earnings_warning": false}',
    )
    db.add(sig)
    db.commit()

    resp = client.get("/api/opportunities/DOSSIER_TEST/dossier?market=IN")
    assert resp.status_code == 200
    data = resp.json()

    # Setup & Invalidation
    setup = data["setup"]
    assert setup["pattern"] == "VCP"
    assert setup["trigger"] == 1200.0
    assert setup["stop"] == 1140.0
    assert setup["target1"] == 1350.0
    assert setup["risk_reward_ratio"] == 2.5  # (1350 - 1200) / (1200 - 1140) = 150 / 60 = 2.5

    rules = setup["invalidation_rules"]
    assert any("Hard Stop" in r and "1140" in r for r in rules)
    assert any("Time Stop" in r and "20 completed" in r for r in rules)
    assert any("Earnings Blackout" in r for r in rules)

    # Compliance Firewall
    assert "Not a Trading Directive" in data["disclaimer"]
    assert "Deterministic trading logic governs all orders" in data["disclaimer"]


def test_trade_plan_returns_factors_and_evidence(isolated_db_session):
    """Verify that GET /api/plan returns the new factors and evidence payloads
    on candidate opportunities and signals while maintaining 100% backward compatibility.
    """
    db = isolated_db_session
    scan = Scan(
        market="IN",
        session_date=datetime.date.today(),
        regime="BULLISH",
        universe_size=10,
        passed_filters=5,
    )
    db.add(scan)
    db.flush()

    sig = Signal(
        scan_id=scan.id,
        symbol="PLAN_COMPAT",
        market="IN",
        setup="VCP",
        trigger=800.0,
        entry_zone_high=810.0,
        stop=760.0,
        target1=900.0,
        qty=40,
        risk_amount=1600.0,
        cost_estimate=20.0,
        cost_in_r=0.08,
        rs_rank=0.78,
        score=75.0,
        atr=18.0,
        valid_until=datetime.date.today() + datetime.timedelta(days=2),
        state="VALID_SETUP",
        reasons_json='["Stage 2 uptrend"]',
        news_flags_json='{"status": "CLEAR"}',
        fundamentals_json='{"green_count": 5, "yellow_count": 1, "red_count": 0}',
    )
    db.add(sig)
    db.commit()

    resp = client.get("/api/plan?market=IN")
    assert resp.status_code == 200
    plan_data = resp.json()

    assert "signals" in plan_data
    assert "candidate_opportunities" in plan_data

    all_signals = plan_data["signals"] + plan_data["candidate_opportunities"]
    target = next((s for s in all_signals if s["symbol"] == "PLAN_COMPAT"), None)
    assert target is not None

    # Check factors and evidence existence
    assert "factors" in target
    factors = target["factors"]
    assert "technical_score" in factors
    assert "sector_score" in factors
    assert "fundamental_score" in factors
    assert "catalyst_score" in factors
    assert "composite_score" in factors
    assert "summary_rationale" in factors

    assert "evidence" in target
    ev = target["evidence"]
    assert "catalysts" in ev
    assert "sector_name" in ev


def test_sector_momentum_integration_and_tailwinds():
    """Verify that sector group relative strength and trend (LEADING vs LAGGING)
    correctly impact the sector score component and summary rationale (Phase 3.3).
    """
    # Leading sector candidate (Stock RS 80%, Sector Group RS 90%)
    res_leading = compute_factor_score_breakdown(
        symbol="LEAD_SYM",
        setup="VCP",
        trigger=1000.0,
        stop=950.0,
        rs_rank=0.80,
        sector_name="Semiconductors",
        sector_rs_rank=0.90,
        sector_trend="LEADING",
    )
    # Lagging sector candidate (Stock RS 80%, Sector Group RS 20%)
    res_lagging = compute_factor_score_breakdown(
        symbol="LAG_SYM",
        setup="VCP",
        trigger=1000.0,
        stop=950.0,
        rs_rank=0.80,
        sector_name="Real Estate",
        sector_rs_rank=0.20,
        sector_trend="LAGGING",
    )

    # 60% Stock RS (48) + 40% Group RS (36) = 84.0 vs 60% Stock RS (48) + 40% Group RS (8) = 56.0
    assert res_leading.sector_score > res_lagging.sector_score
    assert res_leading.sector_score == 84.0
    assert res_lagging.sector_score == 56.0

    # Summary rationale contains the tailwind / drag explanation
    assert "LEADING Semiconductors tailwind" in res_leading.summary_rationale
    assert "LAGGING Real Estate drag" in res_lagging.summary_rationale


def test_ai_research_assistant_dynamic_synthesis():
    """Verify that AiResearchAssistant dynamically synthesizes primary evidence citations,
    green/red fundamental factors, and explicit invalidation thresholds (Phase 3.4).
    """
    from app.engine.ai_research_assistant import ai_research_assistant

    catalysts = [
        {
            "id": 101,
            "title": "Board Approves 1:1 Bonus Issue and Strategic Acquisition",
            "source": "BSE Exchange Corporate Filing",
            "severity": "CLEAR",
            "source_url": "https://bseindia.com/filings/101.pdf",
        }
    ]
    fund_lights = {
        "green_count": 5,
        "yellow_count": 1,
        "red_count": 1,
        "lights": [
            {"metric": "YoY PAT Growth", "status": "GREEN"},
            {"metric": "ROCE", "status": "GREEN"},
            {"metric": "Promoter Pledge %", "status": "RED"},
        ],
        "as_of": "2026-09-30",
    }
    setup_details = {
        "pattern": "VCP",
        "trigger": 2400.0,
        "stop": 2280.0,
        "risk_pct": 5.0,
    }

    thesis = ai_research_assistant.analyze_candidate_thesis(
        symbol="DYNAMIC_CORP",
        sector="Defense",
        current_price=2390.0,
        momentum_score=0.88,
        regime_status="BULLISH",
        catalysts=catalysts,
        fundamental_lights=fund_lights,
        setup_details=setup_details,
        sector_trend="LEADING",
    )

    # Bull Case verifies dynamic citations
    bull_evidence = " ".join(thesis["bull_case"]["evidence"])
    assert "VCP" in bull_evidence
    assert "2400.00" in bull_evidence
    assert "Sector leadership tailwind" in bull_evidence
    assert "Board Approves 1:1 Bonus Issue" in bull_evidence

    # Bear Case verifies headwind citations
    bear_evidence = " ".join(thesis["bear_case"]["evidence"])
    assert "Promoter Pledge %" in bear_evidence

    # Risks verify explicit stop
    risks_joined = " ".join(thesis["key_risks"])
    assert "2280.00" in risks_joined

    # Citations
    assert any("BSE Exchange Corporate Filing" in s for s in thesis["data_sources"])
    assert "Not a Trading Directive" in thesis["disclaimer"]


def test_opportunity_dossier_includes_ai_thesis(isolated_db_session):
    """Verify that the /api/opportunities/{symbol}/dossier endpoint includes the
    dynamically synthesized AI thesis with citations and sector trend.
    """
    db = isolated_db_session
    today = datetime.date.today()

    inst = Instrument(
        symbol="DOSSIER_AI",
        market="IN",
        sector="Engineering",
        universe_tier="Mid",
        last_price=1500.0,
    )
    db.add(inst)

    sig = Signal(
        symbol="DOSSIER_AI",
        market="IN",
        setup="VCP",
        trigger=1500.0,
        entry_zone_high=1520.0,
        stop=1425.0,
        target1=1680.0,
        qty=35,
        risk_amount=2625.0,
        cost_estimate=25.0,
        cost_in_r=0.06,
        rs_rank=0.82,
        score=85.0,
        atr=30.0,
        valid_until=today + datetime.timedelta(days=2),
        state="VALID_SETUP",
        reasons_json='["VCP 3-stage contraction"]',
        news_flags_json='{"status": "CLEAR"}',
    )
    db.add(sig)
    db.commit()

    resp = client.get("/api/opportunities/DOSSIER_AI/dossier?market=IN")
    assert resp.status_code == 200
    data = resp.json()

    assert "ai_thesis" in data
    ai = data["ai_thesis"]
    assert "bull_case" in ai
    assert "bear_case" in ai
    assert "key_risks" in ai
    assert "data_sources" in ai
    assert "evidence" in data
    assert data["evidence"]["sector_name"] == "Engineering"
    assert data["evidence"]["sector_trend"] in ("LEADING", "NEUTRAL", "LAGGING", "INSUFFICIENT_COVERAGE")


def test_news_severity_and_catalyst_scoring_rules():
    """Verify Section 1A rules:
    - RED news must never be described as positive; incurs -40 penalty.
    - AMBER identified as cautionary; incurs -20 penalty.
    - Missing/UNKNOWN coverage incurs -15 penalty (never awards positive bonus).
    - CLEAR is neutral baseline 50.0 (absence of negative news != positive catalyst).
    - Only verified material catalysts award positive points.
    """
    # 1. Clean news (CLEAR) with 0 catalysts -> exactly 50.0 baseline
    res_clear = compute_factor_score_breakdown(
        symbol="TCS",
        setup="MONITORING",
        trigger=0.0,
        stop=0.0,
        rs_rank=0.5,
        news_cov={"status": "CLEAR"},
        catalyst_count=0,
    )
    assert res_clear.catalyst_score == 50.0

    # 2. Unknown / missing coverage -> 35.0 (unverified penalty, no bonus)
    res_unknown = compute_factor_score_breakdown(
        symbol="TCS",
        setup="MONITORING",
        trigger=0.0,
        stop=0.0,
        rs_rank=0.5,
        news_cov=None,  # Missing coverage
        catalyst_count=2,  # Should not get catalyst bonus with missing coverage
    )
    assert res_unknown.catalyst_score == 35.0

    # 3. AMBER news -> 30.0 (-20 penalty)
    res_amber = compute_factor_score_breakdown(
        symbol="TCS",
        setup="MONITORING",
        trigger=0.0,
        stop=0.0,
        rs_rank=0.5,
        news_cov={"status": "AMBER"},
        catalyst_count=0,
    )
    assert res_amber.catalyst_score == 30.0

    # 4. RED news -> 10.0 (-40 penalty, never positive)
    res_red = compute_factor_score_breakdown(
        symbol="TCS",
        setup="MONITORING",
        trigger=0.0,
        stop=0.0,
        rs_rank=0.5,
        news_cov={"status": "NEWS_RED"},
        catalyst_count=3,  # Severe red news suppresses positive catalyst bonus
    )
    assert res_red.catalyst_score == 10.0


def test_unverified_and_cross_market_news_exclusion(isolated_db_session):
    """Verify Section 1B rules:
    - Unverified news (is_unverified=True) excluded from verified catalysts.
    - US sources (sec_edgar) excluded from IN market queries.
    - IN sources (nse_rss) excluded from US market queries.
    - Ambiguous cross-market symbol collisions excluded.
    """
    db = isolated_db_session
    today = datetime.date.today()
    now = datetime.datetime.utcnow()

    # Instruments in both markets with colliding symbol "DUAL"
    inst_in = Instrument(symbol="DUAL", market="IN", sector="Auto", universe_tier="Mid", last_price=500.0)
    inst_us = Instrument(symbol="DUAL", market="US", sector="Auto", universe_tier="Mid", last_price=25.0)
    db.add_all([inst_in, inst_us])

    # 1. Native Indian unverified rumor on DUAL
    n1 = NewsEvent(
        symbol="DUAL",
        source="nse_rss",
        title="Unverified Acquisition Rumor",
        published_at=now,
        ingested_at=now,
        severity="GREEN",
        materiality="HIGH",
        is_unverified=True,
        dedupe_key="rumor_1",
    )
    # 2. US SEC Edgar filing on DUAL
    n2 = NewsEvent(
        symbol="DUAL",
        source="sec_edgar",
        title="Form 8-K US Disclosure",
        published_at=now,
        ingested_at=now,
        severity="GREEN",
        materiality="HIGH",
        is_unverified=False,
        dedupe_key="sec_1",
    )
    # 3. Native Indian NSE filing on DUAL
    n3 = NewsEvent(
        symbol="DUAL",
        source="nse_rss",
        title="Board Approves Dividend",
        published_at=now,
        ingested_at=now,
        severity="GREEN",
        materiality="HIGH",
        is_unverified=False,
        dedupe_key="nse_1",
    )
    # 4. Ambiguous non-native source on colliding ticker
    n4 = NewsEvent(
        symbol="DUAL",
        source="gdelt_doc",
        title="Ambiguous Global Wire Item",
        published_at=now,
        ingested_at=now,
        severity="GREEN",
        materiality="HIGH",
        is_unverified=False,
        dedupe_key="gdelt_ambig_1",
    )
    db.add_all([n1, n2, n3, n4])
    db.commit()

    resp = client.get("/api/opportunities/DUAL/dossier?market=IN")
    assert resp.status_code == 200
    data = resp.json()

    verified_titles = [c["title"] for c in data["evidence"]["catalysts"]]
    # US SEC filing must be excluded from IN
    assert "Form 8-K US Disclosure" not in verified_titles
    # Ambiguous generic source on colliding ticker must be excluded
    assert "Ambiguous Global Wire Item" not in verified_titles
    # Unverified rumor must be excluded from verified catalysts
    assert "Unverified Acquisition Rumor" not in verified_titles
    # Native NSE filing should be verified
    assert "Board Approves Dividend" in verified_titles

    # Unverified rumor should be separated into unverified_catalysts
    unverified_titles = [c["title"] for c in data["evidence"]["unverified_catalysts"]]
    assert "Unverified Acquisition Rumor" in unverified_titles


def test_dossier_no_fabrication_when_no_setup(isolated_db_session):
    """Verify Section 1D rules:
    - Do NOT invent trigger, stop, or target when no valid stored setup exists.
    - Do NOT multiply last_price by arbitrary percentages.
    - Stop, trigger, and target must be None when no setup is confirmed.
    - Market regime must be retrieved from scan, not hardcoded BULLISH.
    """
    db = isolated_db_session
    today = datetime.date.today()

    inst = Instrument(
        symbol="NO_SETUP_STOCK",
        market="IN",
        sector="Pharma",
        universe_tier="Mid",
        last_price=800.0,
    )
    db.add(inst)

    scan = Scan(
        session_date=today,
        market="IN",
        regime="CAUTION",  # Test actual regime retrieval
        run_at=datetime.datetime.utcnow(),
    )
    db.add(scan)
    db.commit()

    # Query dossier with NO Signal stored
    resp = client.get("/api/opportunities/NO_SETUP_STOCK/dossier?market=IN")
    assert resp.status_code == 200
    data = resp.json()

    setup = data["setup"]
    assert setup["pattern"] == "NO_SETUP"
    # Strict requirement: trigger, stop, and target1 MUST be None, not fabricated
    assert setup["trigger"] is None
    assert setup["stop"] is None
    assert setup["target1"] is None
    assert setup["risk_reward_ratio"] is None

    # Invalidation rules must state Hard Stop is None
    assert any("Hard Stop: None" in rule for rule in setup["invalidation_rules"])
    assert any("Time Stop: 20 completed exchange sessions" in rule for rule in setup["invalidation_rules"])
    assert any("Earnings Blackout" in rule for rule in setup["invalidation_rules"])

    # AI thesis must reflect CAUTION regime and no active stop
    ai = data["ai_thesis"]
    assert any("CAUTION" in risk for risk in ai["key_risks"])
    assert any("No active hard stop" in risk for risk in ai["key_risks"])

