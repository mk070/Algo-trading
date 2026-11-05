from app.engine.fundamentals import evaluate_fundamentals
from app.engine.research_metrics import lead_time_summary
from app.engine.setups import is_broke_out_today
from app.settings import settings


def test_fundamental_unknown_values_never_green():
    result = evaluate_fundamentals({}, "Unknown")
    assert result["unknown_count"] >= 6
    assert all(light["status"] != "GREEN" for light in result["lights"])


def test_profit_growth_boundaries():
    for value, expected in ((15, "GREEN"), (0, "YELLOW"), (-0.01, "RED")):
        result = evaluate_fundamentals({"profit_growth_yoy_pct": value})
        assert result["lights"][0]["status"] == expected


def test_profit_two_quarter_loss_or_decline_rules():
    loss = evaluate_fundamentals({"last_two_net_profits": [2, -1], "last_two_profit_yoy_changes_pct": [10, 2]})
    double_decline = evaluate_fundamentals({"last_two_net_profits": [2, 3], "last_two_profit_yoy_changes_pct": [-1, -4]})
    mixed = evaluate_fundamentals({"last_two_net_profits": [2, 3], "last_two_profit_yoy_changes_pct": [1, -4]})
    assert [x for x in loss["lights"] if x["metric"] == "Last 2 quarters net profit"][0]["status"] == "RED"
    assert [x for x in double_decline["lights"] if x["metric"] == "Last 2 quarters net profit"][0]["status"] == "RED"
    assert [x for x in mixed["lights"] if x["metric"] == "Last 2 quarters net profit"][0]["status"] == "YELLOW"


def test_debt_and_sector_relative_valuation_boundaries():
    for de, coverage, expected in ((0.49, 3, "GREEN"), (0.5, 3, "YELLOW"), (1.5, 1.5, "YELLOW"), (1.51, 3, "RED"), (0.2, 1.49, "RED")):
        result = evaluate_fundamentals({"debt_equity": de, "interest_coverage": coverage})
        assert next(x for x in result["lights"] if x["metric"].startswith("Debt/"))["status"] == expected
    for ratio, expected in ((0.79, "GREEN"), (0.8, "YELLOW"), (1.3, "YELLOW"), (1.51, "RED")):
        result = evaluate_fundamentals({"pe_vs_sector_median": ratio})
        assert next(x for x in result["lights"] if x["metric"].startswith("Valuation"))["status"] == expected


def test_margin_roce_and_roe_threshold_boundaries():
    for change, expected in ((1.01, "GREEN"), (1.0, "YELLOW"), (-1.0, "YELLOW"), (-2.0, "YELLOW"), (-2.01, "RED")):
        result = evaluate_fundamentals({"operating_margin_change_pp": change, "roce_pct": 15, "roe_pct": 12})
        assert next(x for x in result["lights"] if x["metric"] == "Operating margin change")["status"] == expected
    for value, expected in ((15, "GREEN"), (10, "YELLOW"), (9.99, "RED")):
        result = evaluate_fundamentals({"roce_pct": value})
        assert next(x for x in result["lights"] if x["metric"] == "ROCE")["status"] == expected
    for value, expected in ((12, "GREEN"), (8, "YELLOW"), (7.99, "RED")):
        result = evaluate_fundamentals({"roe_pct": value}, financial=True)
        assert next(x for x in result["lights"] if x["metric"] == "ROE")["status"] == expected


def test_valuation_and_promoter_red_thresholds_are_inclusive_as_specified():
    for ratio, expected in ((1.5, "YELLOW"), (1.5001, "RED")):
        result = evaluate_fundamentals({"pe_vs_sector_median": ratio})
        assert next(x for x in result["lights"] if x["metric"].startswith("Valuation"))["status"] == expected
    result = evaluate_fundamentals({"negative_earnings": True, "pe_vs_sector_median": 0.5})
    assert next(x for x in result["lights"] if x["metric"].startswith("Valuation"))["status"] == "RED"
    for change, pledge, expected in ((-3.01, 1, "RED"), (-3, 5, "YELLOW"), (0, 25, "YELLOW"), (0, 25.01, "RED"), (0, 4.99, "GREEN")):
        result = evaluate_fundamentals({"promoter_holding_change_4q_pp": change, "pledge_pct": pledge})
        # Current ingestion key is promoter_holding_change_4q_pp normalized below.
        assert next(x for x in result["lights"] if x["metric"] == "Promoter holding and pledge")["status"] == expected


def test_financial_sector_uses_roe_pb_and_asset_quality_not_leverage():
    result = evaluate_fundamentals({"roe_pct": 12, "pb_vs_sector_median": 0.7, "asset_quality_status": "GREEN", "asset_quality_status_light": "GREEN"}, "Banks", financial=True)
    metrics = {item["metric"]: item["status"] for item in result["lights"]}
    assert metrics["ROE"] == "GREEN"
    assert metrics["Valuation: P/B vs sector median"] == "GREEN"
    assert "Debt/equity and interest coverage" not in metrics
    assert metrics["Asset quality"] == "GREEN"


def test_mode_is_configured_and_red_blocking_is_opt_in():
    original = settings.fundamentals_config
    try:
        data = {"profit_growth_yoy_pct": -2}
        settings.fundamentals_config = {**original, "mode": "warn"}
        warn = evaluate_fundamentals(data)
        settings.fundamentals_config = {**original, "mode": "block_on_red"}
        blocked = evaluate_fundamentals(data)
        assert warn["review"] and not warn["blocks"]
        assert blocked["review"] and blocked["blocks"]
    finally:
        settings.fundamentals_config = original


def test_signal_day_breakout_uses_prior_pivot_and_is_disabled_by_default():
    assert settings.get_vcp_config().pivot_excludes_signal_day is False
    assert is_broke_out_today(101, 100, 100, True)
    assert not is_broke_out_today(101, 99.99, 100, True)
    assert not is_broke_out_today(100, 100, 100, True)
    assert not is_broke_out_today(101, 100, 100, False)


def test_lead_time_kpi_math_counts_before_after_and_never_flagged():
    result = lead_time_summary(
        ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"],
        ["2026-01-05", "2026-01-06", "2026-01-06"],
        ["2026-01-02", "2026-01-06", None],
    )
    assert result["median_sessions_earlier"] == 0.5
    assert result["flagged_before_pct"] == 33.3
    assert result["flagged_on_or_after_pct"] == 33.3
    assert result["never_flagged_pct"] == 33.3
