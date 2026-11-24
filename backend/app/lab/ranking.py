"""Strategy Lab — Ranking Engine.

Top-5 auto-pick logic based on median net expectancy across eligible holding horizons.
Strategies must have >= 100 out-of-sample trades to be eligible.
Tie-break: half-1 vs half-2 consistency.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_TRADES_FOR_RANKING = 100
MAX_STRATEGIES_SELECTED = 5


def rank_strategies(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Given a list of result dicts (from lab_results rows), return a ranked list
    with auto-selection of top 5 eligible strategies.

    Each dict should contain:
        strategy_id, holding_days, total_trades, median_net_expectancy,
        half_consistency, sample_ok, sample_label, ...

    Returns the same list with added fields:
        rank (int or None for ineligible)
        auto_selected (bool)
        ranking_note (str)
    """
    # Group by strategy_id — pick best holding_days per strategy (highest median expectancy)
    by_strategy: Dict[str, Dict] = {}
    for r in results:
        sid = r["strategy_id"]
        if not r.get("sample_ok", False):
            continue
        exp = r.get("median_net_expectancy") or r.get("expectancy_r") or 0.0
        if sid not in by_strategy or exp > (by_strategy[sid].get("median_net_expectancy") or 0):
            by_strategy[sid] = r

    eligible = list(by_strategy.values())
    # Sort: primary = median_net_expectancy desc, tie-break = half_consistency desc
    eligible.sort(
        key=lambda x: (
            -(x.get("median_net_expectancy") or 0),
            -(x.get("half_consistency") or 0),
        )
    )

    selected_ids = {r["strategy_id"] for r in eligible[:MAX_STRATEGIES_SELECTED]}

    # Annotate all results
    rank_counter = 1
    seen_ranked = set()
    ranked_results = []
    for r in results:
        sid = r["strategy_id"]
        r2 = dict(r)
        if not r.get("sample_ok", False):
            r2["rank"] = None
            r2["auto_selected"] = False
            r2["ranking_note"] = f"INSUFFICIENT_SAMPLE ({r.get('total_trades', 0)} trades < {MIN_TRADES_FOR_RANKING} required)"
        elif sid in selected_ids and sid not in seen_ranked:
            r2["rank"] = rank_counter
            r2["auto_selected"] = True
            r2["ranking_note"] = f"Rank #{rank_counter} — auto-selected"
            seen_ranked.add(sid)
            rank_counter += 1
        else:
            # Eligible but not in top-5, or duplicate holding_day row
            if sid not in seen_ranked:
                r2["rank"] = rank_counter
                r2["auto_selected"] = False
                r2["ranking_note"] = f"Rank #{rank_counter} — eligible but not auto-selected"
                seen_ranked.add(sid)
                rank_counter += 1
            else:
                r2["rank"] = None
                r2["auto_selected"] = sid in selected_ids
                r2["ranking_note"] = "Alternate holding-day variant"
        ranked_results.append(r2)

    return ranked_results


def build_promotion_checklist(
    result: Dict[str, Any],
    paper_trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Returns a promotion checklist for a strategy:
    - gate_15_trades: has 15+ forward paper trades
    - gate_nonneg_expectancy: median R >= 0
    - gate_beats_random: beats random control (placeholder until random control added)
    - gate_slippage_ok: costs within assumptions
    - overall: GREEN / AMBER / RED
    - owner_can_override: always True
    """
    n = len(paper_trades)
    r_mults = [t.get("r_multiple", 0) or 0 for t in paper_trades]
    import statistics
    median_r = statistics.median(r_mults) if r_mults else 0.0
    total_costs = sum(t.get("costs", 0) or 0 for t in paper_trades)
    total_pnl = sum(t.get("net_pnl", 0) or 0 for t in paper_trades)

    gates = {
        "gate_15_trades": {
            "passed": n >= 15,
            "value": n,
            "label": f"{n} forward trades (need >= 15)",
        },
        "gate_nonneg_expectancy": {
            "passed": median_r >= 0,
            "value": round(median_r, 4),
            "label": f"Median R = {median_r:.3f} (need >= 0)",
        },
        "gate_beats_random": {
            "passed": None,  # requires random control — PENDING
            "value": None,
            "label": "Random control comparison — pending (need 15+ paper trades for each)",
        },
        "gate_slippage_ok": {
            "passed": total_pnl + total_costs > 0 if total_pnl != 0 else None,
            "value": round(total_costs, 2),
            "label": f"Total costs: ₹{total_costs:.2f} — gross PnL positive: {total_pnl + total_costs:.2f}",
        },
    }

    passed_gates = [g for g in gates.values() if g["passed"] is True]
    failed_gates = [g for g in gates.values() if g["passed"] is False]
    pending_gates = [g for g in gates.values() if g["passed"] is None]

    if failed_gates:
        overall = "RED"
    elif pending_gates:
        overall = "AMBER"
    elif len(passed_gates) == len(gates):
        overall = "GREEN"
    else:
        overall = "AMBER"

    return {
        "gates": gates,
        "overall": overall,
        "owner_can_override": True,
        "note": "Owner may override any gate. Promotion is advisory, not mandatory.",
    }
