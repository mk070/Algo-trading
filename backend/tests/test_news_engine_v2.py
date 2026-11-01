import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.engine.news_collectors import (
    CollectorResponse,
    ComplianceHTTPClient,
    ComplianceViolationError,
    NseRssCollector,
    RawNewsItem,
    SecEdgarCollector,
)
from app.engine.news_processor import (
    AnalystActionExtractor,
    EntityResolver,
    ExtractiveSummarizer,
    MaterialityEvaluator,
    RumourClassifier,
    WireSyndicationClusterer,
)
from app.engine.newsfilter import NewsIntelligenceEngine, news_engine
from app.models import (
    NewsCoverageGap,
    NewsEvent,
    NewsSourceState,
)


@pytest.fixture
def mem_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# -----------------------------------------------------------------------------
# 1. COMPLIANCE & ALLOWLIST AUDIT TESTS
# -----------------------------------------------------------------------------

def test_compliance_client_blocks_prohibited_scraping_urls():
    """MANDATORY AUDIT: Prohibits scraping NSE/BSE website endpoints or scraping targets."""
    client = ComplianceHTTPClient()

    # Must block NSE website endpoints
    with pytest.raises(ComplianceViolationError):
        client.get("https://www.nseindia.com/api/corporates-pit")

    with pytest.raises(ComplianceViolationError):
        client.get("https://nseindia.com/market-data/live-equity-market")

    # Must block BSE website endpoints
    with pytest.raises(ComplianceViolationError):
        client.get("https://www.bseindia.com/corporates/ann.html")

    # Must block third-party scraping sites
    with pytest.raises(ComplianceViolationError):
        client.get("https://www.moneycontrol.com/news/business/stocks/")


def test_compliance_client_permits_sanctioned_sources():
    """Permits only sanctioned RSS syndication archives and official APIs."""
    client = ComplianceHTTPClient()

    assert client.is_url_allowed("https://nsearchives.nseindia.com/content/RSS/Corporate_announcements.xml")
    assert client.is_url_allowed("https://data.sec.gov/submissions/CIK0000320193.json")
    assert client.is_url_allowed("https://www.sec.gov/Archives/edgar/data/320193/000032019324000106/a8-k.htm")
    assert client.is_url_allowed("https://api.gdeltproject.org/api/v2/doc/doc")
    assert client.is_url_allowed("https://finnhub.io/api/v1/company-news")
    assert client.is_url_allowed("https://www.rbi.org.in/rss/pressreleases.xml")
    assert client.is_url_allowed("https://www.federalreserve.gov/feeds/press_monetary.xml")


# -----------------------------------------------------------------------------
# 2. ENTITY RESOLUTION & TICKER COLLISION GUARD TESTS
# -----------------------------------------------------------------------------

def test_entity_resolver_collision_guard_tcs_and_bel():
    """Verifies that common acronyms (TCS, BEL) colliding with general text are discarded or flagged TICKER_ONLY."""
    resolver = EntityResolver()

    # False positive text using "tax collected at source"
    fp_text = "The government issued new guidelines for tax collected at source on foreign remittances under TCS rules."
    matched, match_type, conf = resolver.resolve("TCS", "Tata Consultancy Services Limited", ["Tata Consultancy"], fp_text)
    assert not matched
    assert match_type == "COLLISION_DISCARD"

    # Genuine text mentioning official company name
    genuine_text = "Tata Consultancy Services reported strong cloud deal wins across Europe."
    matched, match_type, conf = resolver.resolve("TCS", "Tata Consultancy Services Limited", ["Tata Consultancy"], genuine_text)
    assert matched
    assert match_type == "EXACT_NAME"
    assert conf == 1.0

    # Bare ticker match with no company name routes to TICKER_ONLY with reduced confidence
    bare_ticker_text = "Heavy volumes seen in TCS ahead of quarterly numbers."
    matched, match_type, conf = resolver.resolve("TCS", "Tata Consultancy Services Limited", ["Tata Consultancy"], bare_ticker_text)
    assert matched
    assert match_type == "TICKER_ONLY"
    assert conf <= 0.50  # Must be discounted for review


def test_entity_resolver_bel_belgium_collision():
    resolver = EntityResolver()

    # "belgium" text without Bharat Electronics
    bel_fp = "Trade delegation from Belgium visits New Delhi to discuss aerospace cooperation."
    matched, match_type, _ = resolver.resolve("BEL", "Bharat Electronics Limited", ["Bharat Electronics"], bel_fp)
    assert not matched
    assert match_type in ("COLLISION_DISCARD", "NO_MATCH")

    # Genuine Bharat Electronics mention
    genuine_bel = "Bharat Electronics secures INR 1,150 Cr naval radar contract from Ministry of Defence."
    matched, match_type, conf = resolver.resolve("BEL", "Bharat Electronics Limited", ["Bharat Electronics"], genuine_bel)
    assert matched
    assert match_type == "EXACT_NAME"
    assert conf == 1.0


