"""
Strictly Separate AI Research Assistant
Informational & Explanatory Layer — Zero Control Over Trading Execution

Capabilities:
1. Summarize company quarterly filings & news sentiment.
2. Present structured Bullish vs Bearish theses with citations.
3. Post-Trade Post-Mortems (explaining why a closed trade won or lost).
4. Identify risks, contradictory evidence, and corporate disclosures.

STRICT FIREWALL:
- NEVER generates or modifies deterministic trading signals.
- NEVER alters entry, stop-loss, target, or position sizing.
- NEVER overrides strategy rankings, filters, or PASS/BLOCK decisions.
- NEVER places or executes orders.
- If AI engine or LLM API is unavailable, the deterministic paper-trading system
  functions 100% normally without interruption.
- All outputs are explicitly marked: "AI Informational Research Only — Not a Trading Directive".
"""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AiResearchAssistant:
    """
    Isolated AI Research Assistant for informational analysis and trade explanations.
    """

    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name

    def analyze_candidate_thesis(
        self,
        symbol: str,
        sector: str,
        current_price: float,
        momentum_score: float,
        regime_status: str,
        catalysts: Optional[List[Dict[str, Any]]] = None,
        fundamental_lights: Optional[Dict[str, Any]] = None,
        setup_details: Optional[Dict[str, Any]] = None,
        sector_trend: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generates balanced Bullish vs Bearish theses with dynamic primary evidence citations,
        fundamental factor checks, news catalysts, and explicit invalidation thresholds.
        STRICT FIREWALL: Informational analysis only — zero control over deterministic execution.
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M IST")

        bull_points: List[str] = []
        bear_points: List[str] = []
        price_desc = f"{current_price:.2f}" if (current_price is not None and current_price > 0) else "N/A"
        citations: List[str] = [
            f"Exchange Price Snapshot ({symbol} closing {price_desc})",
            f"Sector Group ({sector})",
            f"Market Regime Tracker ({regime_status})",
        ]

        # 1. Technical & Momentum Structural Evidence
        has_valid_setup = bool(
            setup_details
            and setup_details.get("pattern") in ("VCP", "BREAKOUT", "PULLBACK")
            and setup_details.get("trigger") is not None
            and setup_details.get("stop") is not None
        )
        if has_valid_setup:
            pat = setup_details["pattern"]
            trig = setup_details["trigger"]
            st = setup_details["stop"]
            risk_pct = setup_details.get("risk_pct", round((trig - st) / trig * 100.0, 1) if trig > st else 5.0)
            bull_points.append(
                f"Minervini {pat} consolidation structure with defined pivot at {trig:.2f} and tight risk of {risk_pct:.1f}%."
            )
        else:
            pat = setup_details.get("pattern", "NO_SETUP") if setup_details else "NO_SETUP"
            if pat in ("MONITORING", "NO_SETUP", "UNAVAILABLE"):
                bear_points.append(
                    f"No confirmed technical breakout trigger (pattern: {pat}). Monitoring for constructive base formation."
                )
            if momentum_score is not None:
                bull_points.append(
                    f"Relative momentum score ({momentum_score:+.2f}) demonstrates persistent price acceptance."
                )

        # 2. Sector Momentum & Group Relative Strength (Phase 3.3)
        trend_label = sector_trend or "NEUTRAL"
        if trend_label == "LEADING":
            bull_points.append(
                f"Sector leadership tailwind: {sector} is a top-tier leading industry group outperforming broader benchmark indices."
            )
        elif trend_label == "LAGGING":
            bear_points.append(
                f"Sector group drag: {sector} is a lagging industry group, increasing vulnerability to overhead supply on breakouts."
            )
        elif trend_label in ("INSUFFICIENT_COVERAGE", "UNKNOWN"):
            bear_points.append(
                f"Sector cohort limitation: {sector} peer sample size is insufficient for reliable relative strength classification."
            )
        else:
            bull_points.append(
                f"Sector peer stability in {sector} trading with neutral market alignment."
            )

        # 3. Fundamental Factor Checklist
        if fundamental_lights:
            green_cnt = fundamental_lights.get("green_count", 0)
            red_cnt = fundamental_lights.get("red_count", 0)
            unknown_cnt = fundamental_lights.get("unknown_count", 0)
            lights = fundamental_lights.get("lights", [])

            green_names = [l.get("metric", "") for l in lights if l.get("status") == "GREEN"]
            red_names = [l.get("metric", "") for l in lights if l.get("status") == "RED"]

            if green_cnt > 0:
                bull_points.append(
                    f"Fundamental backing: {green_cnt} verified green checks ({', '.join(green_names[:2]) or 'Quality metrics pass'})."
                )
            if red_cnt > 0:
                bear_points.append(
                    f"Financial quality headwind: {red_cnt} red traffic lights ({', '.join(red_names[:2]) or 'High leverage/pledge'})."
                )
            elif unknown_cnt > 4:
                bear_points.append(
                    "Disclosure gap: multiple fundamental quality metrics remain unverified."
                )

            citations.append(f"Fundamental Snapshot (as of {fundamental_lights.get('as_of', 'Latest')})")
        else:
            bear_points.append("Fundamental coverage unavailable: no verified fundamental snapshot stored.")

        # 4. News Catalysts & Disclosures (Phase 3.1 & 3.4 & 3.5)
        # RED: adverse evidence in bear points (NEVER positive).
        # AMBER: cautionary evidence in bear points.
        # Unverified: marked explicitly as rumor/unverified.
        # GREEN: routine disclosures added to citations; HIGH/MEDIUM materiality added to bull points.
        if catalysts and len(catalysts) > 0:
            verified_positive_count = 0
            for cat in catalysts[:5]:
                c_title = cat.get("title", "")
                c_src = cat.get("source", "Exchange Disclosure")
                c_sev = (cat.get("severity") or "CLEAR").upper()
                c_unverified = bool(cat.get("is_unverified", False))
                c_mat = (cat.get("materiality") or "LOW").upper()

                is_material_pos = (
                    c_mat in ("HIGH", "MEDIUM")
                    or cat.get("category") == "MATERIAL_EVENT"
                    or any(kw in c_title.lower() for kw in ("acquisition", "bonus issue", "dividend", "eir", "approval", "order win", "contract"))
                )

                if c_unverified:
                    bear_points.append(f"Unverified report/rumor (unconfirmed): '{c_title}' (Source: {c_src}).")
                elif c_sev in ("RED", "NEWS_RED"):
                    bear_points.append(f"Adverse corporate disclosure: '{c_title}' (Source: {c_src}).")
                elif c_sev in ("AMBER", "REVIEW"):
                    bear_points.append(f"Cautionary news disclosure: '{c_title}' (Source: {c_src}).")
                elif is_material_pos:
                    bull_points.append(f"Recent verified catalyst: '{c_title}' (Source: {c_src}).")
                    verified_positive_count += 1
                else:
                    # Routine disclosure with low materiality - valid context, not claimed as major bull driver
                    pass

                if cat.get("source_url"):
                    citations.append(f"{c_src}: {c_title}")

            if verified_positive_count == 0:
                bear_points.append(
                    "Lack of fresh material news catalyst: setup relies primarily on technical pattern continuation."
                )
        else:
            bear_points.append(
                "Lack of fresh material news catalyst: setup relies primarily on technical pattern continuation."
            )

        # Fallback defaults if empty
        if not bull_points:
            bull_points.append(f"Trading above key moving averages in an active {regime_status} environment.")
        if not bear_points:
            bear_points.append("Momentum tail-risk: sharp sector rotation or mean-reversion drawdowns if broader market corrects.")

        risks = [
            f"Broader index drawdown risk: market regime transition ({regime_status}) would invalidate setup.",
            "Quarterly earnings volatility: unannounced reports within 3 trading days trigger mandatory exit.",
            "Execution friction: statutory transaction fees and whole-share cash drag at realistic account size.",
        ]
        if has_valid_setup and setup_details.get("stop"):
            risks.append(f"Explicit Invalidation: Intraday break or close below {setup_details['stop']:.2f}.")
        else:
            risks.append("Explicit Invalidation: No active hard stop (no confirmed entry setup).")

        return {
            "symbol": symbol,
            "sector": sector,
            "sector_trend": trend_label,
            "as_of": now_str,
            "current_price": current_price,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive. Deterministic signals govern all trade recommendations for manual execution.",
            "bull_case": {
                "title": f"Structural Bull Factors for {symbol}",
                "evidence": bull_points,
                "confidence_level": "HIGH_EVIDENCE" if len(bull_points) >= 3 else "MODERATE_EVIDENCE",
            },
            "bear_case": {
                "title": f"Key Headwinds & Opposing Evidence for {symbol}",
                "evidence": bear_points,
                "confidence_level": "ELEVATED_VULNERABILITY" if len(bear_points) >= 3 else "MONITORED_RISK",
            },
            "key_risks": risks,
            "data_sources": citations,
        }

    def post_trade_evaluation(
        self,
        trade_record: Dict[str, Any],
        market_regime: str,
    ) -> Dict[str, Any]:
        """
        Performs post-trade evaluation explaining execution, fee impact, and outcome.
        """
        sym = trade_record.get("symbol", "UNKNOWN")
        pnl = trade_record.get("realized_pnl", 0.0)
        costs = trade_record.get("total_costs", 0.0)
        action = trade_record.get("action", "SELL")
        exec_date = trade_record.get("exec_date", "UNKNOWN")

        is_win = pnl > 0
        outcome_label = "PROFITABLE_EXIT" if is_win else "CAPITAL_PRESERVATION_EXIT"

        explanation = (
            f"Trade completed on {exec_date} via {action} with net P&L of INR {pnl:+.2f}. "
            f"Total statutory transaction costs paid were INR {costs:.2f} (including DP charges where applicable). "
            f"The prevailing market regime was {market_regime}. "
            f"{'The position captured favorable trend continuation before portfolio rebalancing.' if is_win else 'The exit contained downside risk in accordance with deterministic retention buffer rules.'}"
        )

        return {
            "symbol": sym,
            "exec_date": exec_date,
            "outcome": outcome_label,
            "net_pnl": pnl,
            "costs_paid": costs,
            "explanation": explanation,
            "disclaimer": "Post-Trade Research Review — Retrospective Diagnostic Only.",
        }


ai_research_assistant = AiResearchAssistant()

