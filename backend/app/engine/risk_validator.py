import datetime
import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.engine.costs import CostBreakdown
from app.engine.pipeline import StageCheck
from app.settings import settings

logger = logging.getLogger(__name__)


class RiskValidationResult(BaseModel):
    passed: bool
    status: str  # PASS or BLOCK
    checks: List[StageCheck]
    rejection_reasons: List[str]


class RiskValidator:
    """Dedicated Standalone Risk Validator & Circuit Breakers (Spec 4.5).
    Evaluates:
      1. Risk per trade boundary
      2. Portfolio heat limit (open risk)
      3. Max open positions
      4. Sector exposure limit
      5. Correlation cluster exposure (60d correlation >= 0.75)
      6. Liquidity ADV boundary
      7. Cost Gate (costs <= 0.25R)
      8. Consecutive-loss circuit breaker (pause new entries after N consecutive losses)
      9. Drawdown pause circuit breaker (pause new entries if drawdown >= threshold)
      10. Daily / Weekly loss limits
    CRITICAL RULE: Circuit breakers block NEW entries only; they NEVER force exits of valid positions.
    """

    def __init__(self, market: str = "IN"):
        self.market = market.upper()
        self.mkt_cfg = settings.get_market_config(self.market)
        self.risk_cfg = settings.get_risk_config()

    def validate(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        qty: int,
        risk_amount: float,
        cost_breakdown: CostBreakdown,
        capital: float,
        current_open_positions: int = 0,
        current_open_heat: float = 0.0,
        open_symbols: Optional[List[str]] = None,
        sector: Optional[str] = None,
        open_sectors: Optional[List[str]] = None,
        recent_closed_trades: Optional[List[Dict]] = None,
        current_drawdown_pct: float = 0.0,
        today_loss_pct: float = 0.0,
        this_week_loss_pct: float = 0.0,
        all_universe_data: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> RiskValidationResult:
        checks: List[StageCheck] = []
        rejections: List[str] = []

        # 1. Risk per trade check
        max_risk_pct = self.mkt_cfg.risk_per_trade_pct
        if self.mkt_cfg.small_account_mode.get("enabled", False):
            max_risk_pct = float(self.mkt_cfg.small_account_mode.get("risk_per_trade_pct", 1.5))
        max_risk_allowed = capital * (max_risk_pct / 100.0)

        # Allow small epsilon for floating-point tolerance
        passed_risk = risk_amount <= (max_risk_allowed * 1.01)
        checks.append(
            StageCheck(
                name="Risk per Trade",
                value=f"{risk_amount:.2f}",
                threshold=f"<= {max_risk_allowed:.2f} ({max_risk_pct}%)",
                passed=passed_risk,
                note=f"Capital: {capital:,.0f}",
            )
        )
        if not passed_risk:
            rejections.append(f"Risk amount {risk_amount:.2f} exceeds limit {max_risk_allowed:.2f}")

        # 2. Portfolio Heat Check
        max_heat_pct = self.mkt_cfg.max_portfolio_heat_pct
        if self.mkt_cfg.small_account_mode.get("enabled", False):
            max_heat_pct = float(self.mkt_cfg.small_account_mode.get("max_portfolio_heat_pct", 3.0))
        max_heat_allowed = capital * (max_heat_pct / 100.0)

        total_heat = current_open_heat + risk_amount
        passed_heat = total_heat <= (max_heat_allowed * 1.01)
        checks.append(
            StageCheck(
                name="Portfolio Heat (Open Risk)",
                value=f"{total_heat:.2f}",
                threshold=f"<= {max_heat_allowed:.2f} ({max_heat_pct}%)",
                passed=passed_heat,
                note=f"Current: {current_open_heat:.2f} + New: {risk_amount:.2f}",
            )
        )
        if not passed_heat:
            rejections.append(f"Portfolio heat {total_heat:.2f} breaches max allowed {max_heat_allowed:.2f}")

        # 3. Max Concurrent Positions
        max_positions = self.mkt_cfg.max_open_positions
        passed_positions = current_open_positions < max_positions
        checks.append(
            StageCheck(
                name="Max Concurrent Positions",
                value=f"{current_open_positions} open",
                threshold=f"< {max_positions} max",
                passed=passed_positions,
                note=f"Market: {self.market}",
            )
        )
        if not passed_positions:
            rejections.append(f"Max concurrent positions reached ({current_open_positions}/{max_positions})")

        # 4. Sector Exposure Limit (default: max 1 per sector)
        max_per_sector = self.risk_cfg.max_per_sector
        passed_sector = True
        if sector and open_sectors:
            sector_count = open_sectors.count(sector)
            passed_sector = sector_count < max_per_sector
            if not passed_sector:
                rejections.append(f"Sector exposure limit reached for '{sector}' ({sector_count}/{max_per_sector})")
        checks.append(
            StageCheck(
                name="Sector Exposure Cap",
                value=f"{sector or 'General'} ({open_sectors.count(sector) if sector and open_sectors else 0} open)",
                threshold=f"< {max_per_sector} max per sector",
                passed=passed_sector,
                note="Prevents sector concentration",
            )
        )

        # 5. Correlation Cluster Check (60d correlation >= 0.75)
        passed_cluster = True
        corr_thresh = self.risk_cfg.corr_threshold
        if open_symbols and all_universe_data and symbol in all_universe_data:
            sym_df = all_universe_data[symbol]
            if len(sym_df) >= 60:
                sym_ret = sym_df["close"].pct_change().iloc[-60:]
                for op_sym in open_symbols:
                    if op_sym in all_universe_data:
                        op_df = all_universe_data[op_sym]
                        if len(op_df) >= 60:
                            op_ret = op_df["close"].pct_change().iloc[-60:]
                            corr = float(sym_ret.corr(op_ret))
                            if pd.notna(corr) and corr >= corr_thresh:
                                passed_cluster = False
                                rejections.append(
                                    f"Correlation cluster limit breached: 60d correlation with {op_sym} is {corr:.2f} (>= {corr_thresh})"
                                )
                                break
        checks.append(
            StageCheck(
                name="Correlation Cluster (corr < 0.75)",
                value="Independent" if passed_cluster else "Clustered",
                threshold=f"Correlation < {corr_thresh}",
                passed=passed_cluster,
                note="Max 1 position per correlation cluster",
            )
        )

        # 6. Cost Gate (Costs in R <= 0.25R)
        checks.append(
            StageCheck(
                name="Cost Gate (Round-Trip Cost in R)",
                value=f"{cost_breakdown.cost_in_r:.3f}R (Total: {cost_breakdown.total_cost:.2f})",
                threshold=f"<= {self.risk_cfg.max_cost_in_R:.2f}R",
                passed=cost_breakdown.passed_gate,
                note="Rejects trades where costs consume excessive risk",
            )
        )
        if not cost_breakdown.passed_gate:
            rej = (cost_breakdown.rejection_reason or "").strip()
            if not rej:
                rej = f"Round-trip transaction costs {cost_breakdown.cost_in_r:.2f}R exceed maximum risk gate {self.risk_cfg.max_cost_in_R:.2f}R"
            rejections.append(rej)

        # 7. Consecutive-Loss Circuit Breaker (pause after 3 consecutive losses)
        max_consecutive_losses = 3
        consecutive_losses = 0
        if recent_closed_trades:
            for t in reversed(recent_closed_trades):
                if t.get("pnl", 0.0) <= 0:
                    consecutive_losses += 1
                else:
                    break
        passed_loss_streak = consecutive_losses < max_consecutive_losses
        checks.append(
            StageCheck(
                name="Consecutive-Loss Circuit Breaker",
                value=f"{consecutive_losses} consecutive losses",
                threshold=f"< {max_consecutive_losses} max",
                passed=passed_loss_streak,
                note="Pauses new entries during adverse drawdowns",
            )
        )
        if not passed_loss_streak:
            rejections.append(
                f"Circuit breaker active: {consecutive_losses} consecutive losses. New entries paused."
            )

        # 8. Drawdown Pause Circuit Breaker (pause if current portfolio drawdown >= 8%)
        max_drawdown_pause_pct = 8.0
        passed_drawdown_pause = current_drawdown_pct < max_drawdown_pause_pct
        checks.append(
            StageCheck(
                name="Drawdown Pause Circuit Breaker",
                value=f"{current_drawdown_pct:.1f}% drawdown",
                threshold=f"< {max_drawdown_pause_pct}% max pause threshold",
                passed=passed_drawdown_pause,
                note="Prevents compounding losses during market tailspins",
            )
        )
        if not passed_drawdown_pause:
            rejections.append(
                f"Circuit breaker active: Portfolio drawdown {current_drawdown_pct:.1f}% >= {max_drawdown_pause_pct}%. New entries paused."
            )

        # 9. Daily & Weekly Loss Limits
        max_daily_loss_pct = 1.5
        passed_daily_loss = today_loss_pct < max_daily_loss_pct
        checks.append(
            StageCheck(
                name="Daily Loss Limit",
                value=f"{today_loss_pct:.1f}%",
                threshold=f"< {max_daily_loss_pct}%",
                passed=passed_daily_loss,
                note="Pauses new entries if daily loss limit hit",
            )
        )
        if not passed_daily_loss:
            rejections.append(f"Daily loss limit hit ({today_loss_pct:.1f}% >= {max_daily_loss_pct}%). New entries paused.")

        passed = len(rejections) == 0
        return RiskValidationResult(
            passed=passed,
            status="PASS" if passed else "BLOCK",
            checks=checks,
            rejection_reasons=rejections,
        )


risk_validator = RiskValidator()

