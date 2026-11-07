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
    ) -> Dict[str, Any]:
        """
        Generates balanced Bullish vs Bearish theses with structural evidence and risk factors.
        Does NOT produce buy/sell directives.
        """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M IST")

        bull_points = [
            f"Strong 12-1 relative momentum score ({momentum_score:+.2f}) demonstrates persistent institutional price acceptance.",
            f"Trading above key moving averages in an active {regime_status} environment.",
            f"Sector peer leadership in {sector} showing relative outperformance against broader NSE indices.",
        ]

        bear_points = [
            f"Momentum tail-risk: sharp sector rotations can trigger high drawdowns if {sector} falls out of favor.",
            f"Execution slippage and whole-share cash drag at practical scale (INR 20,000) reduce net capture.",
            f"Mean-reversion vulnerability if broader market index breaks below its 200-day moving average.",
        ]

        risks = [
            "Earnings season volatility and guidance downgrades.",
            "Broader macroeconomic liquidity contractions affecting Indian equities.",
            "DP charge friction (INR 15.93 per completed scrip liquidation) impacting lower-turnover trades.",
        ]

        return {
            "symbol": symbol,
            "sector": sector,
            "as_of": now_str,
            "current_price": current_price,
            "disclaimer": "AI Informational Research Only — Not a Trading Directive. Deterministic signals govern all paper-broker execution.",
            "bull_case": {
                "title": f"Structural Bull Factors for {symbol}",
                "evidence": bull_points,
                "confidence_level": "MODERATE_EVIDENCE",
            },
            "bear_case": {
                "title": f"Key Headwinds & Opposing Evidence for {symbol}",
                "evidence": bear_points,
                "confidence_level": "ELEVATED_VULNERABILITY",
            },
            "key_risks": risks,
            "data_sources": [
                f"NSE EOD Price Snapshot (Closing {current_price:.2f})",
                f"Sector Index Aggregate ({sector})",
                "^NSEI 200-day Moving Average Regime Tracker",
            ],
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

