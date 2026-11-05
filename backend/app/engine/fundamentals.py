"""Heuristic fundamental traffic lights. Missing inputs always remain UNKNOWN."""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from app.settings import settings


def _light(metric: str, value: Any, period: str, source: str, status: str, why: str, threshold: str) -> dict:
    return {"metric": metric, "status": status, "value": value, "period": period, "source": source,
            "why": why, "threshold": threshold}


def evaluate_fundamentals(data: Dict[str, Any], sector: str = "Unknown", financial: bool = False) -> dict:
    """Evaluate available normalized values without inventing missing data.

    Input percentages use percentage points (15 means 15%), ratios use ordinary
    multiples. Thresholds are sourced from config/fundamentals.yaml.
    """
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    data = {key: clean(value) for key, value in data.items()}
    cfg = settings.fundamentals_config
    t = cfg.get("thresholds", {})
    source = str(data.get("source") or "UNKNOWN")
    period = str(data.get("period") or "Latest available")
    lights = []

    def add_growth(key: str, title: str, threshold_key: str):
        value = data.get(key)
        th = t.get(threshold_key, {})
        if value is None:
            return _light(title, "No data", period, source, "UNKNOWN", "No comparable consolidated quarterly values were available.", f"Green >= {th.get('green_min_pct')}%; Yellow >= {th.get('yellow_min_pct')}%; Red < {th.get('yellow_min_pct')}%")
        status = "GREEN" if value >= th["green_min_pct"] else "YELLOW" if value >= th["yellow_min_pct"] else "RED"
        return _light(title, f"{value:+.1f}% YoY", period, source, status, "Compares the latest quarter with the same quarter a year earlier.", f"Green >= {th['green_min_pct']}%; Yellow >= {th['yellow_min_pct']}%; Red < {th['yellow_min_pct']}%")

    lights.append(add_growth("profit_growth_yoy_pct", "Latest-quarter profit growth YoY", "profit_growth_yoy"))
    profits = data.get("last_two_net_profits")
    yoy_growths = data.get("last_two_profit_yoy_changes_pct")
    if not profits or len(profits) < 2 or not yoy_growths or len(yoy_growths) < 2:
        lights.append(_light("Last 2 quarters net profit", "No data", period, source, "UNKNOWN", "Two reported quarters and their YoY comparisons are needed.", "Red if either quarter is a loss or both YoY changes decline"))
    elif any(x <= 0 for x in profits) or all(x < 0 for x in yoy_growths):
        lights.append(_light("Last 2 quarters net profit", str(profits), period, source, "RED", "At least one quarter is loss-making or both quarters declined year over year.", "Red if either quarter is a loss or both YoY changes decline"))
    elif all(x > 0 for x in profits) and profits[0] > profits[1] and all(x >= 0 for x in yoy_growths):
        lights.append(_light("Last 2 quarters net profit", str(profits), period, source, "GREEN", "Both quarters were profitable and the latest is higher.", "Green if both positive and rising; mixed = Yellow"))
    else:
        lights.append(_light("Last 2 quarters net profit", str(profits), period, source, "YELLOW", "Recent quarterly results are mixed.", "Green if both positive and rising; mixed = Yellow"))
    lights.append(add_growth("revenue_growth_yoy_pct", "Revenue growth YoY", "revenue_growth_yoy"))

    margin = data.get("operating_margin_change_pp")
    mt = t.get("operating_margin_change_pp", {})
    if margin is None:
        lights.append(_light("Operating margin change", "No data", period, source, "UNKNOWN", "Four-quarter comparison unavailable.", "Green expanding; Yellow within +/-1 pp; Red below -2 pp"))
    else:
        green_pp = mt.get("green_min_pp", 1)
        red_pp = mt.get("red_below_pp", -2)
        status = "GREEN" if margin > green_pp else "RED" if margin < red_pp else "YELLOW"
        lights.append(_light("Operating margin change", f"{margin:+.1f} pp", period, source, status, "Shows whether operating profitability expanded over four quarters.", f"Green > +{green_pp} pp; Yellow +/-1 pp; Red < {red_pp} pp"))

    return_pct = data.get("roe_pct") if financial else data.get("roce_pct")
    return_type = "ROE" if financial else "ROCE"
    rt = t.get("roe_financial_pct" if financial else "roce_pct", {})
    green, yellow = rt.get("green_min"), rt.get("yellow_min")
    if return_pct is None:
        lights.append(_light(return_type, "No data", period, source, "UNKNOWN", "Reported return metric unavailable.", f"Green >= {green}%; Yellow >= {yellow}%; Red below {yellow}%"))
    else:
        status = "GREEN" if return_pct >= green else "YELLOW" if return_pct >= yellow else "RED"
        lights.append(_light(return_type, f"{return_pct:.1f}%", period, source, status, "Measures returns generated on capital or equity.", f"Green >= {green}%; Yellow >= {yellow}%; Red below {yellow}%"))

    if financial:
        for key, name in (("pb_vs_sector_median", "P/B vs sector median"), ("asset_quality_status", "Asset quality")):
            val = data.get(key)
            lights.append(_light(name, val if val is not None else "No data", period, source, str(data.get(f"{key}_light", "UNKNOWN")), "Banks and NBFCs use price-to-book and asset quality instead of debt/equity.", "Sector-aware; missing values remain UNKNOWN"))
    else:
        de, coverage = data.get("debt_equity"), data.get("interest_coverage")
        if de is None or coverage is None:
            status, value = "UNKNOWN", "No data"
        elif de > 1.5 or coverage < 1.5:
            status, value = "RED", f"D/E {de:.2f}x; coverage {coverage:.2f}x"
        elif de < 0.5 and coverage >= 3:
            status, value = "GREEN", f"D/E {de:.2f}x; coverage {coverage:.2f}x"
        else:
            status, value = "YELLOW", f"D/E {de:.2f}x; coverage {coverage:.2f}x"
        lights.append(_light("Debt/equity and interest coverage", value, period, source, status, "Checks leverage and the ability to pay interest.", "Green D/E <0.5 and coverage >=3; Yellow D/E 0.5-1.5 or coverage 1.5-3; Red D/E >1.5 or coverage <1.5"))

    pe_ratio = data.get("pb_vs_sector_median") if financial else data.get("pe_vs_sector_median")
    pt = t.get("pe_vs_sector_median", {})
    if pe_ratio is None:
        status, value = "UNKNOWN", "No sector comparison"
    elif data.get("negative_earnings"):
        status, value = "RED", "Negative earnings"
    elif pe_ratio > pt["red_min_ratio"]:
        status, value = "RED", f"{pe_ratio:.2f}x sector median"
    elif pe_ratio < pt["green_max_ratio"]:
        status, value = "GREEN", f"{pe_ratio:.2f}x sector median"
    else:
        status, value = "YELLOW", f"{pe_ratio:.2f}x sector median"
    metric_name = "Valuation: P/B vs sector median" if financial else "Valuation: P/E vs sector median"
    lights.append(_light(metric_name, value, period, source, status, "Compares valuation with peers; low absolute multiples alone are not treated as good.", "Green <0.8x; Yellow 0.8-1.3x; Red >1.5x or negative earnings"))

    pledge, holding_change = data.get("pledge_pct"), data.get("promoter_holding_change_4q_pp")
    if pledge is None or holding_change is None:
        status, value = "UNKNOWN", "No data"
    elif holding_change < -3 or pledge > 25:
        status, value = "RED", f"Holding change {holding_change:+.1f} pp; pledge {pledge:.1f}%"
    elif pledge >= 5:
        status, value = "YELLOW", f"Holding change {holding_change:+.1f} pp; pledge {pledge:.1f}%"
    else:
        status, value = "GREEN", f"Holding change {holding_change:+.1f} pp; pledge {pledge:.1f}%"
    lights.append(_light("Promoter holding and pledge", value, period, source, status, "A sharp promoter holding fall or pledged shares can indicate governance or funding risk.", "Green stable/rising and pledge <5%; Yellow pledge 5-25%; Red holding fall >3 pp or pledge >25%"))

    red_count = sum(item["status"] == "RED" for item in lights)
    unknown_count = sum(item["status"] == "UNKNOWN" for item in lights)
    any_red = red_count > 0
    mode = cfg.get("mode", "warn")
    sector_name = (sector or "Unknown").strip()
    cyclical = sector_name.lower() in {str(s).lower() for s in cfg.get("cyclical_sectors", [])}
    return {"symbol": data.get("symbol"), "sector": sector_name, "period": period, "source": source,
            "mode": mode, "lights": lights, "red_count": red_count, "unknown_count": unknown_count,
            "review": any_red and mode in {"warn", "block_on_red"},
            "blocks": any_red and mode == "block_on_red", "cyclical_note": "Cyclical business: valuation light should be weighed lightly near peak earnings." if cyclical else None,
            "detail_url": str(cfg.get("sector_url_templates", {}).get("screener", "https://www.screener.in/company/{symbol}/")).format(symbol=data.get("symbol", ""))}
