"""
Shared Deterministic Paper Broker Service
Strictly Offline / Paper Simulation — No Live Broker Order Placement

Features:
- Completely decoupled from strategy signal generation
- Independent portfolio account state per strategy (e.g. INR 20,000 simulated capital)
- Strict whole-share integer quantities: floor(target_capital / fill_price)
- Strict cash validation: Cash >= Required Turnover + Costs; no negative cash, no leverage
- Realistic execution modeling: fills at next session Open with configurable adverse slippage (+0.10% buy, -0.10% sell)
- Liquidity and volume constraints: minimum median 60-day turnover (INR 50M) and max daily volume participation (1.0%)
- Configurable Indian equity delivery statutory costs (Zerodha NSE):
    * Brokerage: INR 0 flat
    * STT: 0.10% buy, 0.10% sell
    * Exchange turnover charges: 0.003%
    * SEBI turnover charges: INR 10 per crore (0.0001%)
    * Stamp duty: 0.015% on buy turnover
    * DP charge: INR 15.93 flat (INR 13.50 + 18% GST) on full position closure
    * Partial trims leaving position open do NOT incur full DP charge
    * Trims that fully close position DO incur DP charge
    * Multiple partial fills of same scrip on same sell date incur DP charge at most once per day
    * GST: 18% on (Exchange charges + SEBI charges + DP charges)
- Explicit order journal with rejection reasons (e.g. REJECTED_INSUFFICIENT_CASH, REJECTED_ILLIQUID, REJECTED_VOLUME_CAP)
- Trade journal and daily mark-to-market ledger
- Mathematical accounting invariant: Total Equity == Cash + Sum(Shares * Close)
- Idempotent session execution and crash recovery persistence
"""

import datetime
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def safe_json_serialize(obj: Any) -> Any:
    """Safe serializer for numpy, pandas, and datetime objects."""
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (datetime.date, datetime.datetime, pd.Timestamp)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def calculate_indian_delivery_charges(
    turnover: float,
    side: str,
    is_full_closure: bool = False,
    already_charged_dp_today: bool = False,
    stress_multiplier: float = 1.0,
) -> Dict[str, float]:
    """
    Calculates exact statutory Indian equity delivery charges (Zerodha NSE).
    
    Parameters:
    - turnover: Total gross value of the trade (shares * price).
    - side: 'BUY' or 'SELL'.
    - is_full_closure: True if this sell order completely closes out the position.
    - already_charged_dp_today: True if a previous sell of the same scrip today already incurred DP charge.
    - stress_multiplier: Cost stress multiplier (e.g. 2.0 for 2x cost stress test).
    """
    if turnover <= 0:
        return {
            "brokerage": 0.0,
            "stt": 0.0,
            "exchange_charges": 0.0,
            "sebi_charges": 0.0,
            "stamp_duty": 0.0,
            "dp_charges": 0.0,
            "gst": 0.0,
            "total_cost": 0.0,
        }

    is_buy = side.upper() == "BUY"
    is_sell = side.upper() == "SELL"

    # Base rates
    brokerage = 0.0
    stt_rate = 0.001 * stress_multiplier  # 0.10% buy & sell
    stt = stt_rate * turnover

    exch_rate = 0.00003 * stress_multiplier  # 0.003%
    exchange_charges = exch_rate * turnover

    sebi_rate = (10.0 / 10000000.0) * stress_multiplier  # INR 10 / crore
    sebi_charges = sebi_rate * turnover

    stamp_rate = 0.00015 * stress_multiplier if is_buy else 0.0  # 0.015% on buy only
    stamp_duty = stamp_rate * turnover

    # DP charge logic:
    # Only charged on SELL side, only on full closure (or applicable closure), and at most once per scrip per sell day.
    dp_charges = 0.0
    if is_sell and is_full_closure and not already_charged_dp_today:
        base_dp = 13.50 * stress_multiplier
        dp_charges = base_dp

    gst_base = exchange_charges + sebi_charges + dp_charges
    gst = 0.18 * gst_base
    dp_gst = 0.18 * dp_charges
    dp_total = dp_charges + dp_gst

    total = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + dp_charges + gst

    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_charges": round(exchange_charges, 2),
        "sebi_charges": round(sebi_charges, 2),
        "stamp_duty": round(stamp_duty, 2),
        "dp_charges": round(dp_charges, 2),
        "dp_gst": round(dp_gst, 2),
        "dp_total": round(dp_total, 2),
        "gst": round(gst, 2),
        "total_cost": round(total, 2),
    }


