import math
from typing import Dict, List, Optional
from pydantic import BaseModel

from app.engine.costs import CostBreakdown, CostModel
from app.settings import settings


class SizingResult(BaseModel):
    symbol: str
    qty: int
    risk_amount: float
    position_value: float
    effective_risk_per_share: float
    cost_breakdown: CostBreakdown
    passed: bool
    rejection_reason: str = ""


class PositionSizer:
    """Calculates position size strictly respecting risk %, heat, caps, and the cost gate."""

    def __init__(self, market: str = "IN"):
        self.market = market.upper()
        self.mkt_cfg = settings.get_market_config(self.market)
        self.risk_cfg = settings.get_risk_config()
        self.cost_model = CostModel(self.market)

    def calculate_size(
        self,
        symbol: str,
        entry: float,
        stop: float,
        effective_risk_per_share: float,
        capital_override: Optional[float] = None,
        current_open_positions: int = 0,
        current_open_heat: float = 0.0,
    ) -> SizingResult:
        capital = capital_override or self.mkt_cfg.capital

        # Check small account mode
        risk_pct = self.mkt_cfg.risk_per_trade_pct
        max_heat_pct = self.mkt_cfg.max_portfolio_heat_pct
        if self.mkt_cfg.small_account_mode.get("enabled", False):
            risk_pct = float(self.mkt_cfg.small_account_mode.get("risk_per_trade_pct", 1.5))
            max_heat_pct = float(self.mkt_cfg.small_account_mode.get("max_portfolio_heat_pct", 3.0))

        # Check open positions limit
        if current_open_positions >= self.mkt_cfg.max_open_positions:
            return SizingResult(
                symbol=symbol,
                qty=0,
                risk_amount=0.0,
                position_value=0.0,
                effective_risk_per_share=effective_risk_per_share,
                cost_breakdown=CostBreakdown(
                    brokerage=0, stt=0, exchange_charges=0, sebi_charges=0, stamp_duty=0,
                    dp_charges=0, gst=0, slippage=0, total_cost=0, cost_in_r=0, passed_gate=False
                ),
                passed=False,
                rejection_reason=f"Max open positions reached ({current_open_positions}/{self.mkt_cfg.max_open_positions})",
            )

        # Risk amount in currency
        risk_amount = capital * (risk_pct / 100.0)

        # Check portfolio heat limit
        max_heat_amount = capital * (max_heat_pct / 100.0)
        if (current_open_heat + risk_amount) > max_heat_amount:
            return SizingResult(
                symbol=symbol,
                qty=0,
                risk_amount=risk_amount,
                position_value=0.0,
                effective_risk_per_share=effective_risk_per_share,
                cost_breakdown=CostBreakdown(
                    brokerage=0, stt=0, exchange_charges=0, sebi_charges=0, stamp_duty=0,
                    dp_charges=0, gst=0, slippage=0, total_cost=0, cost_in_r=0, passed_gate=False
                ),
                passed=False,
                rejection_reason=f"Portfolio heat limit breached ({current_open_heat + risk_amount:.1f} > max {max_heat_amount:.1f})",
            )

        if effective_risk_per_share <= 0:
            return SizingResult(
                symbol=symbol,
                qty=0,
                risk_amount=risk_amount,
                position_value=0.0,
                effective_risk_per_share=effective_risk_per_share,
                cost_breakdown=CostBreakdown(
                    brokerage=0, stt=0, exchange_charges=0, sebi_charges=0, stamp_duty=0,
                    dp_charges=0, gst=0, slippage=0, total_cost=0, cost_in_r=0, passed_gate=False
                ),
                passed=False,
                rejection_reason="Invalid effective risk per share <= 0",
            )

        # 1. Qty based on risk
        qty_risk = math.floor(risk_amount / effective_risk_per_share)

        # 2. Qty cap based on max single position %
        max_pos_val = capital * (self.risk_cfg.max_position_pct / 100.0)
        qty_cap = math.floor(max_pos_val / entry) if entry > 0 else 0

        qty = min(qty_risk, qty_cap)

        if qty < 1:
            return SizingResult(
                symbol=symbol,
                qty=0,
                risk_amount=risk_amount,
                position_value=0.0,
                effective_risk_per_share=effective_risk_per_share,
                cost_breakdown=CostBreakdown(
                    brokerage=0, stt=0, exchange_charges=0, sebi_charges=0, stamp_duty=0,
                    dp_charges=0, gst=0, slippage=0, total_cost=0, cost_in_r=0, passed_gate=False
                ),
                passed=False,
                rejection_reason=f"Calculated quantity is 0 (price {entry:.2f} requires > risk allocation {risk_amount:.2f})",
            )

        position_value = entry * qty

        # Enforce Cost Gate
        cost_breakdown = self.cost_model.calculate_round_trip(entry, qty, risk_amount)
        if not cost_breakdown.passed_gate:
            return SizingResult(
                symbol=symbol,
                qty=qty,
                risk_amount=risk_amount,
                position_value=position_value,
                effective_risk_per_share=effective_risk_per_share,
                cost_breakdown=cost_breakdown,
                passed=False,
                rejection_reason=cost_breakdown.rejection_reason,
            )

        return SizingResult(
            symbol=symbol,
            qty=qty,
            risk_amount=round(risk_amount, 2),
            position_value=round(position_value, 2),
            effective_risk_per_share=round(effective_risk_per_share, 2),
            cost_breakdown=cost_breakdown,
            passed=True,
            rejection_reason="",
        )

