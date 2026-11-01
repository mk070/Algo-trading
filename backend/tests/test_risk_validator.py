import pandas as pd
import pytest
from app.engine.costs import CostBreakdown
from app.engine.risk_validator import RiskValidator


def make_dummy_cost(passed: bool = True, cost_in_r: float = 0.15) -> CostBreakdown:
    return CostBreakdown(
        brokerage=0.0,
        stt=10.0,
        exchange_charges=0.5,
        sebi_charges=0.05,
        stamp_duty=1.5,
        dp_charges=13.5,
        gst=2.5,
        slippage=5.0,
        total_cost=32.55,
        cost_in_r=cost_in_r,
        passed_gate=passed,
        rejection_reason="Costs exceed 0.25R" if not passed else "",
    )


def test_risk_validator_boundaries():
    validator = RiskValidator(market="IN")
    capital = 20000.0

    # 1. Normal valid trade passes
    res = validator.validate(
        symbol="TCS",
        entry_price=3500.0,
        stop_loss=3325.0,
        qty=1,
        risk_amount=100.0,  # 0.5% of 20,000 = 100.0
        cost_breakdown=make_dummy_cost(passed=True, cost_in_r=0.15),
        capital=capital,
        current_open_positions=0,
        current_open_heat=0.0,
    )
    assert res.passed is True
    assert res.status == "PASS"

    # 2. Max open positions boundary (limit = 2)
    res_pos = validator.validate(
        symbol="TCS",
        entry_price=3500.0,
        stop_loss=3325.0,
        qty=1,
        risk_amount=100.0,
        cost_breakdown=make_dummy_cost(passed=True),
        capital=capital,
        current_open_positions=2,  # already at max!
    )
    assert res_pos.passed is False
    assert res_pos.status == "BLOCK"
    assert any("positions" in r.lower() for r in res_pos.rejection_reasons)

    # 3. Portfolio heat boundary (limit = 2% = 400.0)
    res_heat = validator.validate(
        symbol="TCS",
        entry_price=3500.0,
        stop_loss=3325.0,
        qty=1,
        risk_amount=100.0,
        cost_breakdown=make_dummy_cost(passed=True),
        capital=capital,
        current_open_heat=350.0,  # 350 + 100 = 450 > 400!
    )
    assert res_heat.passed is False
    assert any("heat" in r.lower() for r in res_heat.rejection_reasons)

    # 4. Sector concentration boundary (max 1 per sector)
    res_sector = validator.validate(
        symbol="INFY",
        entry_price=1600.0,
        stop_loss=1520.0,
        qty=1,
        risk_amount=80.0,
        cost_breakdown=make_dummy_cost(passed=True),
        capital=capital,
        sector="Information Technology",
        open_sectors=["Information Technology"],  # already 1 IT stock held!
    )
    assert res_sector.passed is False
    assert any("sector" in r.lower() for r in res_sector.rejection_reasons)

    # 5. Consecutive loss circuit breaker (3 consecutive losses blocks new entries)
    res_loss_streak = validator.validate(
        symbol="TCS",
        entry_price=3500.0,
        stop_loss=3325.0,
        qty=1,
        risk_amount=100.0,
        cost_breakdown=make_dummy_cost(passed=True),
        capital=capital,
        recent_closed_trades=[{"pnl": -50.0}, {"pnl": -80.0}, {"pnl": -100.0}],
    )
    assert res_loss_streak.passed is False
    assert any("consecutive" in r.lower() for r in res_loss_streak.rejection_reasons)

    # 6. Drawdown pause circuit breaker (>= 8% drawdown blocks new entries)
    res_dd = validator.validate(
        symbol="TCS",
        entry_price=3500.0,
        stop_loss=3325.0,
        qty=1,
        risk_amount=100.0,
        cost_breakdown=make_dummy_cost(passed=True),
        capital=capital,
        current_drawdown_pct=9.5,  # 9.5% > 8.0%
    )
    assert res_dd.passed is False
    assert any("drawdown" in r.lower() for r in res_dd.rejection_reasons)


def test_correlation_clustering_boundary():
    """Verify that a stock with 60d daily return correlation >= 0.75 with an existing
    open position is BLOCKED from entry.
    """
    validator = RiskValidator(market="IN")
    dates = pd.date_range("2026-01-01", periods=65, freq="B").date

    # Highly correlated series (corr > 0.90)
    base_returns = [0.01 * (1 if i % 2 == 0 else -1) for i in range(65)]
    prices_a = 100.0 * (1.0 + pd.Series(base_returns)).cumprod()
    prices_b = 200.0 * (1.0 + pd.Series(base_returns) * 1.05).cumprod()

    df_a = pd.DataFrame({"date": dates, "close": prices_a})
    df_b = pd.DataFrame({"date": dates, "close": prices_b})

    res = validator.validate(
        symbol="HDFCBANK",
        entry_price=1600.0,
        stop_loss=1520.0,
        qty=1,
        risk_amount=80.0,
        cost_breakdown=make_dummy_cost(passed=True),
        capital=20000.0,
        open_symbols=["ICICIBANK"],
        all_universe_data={"HDFCBANK": df_a, "ICICIBANK": df_b},
    )

    assert res.passed is False
    assert any("correlation cluster" in r.lower() for r in res.rejection_reasons)