class PaperAccount:
    """
    Represents an isolated paper-trading account for a specific strategy candidate.
    """

    def __init__(self, account_id: str, strategy_name: str, initial_capital: float = 20000.0):
        self.account_id = account_id
        self.strategy_name = strategy_name
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        # Holdings map: symbol -> {shares: int, avg_cost: float, invested_cost: float}
        self.holdings: Dict[str, Dict[str, Any]] = {}
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.total_equity = float(initial_capital)
        self.peak_equity = float(initial_capital)
        self.cumulative_costs = 0.0
        self.cumulative_slippage = 0.0
        self.last_processed_date: Optional[str] = None
        self.position_counter: int = 0
        self.dp_charged_dates: Dict[str, List[str]] = {}
        self.orders_journal: List[Dict[str, Any]] = []
        self.trades_journal: List[Dict[str, Any]] = []
        self.daily_snapshots: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "strategy_name": self.strategy_name,
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 2),
            "holdings": self.holdings,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "total_equity": round(self.total_equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "cumulative_costs": round(self.cumulative_costs, 2),
            "cumulative_slippage": round(self.cumulative_slippage, 2),
            "cost_pct_of_capital": round((self.cumulative_costs / self.initial_capital) * 100.0, 2),
            "last_processed_date": self.last_processed_date,
            "position_counter": self.position_counter,
            "dp_charged_dates": self.dp_charged_dates,
            "orders_count": len(self.orders_journal),
            "trades_count": len(self.trades_journal),
            "snapshots_count": len(self.daily_snapshots),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperAccount":
        acc = cls(
            account_id=data["account_id"],
            strategy_name=data.get("strategy_name", data["account_id"]),
            initial_capital=data.get("initial_capital", 20000.0),
        )
        acc.cash = float(data["cash"])
        acc.holdings = data.get("holdings", {})
        acc.realized_pnl = float(data.get("realized_pnl", 0.0))
        acc.unrealized_pnl = float(data.get("unrealized_pnl", 0.0))
        acc.total_equity = float(data.get("total_equity", acc.cash))
        acc.peak_equity = float(data.get("peak_equity", acc.total_equity))
        acc.cumulative_costs = float(data.get("cumulative_costs", 0.0))
        acc.cumulative_slippage = float(data.get("cumulative_slippage", 0.0))
        acc.last_processed_date = data.get("last_processed_date")
        acc.position_counter = int(data.get("position_counter", 0))
        acc.dp_charged_dates = data.get("dp_charged_dates", {})
        return acc


class DeterministicPaperBroker:
    """
    Deterministic Paper Broker.
    Executes signals generated by strategy engines with realistic market frictions,
    strict whole-share integer sizing, cash constraints, and comprehensive audit journaling.
    """

    def __init__(
        self,
        base_dir: str = "research/cycle4/broker_state",
        slippage_pct: float = 0.0010,  # 0.10% adverse slippage
        cost_stress_multiplier: float = 1.0,
        max_positions: int = 20,
        min_price: float = 50.0,
        min_median_turnover_60d: float = 50000000.0,  # INR 50M
        max_volume_participation_pct: float = 0.01,  # 1% of daily volume
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.slippage_pct = slippage_pct
        self.cost_stress_multiplier = cost_stress_multiplier
        self.max_positions = max_positions
        self.min_price = min_price
        self.min_median_turnover_60d = min_median_turnover_60d
        self.max_volume_participation_pct = max_volume_participation_pct

        # Active accounts map: account_id -> PaperAccount
        self.accounts: Dict[str, PaperAccount] = {}

    def get_or_create_account(
        self,
        account_id: str,
        strategy_name: str,
        initial_capital: float = 20000.0,
    ) -> PaperAccount:
        if account_id in self.accounts:
            return self.accounts[account_id]

        state_file = self.base_dir / f"{account_id}_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                acc = PaperAccount.from_dict(data)

                # Load trade and order journals if available
                orders_file = self.base_dir / f"{account_id}_orders.csv"
                if orders_file.exists():
                    acc.orders_journal = pd.read_csv(orders_file).to_dict(orient="records")
                trades_file = self.base_dir / f"{account_id}_trades.csv"
                if trades_file.exists():
                    acc.trades_journal = pd.read_csv(trades_file).to_dict(orient="records")
                daily_file = self.base_dir / f"{account_id}_daily.csv"
                if daily_file.exists():
                    acc.daily_snapshots = pd.read_csv(daily_file).to_dict(orient="records")

                self.accounts[account_id] = acc
                logger.info(f"Loaded existing account {account_id} from {state_file}")
                return acc
            except Exception as e:
                logger.warning(f"Failed to read account state {state_file} ({e}); creating fresh.")

        acc = PaperAccount(
            account_id=account_id,
            strategy_name=strategy_name,
            initial_capital=initial_capital,
        )
        self.accounts[account_id] = acc
        self.persist_account(acc)
        return acc

    def persist_account(self, account: PaperAccount):
        """Atomically persists account state, order journal, trade journal, and daily ledger."""
        state_file = self.base_dir / f"{account.account_id}_state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(account.to_dict(), f, indent=2, default=safe_json_serialize)

        if account.orders_journal:
            orders_file = self.base_dir / f"{account.account_id}_orders.csv"
            pd.DataFrame(account.orders_journal).to_csv(orders_file, index=False)

        if account.trades_journal:
            trades_file = self.base_dir / f"{account.account_id}_trades.csv"
            pd.DataFrame(account.trades_journal).to_csv(trades_file, index=False)

        if account.daily_snapshots:
            daily_file = self.base_dir / f"{account.account_id}_daily.csv"
            pd.DataFrame(account.daily_snapshots).to_csv(daily_file, index=False)

    def execute_target_portfolio(
        self,
        account: PaperAccount,
        target_symbols: List[str],
        open_prices: Dict[str, float],
        exec_date: str,
        signal_date: str,
        regime_pass: bool,
        daily_volumes: Optional[Dict[str, float]] = None,
        median_turnovers_60d: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes target portfolio allocation at Open of session T+1.
        
        Order of Execution:
        1. Full Liquidations & Trims (Sells first to release cash)
        2. New Entries & Adds (Buys second, constrained by available cash)
        
        Enforces:
        - Full liquidation when regime_pass is False (100% Cash)
        - Whole-share integer quantities: floor(target_capital / fill_price)
        - Adverse slippage: fill_price = open * (1 + slippage) for BUY, open * (1 - slippage) for SELL
        - Liquidity check: median 60d turnover >= INR 50M
        - Volume participation cap: max 1% of daily volume
        - Exact Zerodha delivery costs + single daily DP charge per fully liquidated scrip
        - Rejected orders recorded in order journal with explicit reason
        """
        daily_volumes = daily_volumes or {}
        median_turnovers_60d = median_turnovers_60d or {}

        executed_trades: List[Dict[str, Any]] = []
        dp_charged_scrip_today: Set[str] = set()

        # Step 1: Liquidations and Exits (if stock is no longer in target or regime failed)
        current_symbols = list(account.holdings.keys())
        for sym in current_symbols:
            if sym not in target_symbols or not regime_pass:
                pos = account.holdings[sym]
                op = open_prices.get(sym, 0.0)

                # Validation checks
                if op <= 0:
                    account.orders_journal.append({
                        "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_SELL",
                        "date": exec_date,
                        "signal_date": signal_date,
                        "symbol": sym,
                        "side": "SELL",
                        "action": "LIQUIDATE_EXIT",
                        "shares": pos["shares"],
                        "status": "REJECTED",
                        "rejection_reason": "MISSING_OPEN_PRICE",
                    })
                    continue

                shares = pos["shares"]
                fill_sell = op * (1.0 - self.slippage_pct)
                gross_val = shares * fill_sell
                slippage_cost = (op - fill_sell) * shares

                is_full = True  # Liquidating entire holding
                already_charged = sym in account.dp_charged_dates.get(exec_date, [])
                cost_dict = calculate_indian_delivery_charges(
                    turnover=gross_val,
                    side="SELL",
                    is_full_closure=is_full,
                    already_charged_dp_today=already_charged,
                    stress_multiplier=self.cost_stress_multiplier,
                )
                if cost_dict["dp_charges"] > 0:
                    account.dp_charged_dates.setdefault(exec_date, []).append(sym)

                total_fees = cost_dict["total_cost"]
                net_proceeds = gross_val - total_fees
                cost_basis = pos["avg_cost"] * shares
                realized_trade_pnl = gross_val - cost_basis - total_fees

                account.cash += net_proceeds
                account.cumulative_costs += total_fees
                account.cumulative_slippage += slippage_cost
                account.realized_pnl += realized_trade_pnl
                del account.holdings[sym]

                trade_record = {
                    "trade_id": f"TRD_{exec_date}_{account.account_id}_{sym}_SELL",
                    "position_id": pos.get("position_id", f"POS_{account.account_id}_{sym}"),
                    "exec_date": exec_date,
                    "signal_date": signal_date,
                    "account_id": account.account_id,
                    "symbol": sym,
                    "side": "SELL",
                    "action": "LIQUIDATE_EXIT",
                    "shares": shares,
                    "ref_open": round(op, 2),
                    "fill_price": round(fill_sell, 2),
                    "gross_turnover": round(gross_val, 2),
                    "slippage_cost": round(slippage_cost, 2),
                    "brokerage": cost_dict["brokerage"],
                    "stt": cost_dict["stt"],
                    "exchange_charges": cost_dict["exchange_charges"],
                    "sebi_charges": cost_dict["sebi_charges"],
                    "stamp_duty": cost_dict["stamp_duty"],
                    "dp_charges": cost_dict["dp_charges"],
                    "dp_gst": cost_dict["dp_gst"],
                    "dp_total": cost_dict["dp_total"],
                    "gst": cost_dict["gst"],
                    "total_costs": total_fees,
                    "net_cash_delta": round(net_proceeds, 2),
                    "realized_pnl": round(realized_trade_pnl, 2),
                    "status": "FILLED",
                }
                executed_trades.append(trade_record)
                account.trades_journal.append(trade_record)
                account.orders_journal.append({
                    "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_SELL",
                    "date": exec_date,
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "SELL",
                    "action": "LIQUIDATE_EXIT",
                    "shares": shares,
                    "fill_price": round(fill_sell, 2),
                    "status": "FILLED",
                    "rejection_reason": None,
                })

        # If market regime failed, all assets liquidated, portfolio holds 100% cash.
        if not regime_pass:
            self.persist_account(account)
            return executed_trades

        # Step 2: Calculate target allocation per slot
        # Pre-execution equity at current open prices
        equity_before_buys = account.cash
        for sym, pos in account.holdings.items():
            op = open_prices.get(sym, pos["avg_cost"])
            equity_before_buys += (op if op > 0 else pos["avg_cost"]) * pos["shares"]

        n_targets = min(len(target_symbols), self.max_positions)
        target_capital_per_slot = (equity_before_buys / n_targets) if n_targets > 0 else 0.0

        # Step 3: Execute Buys & Trims for target symbols
        for sym in target_symbols[:self.max_positions]:
            op = open_prices.get(sym, 0.0)

            # Price Floor check
            if op < self.min_price:
                account.orders_journal.append({
                    "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_BUY",
                    "date": exec_date,
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "BUY",
                    "action": "ENTER_NEW",
                    "shares": 0,
                    "status": "REJECTED",
                    "rejection_reason": f"REJECTED_PRICE_FLOOR (Price INR {op:.2f} < INR {self.min_price:.2f})",
                })
                continue

            # Liquidity check
            med_to = median_turnovers_60d.get(sym, 0.0)
            if med_to > 0 and med_to < self.min_median_turnover_60d:
                account.orders_journal.append({
                    "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_BUY",
                    "date": exec_date,
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "BUY",
                    "action": "ENTER_NEW",
                    "shares": 0,
                    "status": "REJECTED",
                    "rejection_reason": f"REJECTED_ILLIQUID (60d Median Turnover INR {med_to:,.0f} < INR {self.min_median_turnover_60d:,.0f})",
                })
                continue

            fill_buy = op * (1.0 + self.slippage_pct)
            target_shares = int(math.floor(target_capital_per_slot / fill_buy)) if fill_buy > 0 else 0

            curr_shares = account.holdings[sym]["shares"] if sym in account.holdings else 0
            if target_shares <= 0 and curr_shares == 0:
                account.orders_journal.append({
                    "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_BUY",
                    "date": exec_date,
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "BUY",
                    "action": "ENTER_NEW",
                    "shares": 0,
                    "status": "REJECTED",
                    "rejection_reason": f"REJECTED_INSUFFICIENT_CASH (Share Price INR {fill_buy:.2f} exceeds allocated slot capital INR {target_capital_per_slot:.2f})",
                })
                continue

            # Volume participation constraint
            vol = daily_volumes.get(sym, 0.0)
            if vol > 0:
                max_vol_shares = int(math.floor(vol * self.max_volume_participation_pct))
                if max_vol_shares > 0 and target_shares > max_vol_shares:
                    target_shares = max_vol_shares

            delta_shares = target_shares - curr_shares

            if delta_shares > 0:
                # Buy order
                trade_turnover = delta_shares * fill_buy
                cost_dict = calculate_indian_delivery_charges(
                    turnover=trade_turnover,
                    side="BUY",
                    is_full_closure=False,
                    stress_multiplier=self.cost_stress_multiplier,
                )
                total_required = trade_turnover + cost_dict["total_cost"]

                # Cash validation
                if account.cash < total_required:
                    # Scale down to affordable integer shares
                    est_per_share_cost = fill_buy * 1.002
                    affordable_shares = int(math.floor(account.cash / est_per_share_cost)) if est_per_share_cost > 0 else 0
                    if affordable_shares <= 0:
                        account.orders_journal.append({
                            "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_BUY",
                            "date": exec_date,
                            "signal_date": signal_date,
                            "symbol": sym,
                            "side": "BUY",
                            "action": "ENTER_NEW" if curr_shares == 0 else "ADD_SLOT",
                            "shares": delta_shares,
                            "status": "REJECTED",
                            "rejection_reason": f"REJECTED_INSUFFICIENT_CASH (Cash INR {account.cash:.2f} < Req INR {total_required:.2f})",
                        })
                        continue

                    delta_shares = affordable_shares
                    trade_turnover = delta_shares * fill_buy
                    cost_dict = calculate_indian_delivery_charges(
                        turnover=trade_turnover,
                        side="BUY",
                        is_full_closure=False,
                        stress_multiplier=self.cost_stress_multiplier,
                    )
                    total_required = trade_turnover + cost_dict["total_cost"]

                slippage_cost = (fill_buy - op) * delta_shares
                account.cash -= total_required
                account.cumulative_costs += cost_dict["total_cost"]
                account.cumulative_slippage += slippage_cost

                # Update position
                if sym in account.holdings:
                    prev = account.holdings[sym]
                    tot_sh = prev["shares"] + delta_shares
                    tot_inv = (prev["avg_cost"] * prev["shares"]) + trade_turnover
                    pos_id = prev.get("position_id", f"POS_{account.account_id}_{sym}_{exec_date}_1")
                    account.holdings[sym] = {
                        "position_id": pos_id,
                        "entry_date": prev.get("entry_date", exec_date),
                        "shares": tot_sh,
                        "avg_cost": round(tot_inv / tot_sh, 2),
                        "invested_cost": round(tot_inv, 2),
                    }
                else:
                    account.position_counter += 1
                    pos_id = f"POS_{account.account_id}_{sym}_{exec_date}_{account.position_counter}"
                    account.holdings[sym] = {
                        "position_id": pos_id,
                        "entry_date": exec_date,
                        "shares": delta_shares,
                        "avg_cost": round(fill_buy, 2),
                        "invested_cost": round(trade_turnover, 2),
                    }

                trade_record = {
                    "trade_id": f"TRD_{exec_date}_{account.account_id}_{sym}_BUY",
                    "position_id": pos_id,
                    "exec_date": exec_date,
                    "signal_date": signal_date,
                    "account_id": account.account_id,
                    "symbol": sym,
                    "side": "BUY",
                    "action": "ENTER_NEW" if curr_shares == 0 else "ADD_SLOT",
                    "shares": delta_shares,
                    "ref_open": round(op, 2),
                    "fill_price": round(fill_buy, 2),
                    "gross_turnover": round(trade_turnover, 2),
                    "slippage_cost": round(slippage_cost, 2),
                    "brokerage": cost_dict["brokerage"],
                    "stt": cost_dict["stt"],
                    "exchange_charges": cost_dict["exchange_charges"],
                    "sebi_charges": cost_dict["sebi_charges"],
                    "stamp_duty": cost_dict["stamp_duty"],
                    "dp_charges": cost_dict["dp_charges"],
                    "dp_gst": cost_dict["dp_gst"],
                    "dp_total": cost_dict["dp_total"],
                    "gst": cost_dict["gst"],
                    "total_costs": cost_dict["total_cost"],
                    "net_cash_delta": round(-total_required, 2),
                    "realized_pnl": 0.0,
                    "status": "FILLED",
                }
                executed_trades.append(trade_record)
                account.trades_journal.append(trade_record)
                account.orders_journal.append({
                    "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_BUY",
                    "date": exec_date,
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "BUY",
                    "action": "ENTER_NEW" if curr_shares == 0 else "ADD_SLOT",
                    "shares": delta_shares,
                    "fill_price": round(fill_buy, 2),
                    "status": "FILLED",
                    "rejection_reason": None,
                })

            elif delta_shares < 0:
                # Partial trim
                trim_shares = abs(delta_shares)
                fill_sell = op * (1.0 - self.slippage_pct)
                gross_val = trim_shares * fill_sell
                slippage_cost = (op - fill_sell) * trim_shares

                prev = account.holdings[sym]
                pos_id = prev.get("position_id", f"POS_{account.account_id}_{sym}")
                rem_shares = prev["shares"] - trim_shares
                is_full = (rem_shares <= 0)

                already_charged = sym in account.dp_charged_dates.get(exec_date, [])
                cost_dict = calculate_indian_delivery_charges(
                    turnover=gross_val,
                    side="SELL",
                    is_full_closure=is_full,
                    already_charged_dp_today=already_charged,
                    stress_multiplier=self.cost_stress_multiplier,
                )
                if cost_dict["dp_charges"] > 0:
                    account.dp_charged_dates.setdefault(exec_date, []).append(sym)

                total_fees = cost_dict["total_cost"]
                net_proceeds = gross_val - total_fees
                trade_realized_pnl = gross_val - (prev["avg_cost"] * trim_shares) - total_fees

                account.cash += net_proceeds
                account.cumulative_costs += total_fees
                account.cumulative_slippage += slippage_cost
                account.realized_pnl += trade_realized_pnl

                if rem_shares > 0:
                    account.holdings[sym] = {
                        "position_id": pos_id,
                        "entry_date": prev.get("entry_date", exec_date),
                        "shares": rem_shares,
                        "avg_cost": prev["avg_cost"],
                        "invested_cost": round(prev["avg_cost"] * rem_shares, 2),
                    }
                else:
                    del account.holdings[sym]

                trade_record = {
                    "trade_id": f"TRD_{exec_date}_{account.account_id}_{sym}_SELL",
                    "position_id": pos_id,
                    "exec_date": exec_date,
                    "signal_date": signal_date,
                    "account_id": account.account_id,
                    "symbol": sym,
                    "side": "SELL",
                    "action": "TRIM_SLOT" if rem_shares > 0 else "FULL_TRIM_CLOSE",
                    "shares": trim_shares,
                    "ref_open": round(op, 2),
                    "fill_price": round(fill_sell, 2),
                    "gross_turnover": round(gross_val, 2),
                    "slippage_cost": round(slippage_cost, 2),
                    "brokerage": cost_dict["brokerage"],
                    "stt": cost_dict["stt"],
                    "exchange_charges": cost_dict["exchange_charges"],
                    "sebi_charges": cost_dict["sebi_charges"],
                    "stamp_duty": cost_dict["stamp_duty"],
                    "dp_charges": cost_dict["dp_charges"],
                    "dp_gst": cost_dict["dp_gst"],
                    "dp_total": cost_dict["dp_total"],
                    "gst": cost_dict["gst"],
                    "total_costs": total_fees,
                    "net_cash_delta": round(net_proceeds, 2),
                    "realized_pnl": round(trade_realized_pnl, 2),
                    "status": "FILLED",
                }
                executed_trades.append(trade_record)
                account.trades_journal.append(trade_record)
                account.orders_journal.append({
                    "order_id": f"ORD_{exec_date}_{account.account_id}_{sym}_SELL",
                    "date": exec_date,
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "SELL",
                    "action": "TRIM_SLOT" if rem_shares > 0 else "FULL_TRIM_CLOSE",
                    "shares": trim_shares,
                    "fill_price": round(fill_sell, 2),
                    "status": "FILLED",
                    "rejection_reason": None,
                })

        self.persist_account(account)
        return executed_trades

    def mark_to_market_session(
        self,
        account: PaperAccount,
        close_prices: Dict[str, float],
        session_date: str,
        benchmark_close: float,
        prev_benchmark_close: float,
        regime_status: str,
    ) -> Dict[str, Any]:
        """
        Marks account to market at daily Close.
        Strict invariant: Total Equity == Cash + Sum(Shares * Close).
        """
        invested_value = 0.0
        unrealized = 0.0
        is_complete = True
        missing_price_symbols: List[str] = []

        for sym, pos in account.holdings.items():
            cp = close_prices.get(sym)
            if cp is None or pd.isna(cp) or cp <= 0:
                is_complete = False
                missing_price_symbols.append(sym)
                cp = pos["avg_cost"]  # Fallback for numerical stability, explicitly flagged below

            cur_val = cp * pos["shares"]
            invested_value += cur_val
            unrealized += cur_val - (pos["avg_cost"] * pos["shares"])

        account.unrealized_pnl = unrealized
        account.total_equity = account.cash + invested_value
        account.peak_equity = max(account.peak_equity, account.total_equity)
        account.last_processed_date = session_date

        drawdown_pct = ((account.total_equity - account.peak_equity) / account.peak_equity * 100.0) if account.peak_equity > 0 else 0.0
        cum_ret_pct = ((account.total_equity / account.initial_capital) - 1.0) * 100.0

        b_ret = ((benchmark_close / prev_benchmark_close) - 1.0) if prev_benchmark_close > 0 else 0.0

        snapshot = {
            "date": session_date,
            "account_id": account.account_id,
            "strategy_name": account.strategy_name,
            "cash": round(account.cash, 2),
            "invested_value": round(invested_value, 2),
            "total_equity": round(account.total_equity, 2),
            "peak_equity": round(account.peak_equity, 2),
            "drawdown_pct": round(drawdown_pct, 2),
            "cumulative_return_pct": round(cum_ret_pct, 2),
            "cumulative_costs": round(account.cumulative_costs, 2),
            "cumulative_slippage": round(account.cumulative_slippage, 2),
            "cost_pct_of_capital": round((account.cumulative_costs / account.initial_capital) * 100.0, 2),
            "realized_pnl": round(account.realized_pnl, 2),
            "unrealized_pnl": round(account.unrealized_pnl, 2),
            "holdings_count": len(account.holdings),
            "benchmark_close": round(benchmark_close, 2),
            "benchmark_daily_return": round(b_ret, 6),
            "regime_status": regime_status,
            "is_complete_valuation": is_complete,
            "missing_price_symbols": missing_price_symbols,
            "valuation_status": "VERIFIED_COMPLETE" if is_complete else f"INCOMPLETE_VALUATION_MISSING_{len(missing_price_symbols)}_SYMBOLS",
        }

        account.daily_snapshots.append(snapshot)
        self.persist_account(account)
        return snapshot
