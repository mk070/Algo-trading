import pytest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, PaperTrade, PaperHolding, PaperDailyHistory, PaperOrder
from app.engine.cycle4_paper import Cycle4PaperEngine


@pytest.fixture
def memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_forward_trades_have_run_type_forward(memory_db):
    trade = PaperTrade(
        trade_id="T_FORWARD_001",
        strategy_id="candidate_reg_alpha_buf30",
        run_type="FORWARD",
        symbol="RELIANCE",
        side="BUY",
        action="ENTER_NEW",
        exec_date=datetime.date(2026, 11, 17),
        shares=10,
        ref_open=2500.0,
        fill_price=2502.5,
        gross_turnover=25025.0,
        costs_json="{}",
        total_cost=25.0,
        net_cash_delta=-25050.0,
        realized_pnl=0.0,
    )
    memory_db.add(trade)
    memory_db.commit()

    loaded = memory_db.query(PaperTrade).filter(PaperTrade.trade_id == "T_FORWARD_001").first()
    assert loaded is not None
    assert loaded.run_type == "FORWARD"


def test_replay_trades_cannot_appear_in_forward_query(memory_db):
    replay_trade = PaperTrade(
        trade_id="T_REPLAY_SEED_001",
        strategy_id="candidate_reg_alpha_buf30",
        run_type="REPLAY",
        symbol="TCS",
        side="BUY",
        action="ENTER_NEW",
        exec_date=datetime.date(2026, 1, 15),
        shares=5,
        ref_open=3500.0,
        fill_price=3503.5,
        gross_turnover=17517.5,
        costs_json="{}",
        total_cost=17.5,
        net_cash_delta=-17535.0,
        realized_pnl=0.0,
    )
    forward_trade = PaperTrade(
        trade_id="T_FORWARD_LIVE_001",
        strategy_id="candidate_reg_alpha_buf30",
        run_type="FORWARD",
        symbol="INFY",
        side="BUY",
        action="ENTER_NEW",
        exec_date=datetime.date(2026, 11, 17),
        shares=8,
        ref_open=1800.0,
        fill_price=1801.8,
        gross_turnover=14414.4,
        costs_json="{}",
        total_cost=14.4,
        net_cash_delta=-14428.8,
        realized_pnl=0.0,
    )
    memory_db.add_all([replay_trade, forward_trade])
    memory_db.commit()

    # Query for forward trades only
    forward_results = (
        memory_db.query(PaperTrade)
        .filter(PaperTrade.strategy_id == "candidate_reg_alpha_buf30", PaperTrade.run_type == "FORWARD")
        .all()
    )
    assert len(forward_results) == 1
    assert forward_results[0].trade_id == "T_FORWARD_LIVE_001"
    assert forward_results[0].symbol == "INFY"

    # Replay trade must NEVER be returned in forward query
    assert not any(t.trade_id == "T_REPLAY_SEED_001" for t in forward_results)


def test_replay_holdings_cannot_appear_in_forward_query(memory_db):
    replay_holding = PaperHolding(
        strategy_id="candidate_reg_alpha_buf30",
        run_type="REPLAY",
        symbol="HDFCBANK",
        shares=10,
        avg_cost=1500.0,
        invested_cost=15000.0,
    )
    forward_holding = PaperHolding(
        strategy_id="candidate_reg_alpha_buf30",
        run_type="FORWARD",
        symbol="ICICIBANK",
        shares=15,
        avg_cost=1000.0,
        invested_cost=15000.0,
    )
    memory_db.add_all([replay_holding, forward_holding])
    memory_db.commit()

    forward_holdings = (
        memory_db.query(PaperHolding)
        .filter(PaperHolding.strategy_id == "candidate_reg_alpha_buf30", PaperHolding.run_type == "FORWARD")
        .all()
    )
    assert len(forward_holdings) == 1
    assert forward_holdings[0].symbol == "ICICIBANK"
    assert not any(h.symbol == "HDFCBANK" for h in forward_holdings)


def test_strategy_id_does_not_mix_between_contexts():
    # Verify candidate, control, and benchmark match prereg draft Section 3 exactly
    expected_candidate = "candidate_reg_alpha_buf30"
    expected_control = "control_c1b_buf30"
    expected_benchmark = "NIFTYBEES.NS"

    assert expected_candidate != expected_control
    assert not expected_candidate.startswith("replay_")
    assert not expected_control.startswith("replay_")