# -----------------------------------------------------------------------------
# 3. WIRE SYNDICATION CLUSTERING TESTS
# -----------------------------------------------------------------------------

def test_wire_syndication_clustering():
    """Verifies that wire stories (PTI / Reuters) syndicated across multiple publisher headlines
    produce identical cluster IDs.
    """
    clusterer = WireSyndicationClusterer()
    pub_dt = datetime.datetime(2026, 4, 10, 10, 30)

    # Agency story 1 published on Livemint
    title1 = "Infosys wins multi-year digital transformation deal from European bank: PTI"
    c_id1 = clusterer.generate_cluster_id(title1, pub_dt, wire_agency="PTI")

    # Agency story 1 published on Economic Times with slightly varied headline
    title2 = "European bank awards multi-year digital transformation deal to Infosys (PTI)"
    c_id2 = clusterer.generate_cluster_id(title2, pub_dt, wire_agency="PTI")

    # Should cluster together under PTI on that date
    assert c_id1 == c_id2

    # Different event produces different cluster ID
    title3 = "Infosys CFO resigns effective immediately after board meeting"
    c_id3 = clusterer.generate_cluster_id(title3, pub_dt, wire_agency=None)
    assert c_id3 != c_id1


# -----------------------------------------------------------------------------
# 4. RUMOUR / UNVERIFIED HEDGED LANGUAGE TESTS
# -----------------------------------------------------------------------------

def test_rumour_classification():
    classifier = RumourClassifier()

    # Hedged language
    assert classifier.is_unverified("Tata Motors in talks to acquire European battery manufacturer, sources said")
    assert classifier.is_unverified("Reliance reportedly weighing bid for petrochemical unit: people familiar")
    assert classifier.is_unverified("Pharma major mulls buyout of domestic peer amid speculation")

    # Confirmed factual headline
    assert not classifier.is_unverified("L&T secures INR 2,500 Cr infrastructure order for metro rail project")

    # Official filings are NEVER unverified
    assert not classifier.is_unverified("Company announces board meeting outcome", is_official_filing=True)


# -----------------------------------------------------------------------------
# 5. ANALYST ACTION EXTRACTOR (STRICT NULL RULE)
# -----------------------------------------------------------------------------

def test_analyst_action_extractor_strict_nulls():
    """Acceptance Test: If a field is not explicitly present, it MUST stay None (null).
    Never synthesize or infer missing ratings or target prices.
    """
    extractor = AnalystActionExtractor()

    # Text with brokerage and new target, but NO old rating or old target
    text1 = "Morgan Stanley maintains BUY on TCS with target price of Rs. 4200"
    res1 = extractor.extract(text1)

    assert res1 is not None
    assert res1["brokerage"] == "Morgan Stanley"
    assert res1["new_rating"] == "BUY"
    assert res1["old_rating"] is None  # Strict Null
    assert res1["new_target"] == 4200.0
    assert res1["old_target"] is None  # Strict Null

    # Text with upgrade from HOLD to BUY and target price increase
    text2 = "Goldman Sachs upgrades Infosys from HOLD to BUY, raises target price from 1600 to 1950"
    res2 = extractor.extract(text2)

    assert res2 is not None
    assert res2["brokerage"] == "Goldman Sachs"
    assert res2["action"] == "UPGRADE"
    assert res2["old_rating"] == "HOLD"
    assert res2["new_rating"] == "BUY"
    assert res2["old_target"] == 1600.0
    assert res2["new_target"] == 1950.0

    # Non-analyst text returns None
    text3 = "Quarterly results announced by board of directors"
    assert extractor.extract(text3) is None


# -----------------------------------------------------------------------------
# 6. NSE RSS PARSING (OFFLINE FIXTURE)
# -----------------------------------------------------------------------------

def test_nse_rss_parsing_fixture():
    collector = NseRssCollector()
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>NSE Corporate Announcements</title>
        <item>
          <title>INFY - Outcome of Board Meeting</title>
          <link>https://nsearchives.nseindia.com/corporate/INFY_01102026.pdf</link>
          <description>Infosys Limited announces audited financial results for Q3</description>
          <pubDate>Wed, 01 Oct 2026 12:30:00 GMT</pubDate>
        </item>
        <item>
          <title>Tata Motors Limited (TATAMOTORS) - Resignation of Director</title>
          <link>https://nsearchives.nseindia.com/corporate/TATAMOTORS_01102026.pdf</link>
          <description>Resignation of Independent Director</description>
          <pubDate>Wed, 01 Oct 2026 14:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    items = collector.parse_rss_content(sample_xml, "Corporate_announcements")
    assert len(items) == 2

    assert items[0].symbol == "INFY"
    assert items[0].is_official_filing is True
    assert "nsearchives.nseindia.com" in items[0].url

    assert items[1].symbol == "TATAMOTORS"
    assert items[1].is_official_filing is True


# -----------------------------------------------------------------------------
# 7. SEC EDGAR 8-K PARSING (OFFLINE FIXTURE)
# -----------------------------------------------------------------------------

