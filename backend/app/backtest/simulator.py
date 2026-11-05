import datetime
import logging
from typing import Dict, List, Optional
import pandas as pd
from pydantic import BaseModel

from app.backtest.metrics import BacktestMetrics, compute_backtest_metrics
from app.engine.costs import CostModel
from app.engine.gaprisk import calculate_effective_risk_per_share, compute_gap95
from app.engine.indicators import add_all_indicators
from app.engine.regime import evaluate_market_regime
from app.engine.screener import screener_engine
from app.engine.setups import SetupEngine, setup_engine
from app.engine.sizing import PositionSizer
from app.settings import settings

logger = logging.getLogger(__name__)


class SimulatedTrade(BaseModel):
    symbol: str
    setup: str
    entry_date: datetime.date
    entry_price: float
    exit_date: datetime.date
    exit_price: float
    exit_reason: str
    qty: int
    pnl: float
    r_multiple: float
    costs: float
    holding_days: int


class BacktestSimulator:
    """Event-driven daily backtesting simulator strictly implementing Section 12.2 fill rules."""

    def __init__(self, market: str = "IN", setup_engine_override: Optional[SetupEngine] = None):
        self.market = market.upper()
        self.mkt_cfg = settings.get_market_config(self.market)
        self.sizer = PositionSizer(self.market)
        self.setup_engine = setup_engine_override or setup_engine
        self.cost_model = CostModel(self.market)
        self.exit_cfg = settings.get_exit_config()
        self.slip_pct = self.mkt_cfg.slippage_pct / 100.0

    def _close_position(self, pos: Dict, exit_reference: float, exit_date: datetime.date, reason: str) -> SimulatedTrade:
        """Close remaining shares and aggregate any earlier partial exit into one trade record."""
        qty = int(pos["qty"])
        exit_price = exit_reference * (1.0 - self.slip_pct)
        risk_per_share = max(0.0, pos["entry_price"] - pos["initial_stop"])
        remaining_risk = risk_per_share * qty
        fees = self.cost_model.calculate_round_trip(
            pos["entry_price"], qty, remaining_risk, include_slippage=False
        )
        remaining_net = (exit_price - pos["entry_price"]) * qty - fees.total_cost
        net_pnl = float(pos.get("partial_net_pnl", 0.0)) + remaining_net
        actual_cost = (
            float(pos.get("partial_costs", 0.0)) + fees.total_cost
            + float(pos.get("entry_slippage_cost", 0.0))
            + abs(exit_reference - exit_price) * qty
        )
        original_qty = int(pos.get("original_qty", qty))
        total_risk = risk_per_share * original_qty
        if pos.get("partial_qty", 0):
            reason = f"Partial Target + {reason}"
        return SimulatedTrade(
            symbol=pos["symbol"], setup=pos["setup"], entry_date=pos["entry_date"],
            entry_price=round(pos["entry_price"], 4), exit_date=exit_date,
            exit_price=round(exit_price, 4), exit_reason=reason,
            qty=original_qty, pnl=round(net_pnl, 2),
            r_multiple=round(net_pnl / total_risk, 4) if total_risk > 0 else 0.0,
            costs=round(actual_cost, 2), holding_days=pos["days_held"],
        )

    def run(
        self,
        bars_data: Dict[str, pd.DataFrame],
        index_df: Optional[pd.DataFrame] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        capital: Optional[float] = None,
        setup_filter: str = "ALL",  # ALL, VCP, PULLBACK
    ) -> Dict:
        init_capital = capital or self.mkt_cfg.capital

        # Enrich all bars
        enriched: Dict[str, pd.DataFrame] = {}
        all_dates = set()
        for sym, df in bars_data.items():
            if df is not None and len(df) >= 30:
                e = add_all_indicators(df)
                enriched[sym] = e
                for d in e["date"]:
                    all_dates.add(d)

        sorted_dates = sorted(list(all_dates))
        if start_date:
            sorted_dates = [d for d in sorted_dates if d >= start_date]
        if end_date:
            sorted_dates = [d for d in sorted_dates if d <= end_date]

        if len(sorted_dates) < 20:
            return {
                "trades": [],
                "metrics": compute_backtest_metrics([]).model_dump(),
                "equity_curve": [{"date": str(datetime.date.today()), "equity": init_capital}],
            }

        open_positions: List[Dict] = []
        closed_trades: List[SimulatedTrade] = []
        pending_orders: List[Dict] = []  # signals generated on close of day t to execute on t+1
        daily_equity_curve = [{"date": str(sorted_dates[0]), "equity": init_capital}]

        for idx, current_date in enumerate(sorted_dates):
            # 1. PROCESS PENDING ORDERS ON DAY t+1 (Section 12.2 Fill Rules)
            remaining_orders = []
            for order in pending_orders:
                sym = order["symbol"]
                df = enriched.get(sym)
                if df is None:
                    continue
                day_bar = df[df["date"] == current_date]
                if day_bar.empty:
                    remaining_orders.append(order)
                    continue

                b = day_bar.iloc[0]
                open_p = float(b["open"])
                high_p = float(b["high"])
                trigger = order["trigger"]

                # Buy-stop entry rule:
                # if open >= trigger: fill at open (gap up); elif high >= trigger: fill at trigger
                fill_price = None
                if open_p >= trigger:
                    fill_price = open_p * (1.0 + self.slip_pct)  # adverse fill slippage
                    reference_price = open_p
                elif high_p >= trigger:
                    fill_price = trigger * (1.0 + self.slip_pct)
                    reference_price = trigger

                if fill_price is not None:
                    # Execute entry fill
                    qty = order["qty"]
                    open_positions.append(
                        {
                            "symbol": sym,
                            "setup": order["setup"],
                            "entry_date": current_date,
                            "entry_price": fill_price,
                            "entry_slippage_cost": max(0.0, fill_price - reference_price) * qty,
                            "original_qty": qty,
                            "partial_net_pnl": 0.0,
                            "partial_costs": 0.0,
                            "partial_qty": 0,
                            "initial_stop": order["stop"],
                            "active_stop": order["stop"],
                            "target1": order["target1"],
                            "qty": qty,
                            "highest_price": fill_price,
                            "days_held": 0,
                            "atr": order["atr"],
                            "has_taken_partial": False,
                        }
                    )
                # Orders are valid for 1 day only
            pending_orders = []

            # 2. MANAGE EXISTING OPEN POSITIONS ON CURRENT BAR
            active_positions = []
            for pos in open_positions:
                sym = pos["symbol"]
                df = enriched.get(sym)
                if df is None:
                    active_positions.append(pos)
                    continue
                day_bar = df[df["date"] == current_date]
                if day_bar.empty:
                    active_positions.append(pos)
                    continue

                b = day_bar.iloc[0]
                open_p = float(b["open"])
                high_p = float(b["high"])
                low_p = float(b["low"])
                close_p = float(b["close"])
                sma50_val = float(b.get("sma50", close_p))

                pos["days_held"] += 1
                pos["highest_price"] = max(pos["highest_price"], high_p)

                if pos.get("exit_pending"):
                    closed_trades.append(self._close_position(pos, open_p, current_date, pos["exit_pending"]))
                    continue

                # Same-bar ambiguity rule: if both stop and target touched, STOP HIT FIRST
                stop_hit = False
                target_hit = False
                exit_price = None
                exit_reason = None

                active_stop = pos["active_stop"]
                if open_p <= active_stop:
                    stop_hit = True
                    exit_price = open_p * (1.0 - self.slip_pct)
                    exit_reference = open_p
                    exit_reason = "Hard Stop (Gap Down)"
                elif low_p <= active_stop:
                    stop_hit = True
                    exit_price = active_stop * (1.0 - self.slip_pct)
                    exit_reference = active_stop
                    exit_reason = "Hard Stop"

                initial_r_per_share = pos["entry_price"] - pos["initial_stop"]
                partial_target = pos["entry_price"] + self.exit_cfg.partial_at_R * initial_r_per_share
                if high_p >= partial_target:
                    target_hit = True

                if stop_hit:
                    closed_trades.append(self._close_position(pos, exit_reference, current_date, exit_reason or "Stop"))
                    continue

                if target_hit and not pos["has_taken_partial"]:
                    r_initial_per_share = initial_r_per_share
                    original_qty = int(pos["original_qty"])
                    partial_qty = int(original_qty * self.exit_cfg.partial_fraction) if original_qty > 1 else 0
                    partial_qty = min(max(0, partial_qty), pos["qty"] - 1)
                    if partial_qty > 0:
                        partial_fill = partial_target * (1.0 - self.slip_pct)
                        partial_risk = r_initial_per_share * partial_qty
                        fees = self.cost_model.calculate_round_trip(
                            pos["entry_price"], partial_qty, partial_risk, include_slippage=False
                        )
                        entry_slippage_share = float(pos["entry_slippage_cost"]) * partial_qty / original_qty
                        pos["partial_net_pnl"] += (partial_fill - pos["entry_price"]) * partial_qty - fees.total_cost
                        pos["partial_costs"] += fees.total_cost + entry_slippage_share + abs(partial_target - partial_fill) * partial_qty
                        pos["entry_slippage_cost"] -= entry_slippage_share
                        pos["partial_qty"] += partial_qty
                        pos["qty"] -= partial_qty
                    # Move the remaining position to break-even as in ExitManager.
                    pos["active_stop"] = max(pos["active_stop"], pos["entry_price"])
                    pos["has_taken_partial"] = True

                # Close-based exits are detected on today's close and filled
                # at the next session's open, matching the build specification.
                r0 = pos["entry_price"] - pos["initial_stop"]
                if close_p < sma50_val:
                    pos["exit_pending"] = "Trend Break (< 50 SMA)"
                    active_positions.append(pos)
                    continue
                if (pos["days_held"] >= self.exit_cfg.time_stop_sessions
                        and close_p < pos["entry_price"] + self.exit_cfg.time_stop_min_R * r0):
                    pos["exit_pending"] = "Time Stop"
                    active_positions.append(pos)
                    continue

                # Trailing stop update (Chandelier trail)
                r0 = pos["entry_price"] - pos["initial_stop"]
                if pos["highest_price"] >= (pos["entry_price"] + r0):
                    chandelier = pos["highest_price"] - (3.0 * pos["atr"])
                    pos["active_stop"] = max(pos["active_stop"], pos["entry_price"], chandelier)

                active_positions.append(pos)

            open_positions = active_positions

            # 3. GENERATE NEW SIGNALS ON CLOSE OF CURRENT BAR (NO LOOK-AHEAD)
            if len(open_positions) + len(pending_orders) < self.mkt_cfg.max_open_positions:
                for sym, df in enriched.items():
                    if len(open_positions) + len(pending_orders) >= self.mkt_cfg.max_open_positions:
                        break
                    sub_df = df[df["date"] <= current_date]
                    if len(sub_df) < 55:
                        continue

                    # Check Setups
                    cand = None
                    if setup_filter in ("ALL", "VCP"):
                        cand = self.setup_engine.evaluate_vcp_breakout(sym, sub_df, tick=self.mkt_cfg.tick)
                    if not cand and setup_filter in ("ALL", "PULLBACK"):
                        cand = self.setup_engine.evaluate_pullback(sym, sub_df, tick=self.mkt_cfg.tick)

                    # Under the opt-in signal-day-excluded pivot policy, a bar
                    # that already closed beyond the prior pivot is extended.
                    # It is excluded from next-day buy-stop entries (no chase).
                    if cand and cand.classification == "BROKE_OUT_TODAY":
                        continue

                    if cand:
                        gap95 = compute_gap95(sub_df)
                        eff_risk = calculate_effective_risk_per_share(cand.trigger, cand.stop, gap95)
                        sizing = self.sizer.calculate_size(
                            cand.symbol,
                            cand.trigger,
                            cand.stop,
                            eff_risk,
                            capital_override=init_capital,
                            current_open_positions=len(open_positions) + len(pending_orders),
                            current_open_heat=sum(max(0.0, p["entry_price"] - p["initial_stop"]) * p["qty"] for p in open_positions)
                            + sum(o.get("risk_amount", 0.0) for o in pending_orders),
                        )
                        if sizing.passed and sizing.qty > 0:
                            pending_orders.append(
                                {
                                    "symbol": cand.symbol,
                                    "setup": cand.setup,
                                    "trigger": cand.trigger,
                                    "stop": cand.stop,
                                    "target1": cand.target1,
                                    "qty": sizing.qty,
                                    "atr": cand.atr,
                                    "risk_amount": sizing.risk_amount,
                                }
                            )

            # Daily portfolio mark-to-market: include open risk and a
            # conservative estimate of remaining round-trip costs.
            realized_pnl = sum(trade.pnl for trade in closed_trades)
            unrealized_pnl = 0.0
            for pos in open_positions:
                pos_df = enriched.get(pos["symbol"])
                if pos_df is None:
                    continue
                available = pos_df[pos_df["date"] <= current_date]
                if available.empty:
                    continue
                mark = float(available.iloc[-1]["close"])
                initial_risk = max(0.0, pos["entry_price"] - pos["initial_stop"]) * pos["qty"]
                estimated_fees = self.cost_model.calculate_round_trip(
                    pos["entry_price"], pos["qty"], initial_risk, include_slippage=False
                ).total_cost
                estimated_exit_slippage = mark * pos["qty"] * self.slip_pct
                unrealized_pnl += float(pos.get("partial_net_pnl", 0.0)) + (mark - pos["entry_price"]) * pos["qty"] - estimated_fees - estimated_exit_slippage
            daily_equity_curve.append({"date": str(current_date), "equity": round(init_capital + realized_pnl + unrealized_pnl, 2)})

        # Liquidate positions still open at the final available close so P&L,
        # trades and the final equity point all cover the same test boundary.
        for pos in open_positions:
            pos_df = enriched.get(pos["symbol"])
            if pos_df is None:
                continue
            available = pos_df[pos_df["date"] <= sorted_dates[-1]]
            if available.empty:
                continue
            last_bar = available.iloc[-1]
            closed_trades.append(self._close_position(
                pos, float(last_bar["close"]), last_bar["date"], "End of Test (liquidated)"
            ))
        if daily_equity_curve:
            daily_equity_curve[-1]["equity"] = round(init_capital + sum(trade.pnl for trade in closed_trades), 2)

        # Compute performance metrics
        trades_dicts = [t.model_dump() for t in closed_trades]
        years_span = (sorted_dates[-1] - sorted_dates[0]).days / 365.25 if len(sorted_dates) > 1 else 1.0
        metrics = compute_backtest_metrics(
            trades_dicts, initial_capital=init_capital, years=years_span,
            equity_curve=daily_equity_curve,
        )

        return {
            "trades": trades_dicts,
            "metrics": metrics.model_dump(),
            "equity_curve": daily_equity_curve,
            "survivorship_bias_notice": "Optimistic: survivorship bias present (current index constituents used for historical backtest).",
        }

