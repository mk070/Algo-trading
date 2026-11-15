import datetime
from unittest.mock import MagicMock
import pandas as pd
import pytest

from app.engine.planner import Planner
from app.engine.pipeline import PipelineDecision, StageResult, StageCheck
from app.engine.setups import SetupCandidate
from app.engine.regime import RegimeResult


def test_planner_contract_and_state_ordering(monkeypatch):
    planner = Planner()

    # Mock regime to be BULLISH
    mock_regime = RegimeResult(
        market="IN",
        status="BULLISH",
        index_symbol="^NSEI",
        last_close=25000.0,
        sma50=24000.0,
        sma200=23000.0,
        is_bullish=True,
        allows_entries=True,
        size_multiplier=1.0,
        detail="Strong uptrend",
    )
    from app.engine import planner as planner_mod
    monkeypatch.setattr(planner_mod, "evaluate_market_regime", lambda *args, **kwargs: mock_regime)

    # Mock universe to return 2 symbols: TCS (valid setup) and INFY (no setup)
    mock_syms = [
        MagicMock(symbol="TCS", tier="Large", is_higher_risk=False),
        MagicMock(symbol="INFY", tier="Large", is_higher_risk=False),
    ]
    from app.engine.universe import universe_manager
    monkeypatch.setattr(universe_manager, "load_universe", lambda *args, **kwargs: mock_syms)

    # Mock daily bars
    dates = pd.date_range("2024-01-01", periods=210, freq="B")
    df = pd.DataFrame({
        "open": [3500.0] * 210,
        "high": [3550.0] * 210,
        "low": [3480.0] * 210,
        "close": [3520.0] * 210,
        "adj_close": [3520.0] * 210,
        "volume": [1000000.0] * 210,
        "sma50": [3400.0] * 210,
        "sma200": [3200.0] * 210,
        "atr14": [40.0] * 210,
        "avg_vol50": [1000000.0] * 210,
    }, index=dates)

    from app.providers.manager import provider_manager
    monkeypatch.setattr(provider_manager, "get_daily_bars", lambda *args, **kwargs: {"^NSEI": df, "TCS": df, "INFY": df})

    # Mock DecisionPipeline.evaluate to return PASS for TCS
    mock_decision_tcs = PipelineDecision(
        symbol="TCS",
        market="IN",
        asof_date=datetime.date.today(),
        mode="EOD_CANDIDATE",
        final_decision="PASS",
        setup="VCP",
        trigger=3500.0,
        stop=3400.0,
        target1=3700.0,
        entry_zone_high=3550.0,
        qty=25,
        risk_amount=2500.0,
        stages=[
            StageResult(stage_name="Risk Validator", status="PASS", checks=[], rejection_reasons=[])
        ],
        all_rejection_reasons=[],
        config_hash="abc",
        code_version="1.0",
        data_source="TEST",
    )

    from app.engine.pipeline import decision_pipeline
    monkeypatch.setattr(decision_pipeline, "evaluate", lambda symbol, **kwargs: mock_decision_tcs if symbol == "TCS" else PipelineDecision(
        symbol="INFY",
        market="IN",
        asof_date=datetime.date.today(),
        mode="EOD_CANDIDATE",
        final_decision="BLOCK",
        stages=[],
        all_rejection_reasons=["No pattern"],
        config_hash="abc",
        code_version="1.0",
        data_source="TEST",
    ))

    # Mock setup_engine to return SetupCandidate for TCS
    mock_cand_tcs = SetupCandidate(
        symbol="TCS",
        setup="VCP",
        pivot=3500.0,
        trigger=3500.0,
        entry_zone_high=3550.0,
        stop=3400.0,
        target1=3700.0,
        risk_per_share=100.0,
        risk_r=100.0,
        atr=40.0,
        reasons=["Valid tight base"],
        classification="PRE_BREAKOUT",
    )
    from app.engine.setups import setup_engine
    monkeypatch.setattr(setup_engine, "evaluate_vcp_breakout", lambda symbol, df=None, **kwargs: mock_cand_tcs if symbol == "TCS" else None)
    monkeypatch.setattr(setup_engine, "evaluate_pullback", lambda *args, **kwargs: None)

    # Mock trend template to pass for TCS
    from app.engine.screener import screener_engine
    mock_tt = MagicMock(passed=True, checklist=[])
    monkeypatch.setattr(screener_engine, "evaluate_trend_template", lambda *args, **kwargs: mock_tt)

    # Mock filter_stock to pass
    monkeypatch.setattr(universe_manager, "filter_stock", lambda *args, **kwargs: MagicMock(passed=True))

    # Mock news coverage to be CLEAR for TCS
    from app.engine.newsfilter import news_engine, SymbolNewsCoverage
    mock_cov = SymbolNewsCoverage(
        symbol="TCS",
        market="IN",
        status="CLEAR",
        checked_at=datetime.datetime.utcnow(),
    )
    monkeypatch.setattr(news_engine, "check_symbol_coverage", lambda *args, **kwargs: mock_cov)

    plan = planner.run_scan(market="IN", target_date=datetime.date.today())

    # Funnel pass count must count PASS decisions
    pass_item = next((item for item in plan.funnel if item["key"] == "PASS"), None)
    assert pass_item is not None
    assert pass_item["count"] >= 1

    # TCS must have state APPROACHING or VALID_SETUP, with qty=25
    tcs_sig = next((s for s in plan.candidate_opportunities if s.symbol == "TCS"), None)
    if not tcs_sig:
        tcs_sig = next((s for s in plan.signals if s.symbol == "TCS"), None)
    assert tcs_sig is not None
    assert tcs_sig.qty == 25
    assert tcs_sig.state in ("VALID_SETUP", "APPROACHING")