def test_sec_edgar_submissions_parsing_fixture():
    collector = SecEdgarCollector()
    sample_json = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000100", "0000320193-26-000101"],
                "filingDate": ["2026-01-28", "2026-01-15"],
                "form": ["8-K", "8-K"],
                "primaryDocument": ["a8-k.htm", "departure.htm"],
                "primaryDocDescription": ["Item 2.02 Earnings", "Item 5.02 Departure of CFO"],
                "items": [["2.02"], ["5.02"]],
            }
        }
    }
    items = collector.parse_submissions("AAPL", "0000320193", sample_json)
    assert len(items) == 2

    assert items[0].symbol == "AAPL"
    assert items[0].category == "EARNINGS"
    assert "Item 2.02" in items[0].title
    assert items[0].is_official_filing is True

    assert items[1].symbol == "AAPL"
    assert items[1].category == "GOVERNANCE"
    assert "Item 5.02" in items[1].title


# -----------------------------------------------------------------------------
# 8. RULE 11: STRICT UNKNOWN POLICY (UNKNOWN IS NOT CLEAR)
# -----------------------------------------------------------------------------

def test_strict_unknown_policy_on_stale_or_missing_source(mem_db):
    """Rule 11: If a required source is down, stale (> 60m), or unmonitored,
    the coverage status MUST be UNKNOWN, never CLEAR.
    """
    engine = NewsIntelligenceEngine()

    # Case A: DB has no state for nse_rss -> Must be UNKNOWN
    cov = engine.check_symbol_coverage("RELIANCE", market="IN", db=mem_db)
    assert cov.status == "UNKNOWN"

    # Case B: nse_rss last polled 2 hours ago (> 60m max_source_age) -> Must be UNKNOWN
    two_hours_ago = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    state = NewsSourceState(
        source="nse_rss",
        status="HEALTHY",
        last_success_at=two_hours_ago,
        last_attempt_at=two_hours_ago,
    )
    mem_db.add(state)
    mem_db.commit()

    cov_stale = engine.check_symbol_coverage("RELIANCE", market="IN", db=mem_db)
    assert cov_stale.status == "UNKNOWN"

    # Case C: Fresh source poll (5 min ago), no red/amber, no gaps -> CLEAR
    state.last_success_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    mem_db.commit()

    cov_fresh = engine.check_symbol_coverage("RELIANCE", market="IN", db=mem_db)
    assert cov_fresh.status == "CLEAR"


def test_offline_coverage_gap_sets_status_unknown(mem_db):
    """When an offline downtime gap is recorded, affected stocks must return UNKNOWN."""
    engine = NewsIntelligenceEngine()

    # Fresh state
    state = NewsSourceState(
        source="nse_rss",
        status="HEALTHY",
        last_success_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=5),
    )
    mem_db.add(state)

    # Unresolved offline gap
    gap = NewsCoverageGap(
        source="nse_rss",
        gap_start=datetime.datetime.utcnow() - datetime.timedelta(hours=3),
        gap_end=datetime.datetime.utcnow() - datetime.timedelta(hours=1),
        duration_sec=7200.0,
        status="RECORDED",
        notes="Backend process stopped during market hours",
    )
    mem_db.add(gap)
    mem_db.commit()

    cov = engine.check_symbol_coverage("TCS", market="IN", db=mem_db)
    assert cov.status == "UNKNOWN"
    assert cov.coverage_gaps_count >= 1


# -----------------------------------------------------------------------------
# 9. MACRO CALENDAR CAUTION FLAGS
# -----------------------------------------------------------------------------

def test_macro_calendar_caution_window():
    engine = NewsIntelligenceEngine()

    # Test date 1 day prior to RBI MPC decision on 2026-02-06
    day_before_rbi = datetime.date(2026, 2, 5)
    flags_in = engine.check_macro_calendar("IN", asof_date=day_before_rbi)
    assert len(flags_in) >= 1
    assert "RBI rate decision" in flags_in[0]

    # Non-event date in July
    quiet_date = datetime.date(2026, 7, 10)
    flags_quiet = engine.check_macro_calendar("IN", asof_date=quiet_date)
    assert len(flags_quiet) == 0


# -----------------------------------------------------------------------------
# 10. ISOLATION INVARIANT TEST
# -----------------------------------------------------------------------------

def test_isolation_invariant_news_cannot_generate_buys_or_alter_risk():
    """Acceptance Test: News engine outputs ONLY status, flags, items, and coverage.
    It can NEVER generate BUY signals, change sizing, stops, targets, or risk limits.
    """
    engine = NewsIntelligenceEngine()
    cov = engine.check_symbol_coverage("INFY", market="IN")

    # Assert model strictly contains decision support metadata, no execution parameters
    dump = cov.model_dump()
    assert "qty" not in dump
    assert "trigger" not in dump
    assert "stop" not in dump
    assert "buy_signal" not in dump
    assert dump["status"] in ("CLEAR", "REVIEW", "BLOCKED", "UNKNOWN")
