from typing import Dict
from pydantic import BaseModel
from app.settings import settings


class CostBreakdown(BaseModel):
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    dp_charges: float
    gst: float
    slippage: float
    total_cost: float
    cost_in_r: float
    passed_gate: bool
    rejection_reason: str = ""


class CostModel:
    """Calculates realistic round-trip trading costs and enforces the Cost Gate."""

    def __init__(self, market: str = "IN"):
        self.market = market.upper()
        self.cfg = settings.get_cost_config(self.market)
        self.risk_cfg = settings.get_risk_config()
        self.mkt_cfg = settings.get_market_config(self.market)

    def calculate_round_trip(
        self, price: float, qty: int, risk_amount: float, include_slippage: bool = True
    ) -> CostBreakdown:
        if qty <= 0 or price <= 0:
            return CostBreakdown(
                brokerage=0.0,
                stt=0.0,
                exchange_charges=0.0,
                sebi_charges=0.0,
                stamp_duty=0.0,
                dp_charges=0.0,
                gst=0.0,
                slippage=0.0,
                total_cost=0.0,
                cost_in_r=0.0,
                passed_gate=False,
                rejection_reason="Invalid price or quantity <= 0",
            )

        buy_turnover = price * qty
        sell_turnover = price * qty  # baseline assumption for cost estimation
        total_turnover = buy_turnover + sell_turnover

        if self.market == "IN":
            # 1. Brokerage (Zerodha delivery is flat 0)
            brokerage = 0.0
            if self.cfg.brokerage.get("type") == "flat":
                brokerage = float(self.cfg.brokerage.get("flat", 0.0)) * 2

            # 2. STT: 0.1% on buy and 0.1% on sell
            stt = (self.cfg.stt_pct_buy / 100.0 * buy_turnover) + (
                self.cfg.stt_pct_sell / 100.0 * sell_turnover
            )

            # 3. Exchange transaction charges: ~0.003% of turnover
            exchange_charges = (self.cfg.exchange_txn_pct / 100.0) * total_turnover

            # 4. SEBI turnover fee: INR 10 per crore
            sebi_charges = (self.cfg.sebi_per_crore / 10000000.0) * total_turnover

            # 5. Stamp duty: 0.015% on buy
            stamp_duty = (self.cfg.stamp_buy_pct / 100.0) * buy_turnover

            # 6. DP flat charge on sell: 13.5 per scrip
            dp_charges = self.cfg.dp_flat_per_scrip_sell

            # 7. GST: 18% on (brokerage + exchange_charges + sebi_charges + dp_charges)
            gst_base = brokerage + exchange_charges + sebi_charges + dp_charges
            gst = (self.cfg.gst_pct / 100.0) * gst_base

            # 8. Slippage
            slip_pct = self.mkt_cfg.slippage_pct / 100.0
            slippage = total_turnover * slip_pct if include_slippage else 0.0

            total_cost = (
                brokerage
                + stt
                + exchange_charges
                + sebi_charges
                + stamp_duty
                + dp_charges
                + gst
                + slippage
            )

        else:
            # US Market
            commission = self.cfg.commission_per_order * 2
            regulatory = (self.cfg.regulatory_pct / 100.0) * sell_turnover
            fx_spread = (self.cfg.fx_spread_pct / 100.0) * total_turnover
            slip_pct = self.mkt_cfg.slippage_pct / 100.0
            slippage = total_turnover * slip_pct if include_slippage else 0.0

            brokerage = commission
            stt = 0.0
            exchange_charges = regulatory
            sebi_charges = 0.0
            stamp_duty = 0.0
            dp_charges = fx_spread
            gst = 0.0
            total_cost = commission + regulatory + fx_spread + slippage

        # Cost Gate evaluation
        cost_in_r = (total_cost / risk_amount) if risk_amount > 0 else 999.0
        max_cost_r = self.risk_cfg.max_cost_in_R
        passed = cost_in_r <= max_cost_r

        rejection_reason = ""
        if not passed:
            rejection_reason = (
                f"Round-trip costs ({total_cost:.2f}) consume {cost_in_r:.2f}R of risk "
                f"(max allowed is {max_cost_r:.2f}R). Trade is uneconomical for account size."
            )

        return CostBreakdown(
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange_charges=round(exchange_charges, 2),
            sebi_charges=round(sebi_charges, 2),
            stamp_duty=round(stamp_duty, 2),
            dp_charges=round(dp_charges, 2),
            gst=round(gst, 2),
            slippage=round(slippage, 2),
            total_cost=round(total_cost, 2),
            cost_in_r=round(cost_in_r, 3),
            passed_gate=passed,
            rejection_reason=rejection_reason,
        )
