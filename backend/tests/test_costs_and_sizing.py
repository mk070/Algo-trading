import pytest
from app.engine.costs import CostModel
from app.engine.sizing import PositionSizer


def test_indian_cost_model_breakdown():
    """Verify Indian delivery round-trip cost calculations."""
    model = CostModel(market="IN")
    price = 1000.0
    qty = 10
    risk_amount = 500.0  # 5% stop on 10,000 position = 500 risk

    breakdown = model.calculate_round_trip(price, qty, risk_amount)

    buy_val = price * qty  # 10,000
    sell_val = price * qty  # 10,000
    turnover = 20000.0

    # STT: 0.1% of buy (10) + 0.1% of sell (10) = 20.0
    assert breakdown.stt == 20.0

    # Stamp duty: 0.015% of buy = 1.50
    assert breakdown.stamp_duty == 1.50

    # DP flat charge: 13.50
    assert breakdown.dp_charges == 13.50

    # Total cost should be positive and reasonable (~60-70 INR with slippage & taxes)
    assert 50.0 <= breakdown.total_cost <= 90.0

    # Cost in R = total_cost / 500 = ~0.12 - 0.15R
    assert 0.10 <= breakdown.cost_in_r <= 0.20
    assert breakdown.passed_gate is True


def test_simulator_can_separate_cost_model_slippage_from_slipped_fill_prices():
    model = CostModel(market="IN")
    full = model.calculate_round_trip(1000.0, 10, 500.0)
    fees_only = model.calculate_round_trip(1000.0, 10, 500.0, include_slippage=False)
    assert full.slippage > 0
    assert fees_only.slippage == 0
    assert round(full.total_cost - fees_only.total_cost, 2) == full.slippage


def test_cost_gate_rejects_small_capital_uneconomical_trades():
    """Section 4.3: With small account size (e.g. INR 17,500), 0.5% risk is INR 87.5.
    Round-trip fixed charges (DP ~15 + STT + taxes) consume > 0.25R (> ~22 INR),
    so the cost gate must honestly reject the trade!
    """
    model = CostModel(market="IN")
    price = 1500.0
    qty = 1
    risk_amount = 87.5  # 0.5% of 17,500

    breakdown = model.calculate_round_trip(price, qty, risk_amount)

    # Cost in R should exceed max allowed 0.25R
    assert breakdown.cost_in_r > 0.25
    assert breakdown.passed_gate is False
    assert "consume" in breakdown.rejection_reason.lower()


def test_position_sizing_respects_limits():
    """Verify position sizing respects capital cap, risk %, and whole share rounding."""
    sizer = PositionSizer(market="IN")
    entry = 500.0
    stop = 475.0  # risk 25 per share
    eff_risk = 25.0
    capital = 50000.0

    res = sizer.calculate_size(
        symbol="TEST",
        entry=entry,
        stop=stop,
        effective_risk_per_share=eff_risk,
        capital_override=capital,
    )

    assert res.passed is True
    # At 0.5% risk on 50,000 = 250 risk amount
    # qty_risk = floor(250 / 25) = 10 shares
    assert res.qty == 10
    assert res.risk_amount == 250.0
    assert res.position_value == 5000.0

