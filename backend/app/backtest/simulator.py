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
        self.slip_pct = self.mkt_cfg.slippage_pct / 100.0

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
                    fill_price = open_p * (1.0 + self.slip_pct)  # gap up with slippage
                elif high_p >= trigger:
                    fill_price = trigger * (1.0 + self.slip_pct)

                if fill_price is not None:
                    # Execute entry fill
                    qty = order["qty"]
                    open_positions.append(
                        {
                            "symbol": sym,
                            "setup": order["setup"],
                            "entry_date": current_date,
                            "entry_price": fill_price,
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

                # Same-bar ambiguity rule: if both stop and target touched, STOP HIT FIRST
                stop_hit = False
                target_hit = False
                exit_price = None
                exit_reason = None

                active_stop = pos["active_stop"]
                if open_p <= active_stop:
                    stop_hit = True
                    exit_price = open_p * (1.0 - self.slip_pct)  # gap through stop
                    exit_reason = "Hard Stop (Gap Down)"
                elif low_p <= active_stop:
                    stop_hit = True
                    exit_price = active_stop * (1.0 - self.slip_pct)
                    exit_reason = "Hard Stop"

                if high_p >= pos["target1"]:
                    target_hit = True

                if stop_hit:
                    # Exit triggered
                    r_initial = pos["entry_price"] - pos["initial_stop"]
                    pnl_per_share = exit_price - pos["entry_price"]
                    gross_pnl = pnl_per_share * pos["qty"]
                    cost_breakdown = self.cost_model.calculate_round_trip(
                        pos["entry_price"], pos["qty"], r_initial * pos["qty"]
                    )
                    net_pnl = gross_pnl - cost_breakdown.total_cost
                    r_mult = (net_pnl / (r_initial * pos["qty"])) if r_initial > 0 else 0.0

                    closed_trades.append(
                        SimulatedTrade(
                            symbol=sym,
                            setup=pos["setup"],
                            entry_date=pos["entry_date"],
                            entry_price=round(pos["entry_price"], 2),
                            exit_date=current_date,
                            exit_price=round(exit_price, 2),
                            exit_reason=exit_reason or "Stop",
                            qty=pos["qty"],
                            pnl=round(net_pnl, 2),
                            r_multiple=round(r_mult, 2),
                            costs=round(cost_breakdown.total_cost, 2),
                            holding_days=pos["days_held"],
                        )
                    )
                    continue

                if target_hit and not pos["has_taken_partial"]:
                    # Breakeven + trail on target reach
                    pos["active_stop"] = max(pos["active_stop"], pos["entry_price"])
                    pos["has_taken_partial"] = True

                # Trend break: close below 50 SMA -> exit next session
                if close_p < sma50_val:
                    exit_price = close_p * (1.0 - self.slip_pct)
                    r_initial = pos["entry_price"] - pos["initial_stop"]
                    gross_pnl = (exit_price - pos["entry_price"]) * pos["qty"]
                    cost_breakdown = self.cost_model.calculate_round_trip(
                        pos["entry_price"], pos["qty"], r_initial * pos["qty"]
                    )
                    net_pnl = gross_pnl - cost_breakdown.total_cost
                    r_mult = (net_pnl / (r_initial * pos["qty"])) if r_initial > 0 else 0.0

                    closed_trades.append(
                        SimulatedTrade(
                            symbol=sym,
                            setup=pos["setup"],
                            entry_date=pos["entry_date"],
                            entry_price=round(pos["entry_price"], 2),
                            exit_date=current_date,
                            exit_price=round(exit_price, 2),
                            exit_reason="Trend Break (< 50 SMA)",
                            qty=pos["qty"],
                            pnl=round(net_pnl, 2),
                            r_multiple=round(r_mult, 2),
                            costs=round(cost_breakdown.total_cost, 2),
                            holding_days=pos["days_held"],
                        )
                    )
                    continue

                # Trailing stop update (Chandelier trail)
                r0 = pos["entry_price"] - pos["initial_stop"]
                if pos["highest_price"] >= (pos["entry_price"] + r0):
                    chandelier = pos["highest_price"] - (3.0 * pos["atr"])
                    pos["active_stop"] = max(pos["active_stop"], pos["entry_price"], chandelier)

                active_positions.append(pos)

            open_positions = active_positions

            # 3. GENERATE NEW SIGNALS ON CLOSE OF CURRENT BAR (NO LOOK-AHEAD)
            if len(open_positions) < self.mkt_cfg.max_open_positions:
                for sym, df in enriched.items():
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
                            current_open_positions=len(open_positions),
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
                                }
                            )

        # Compute performance metrics
        trades_dicts = [t.model_dump() for t in closed_trades]
        years_span = (sorted_dates[-1] - sorted_dates[0]).days / 365.25 if len(sorted_dates) > 1 else 1.0
        metrics = compute_backtest_metrics(trades_dicts, initial_capital=init_capital, years=years_span)

        # Generate equity curve points
        eq_curve = [{"date": str(sorted_dates[0]), "equity": init_capital}]
        cum_equity = init_capital
        for t in closed_trades:
            cum_equity += t.pnl
            eq_curve.append({"date": str(t.exit_date), "equity": round(cum_equity, 2)})

        return {
            "trades": trades_dicts,
            "metrics": metrics.model_dump(),
            "equity_curve": eq_curve,
            "survivorship_bias_notice": "Optimistic: survivorship bias present (current index constituents used for historical backtest).",
        }

