import datetime
import pytest
from app.engine.newsfilter import news_engine


def test_severity_classification_rules():
    # RED Events
    sev, _ = news_engine.classify_severity("SEBI order imposing penalty for fraud")
    assert sev == "RED"

    sev, _ = news_engine.classify_severity("Resignation of Statutory Auditor of the company")
    assert sev == "RED"

    sev, _ = news_engine.classify_severity("Company reports default on debt repayment")
    assert sev == "RED"

    sev, _ = news_engine.classify_severity("Credit rating downgraded to D by CRISIL")
    assert sev == "RED"

    # AMBER Events
    sev, _ = news_engine.classify_severity("Board meeting scheduled for consideration of financial results")
    assert sev == "AMBER"

    sev, _ = news_engine.classify_severity("Company announces fund raise via QIP")
    assert sev == "AMBER"

    # GREEN Events
    sev, _ = news_engine.classify_severity("Company bags new order worth INR 450 Cr from government")
    assert sev == "GREEN"

    sev, _ = news_engine.classify_severity("Board approves share buyback and interim dividend")
    assert sev == "GREEN"


def test_earnings_blackout_blocks_trade():
    today = datetime.date.today()
    earnings_in_3_days = today + datetime.timedelta(days=3)

    coverage = news_engine.check_symbol_coverage(
        "RELIANCE", market="IN", earnings_date=earnings_in_3_days
    )

    assert coverage.has_earnings_blackout is True
    assert coverage.status == "BLOCKED"


def test_deduplication_key_deterministic():
    pub_time = datetime.datetime(2026, 11, 1, 10, 0, 0)
    key1 = news_engine.compute_dedupe_key("INFY", "Board meeting for Q2 results", pub_time)
    key2 = news_engine.compute_dedupe_key("INFY", "Board meeting for Q2 results", pub_time)
    assert key1 == key2

