import datetime
import pytest
from app.engine.earnings_analyst import EarningsAnalyst, PeriodFinancials


def test_missing_consensus_never_produces_synthetic_surprise():
    """Acceptance Test: If consensus data is missing, the engine MUST NOT fabricate
    or guess a surprise; surprise is None and status is strictly UNKNOWN.
    """
    analyst = EarningsAnalyst()
    latest = PeriodFinancials(
        symbol="INFY",
        market="IN",
        period_type="Q3",
        period_ended=datetime.date(2025, 12, 31),
        filing_date=datetime.date(2026, 1, 15),
        revenue=38000.0,
        net_profit=6500.0,
        eps=15.5,
        currency="INR",
        source_name="NSE_XBRL",
        source_url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=INFY",
        consensus_eps=None,  # No consensus
        consensus_source=None,
    )
    prior_yoy = PeriodFinancials(
        symbol="INFY",
        market="IN",
        period_type="Q3_PRIOR",
        period_ended=datetime.date(2024, 12, 31),
        filing_date=datetime.date(2025, 1, 15),
        revenue=35000.0,
        net_profit=6100.0,
        eps=14.5,
        currency="INR",
        source_name="NSE_XBRL",
        source_url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=INFY",
    )

    res = analyst.analyze_results(latest, prior_yoy=prior_yoy)
    assert res.eps_surprise_pct is None
    assert res.consensus_status == "UNKNOWN"
    assert res.guidance_status == "UNKNOWN"


def test_unverified_consensus_source_treated_as_unknown():
    analyst = EarningsAnalyst()
    latest = PeriodFinancials(
        symbol="TCS",
        market="IN",
        period_type="Q3",
        period_ended=datetime.date(2025, 12, 31),
        filing_date=datetime.date(2026, 1, 12),
        revenue=60000.0,
        net_profit=11000.0,
        eps=30.0,
        source_name="BSE_RESULTS",
        source_url="https://www.bseindia.com/corporates/results.html?scrip=532540",
        consensus_eps=28.0,
        consensus_source="TwitterRumors",  # Unverified source
    )

    res = analyst.analyze_results(latest)
    assert res.eps_surprise_pct is None
    assert res.consensus_status == "UNKNOWN"


def test_verified_consensus_calculates_valid_surprise():
    analyst = EarningsAnalyst()
    latest = PeriodFinancials(
        symbol="AAPL",
        market="US",
        period_type="Q1",
        period_ended=datetime.date(2025, 12, 31),
        filing_date=datetime.date(2026, 1, 29),
        revenue=124000.0,
        net_profit=33000.0,
        eps=2.18,
        currency="USD",
        source_name="SEC_EDGAR",
        source_url="https://www.sec.gov/edgar/browse/?CIK=AAPL",
        consensus_eps=2.10,
        consensus_source="Bloomberg",  # Verified source
    )

    res = analyst.analyze_results(latest)
    assert res.consensus_status == "VERIFIED"
    assert res.eps_surprise_pct is not None
    assert round(res.eps_surprise_pct, 1) == 3.8


def test_weak_revenue_and_profit_growth_reliably_flags_amber():
    analyst = EarningsAnalyst()
    latest = PeriodFinancials(
        symbol="WEAKCO",
        market="IN",
        period_type="Q3",
        period_ended=datetime.date(2025, 12, 31),
        filing_date=datetime.date(2026, 1, 20),
        revenue=4500.0,  # down from 5000 (-10%)
        operating_profit=450.0,  # 10% margin vs 15% prior (-500 bps)
        net_profit=250.0,  # down from 400 (-37.5%)
        eps=2.5,
        currency="INR",
        source_name="NSE_XBRL",
        source_url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=WEAKCO",
    )
    prior_yoy = PeriodFinancials(
        symbol="WEAKCO",
        market="IN",
        period_type="Q3_PRIOR",
        period_ended=datetime.date(2024, 12, 31),
        filing_date=datetime.date(2025, 1, 22),
        revenue=5000.0,
        operating_profit=750.0,
        net_profit=400.0,
        eps=4.0,
        currency="INR",
        source_name="NSE_XBRL",
        source_url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=WEAKCO",
    )

    res = analyst.analyze_results(latest, prior_yoy=prior_yoy)
    assert res.severity == "AMBER"
    assert len(res.amber_flags) >= 3
    assert any("Weak Revenue Growth" in f for f in res.amber_flags)
    assert any("Weak Net Profit" in f for f in res.amber_flags)
    assert any("Margin Deterioration" in f for f in res.amber_flags)


def test_strong_growth_produces_clear_status():
    analyst = EarningsAnalyst()
    latest = PeriodFinancials(
        symbol="GROWTHCO",
        market="IN",
        period_type="Q3",
        period_ended=datetime.date(2025, 12, 31),
        filing_date=datetime.date(2026, 1, 18),
        revenue=12000.0,  # up +20%
        operating_profit=2400.0,  # 20% margin
        net_profit=1800.0,  # up +28.5%
        eps=18.0,
        currency="INR",
        source_name="NSE_XBRL",
        source_url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=GROWTHCO",
    )
    prior_yoy = PeriodFinancials(
        symbol="GROWTHCO",
        market="IN",
        period_type="Q3_PRIOR",
        period_ended=datetime.date(2024, 12, 31),
        filing_date=datetime.date(2025, 1, 19),
        revenue=10000.0,
        operating_profit=1900.0,
        net_profit=1400.0,
        eps=14.0,
        currency="INR",
        source_name="NSE_XBRL",
        source_url="https://www.nseindia.com/companies-listing/corporate-filings-financial-results?symbol=GROWTHCO",
    )

    res = analyst.analyze_results(latest, prior_yoy=prior_yoy)
    assert res.severity == "CLEAR"
    assert len(res.amber_flags) == 0
    assert len(res.source_links) >= 1
    assert "https://www.nseindia.com" in res.source_links[0]

