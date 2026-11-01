from typing import Optional
from pydantic import BaseModel

from app.settings import settings


class ExitEvaluation(BaseModel):
    action: str  # HOLD, TRAIL_UPDATE, SELL_PARTIAL, SELL_ALL
    new_active_stop: Optional[float] = None
    reason: str
    exit_qty_fraction: float = 0.0  # 0.5 for partial, 1.0 for full


class ExitManager:
    """Evaluates positional swing trade exit rules: stops, trailing, partial profit, trend breaks, time stops."""

    def __init__(self):
        self.cfg = settings.get_exit_config()

    def evaluate_position(
        self,
        entry_price: float,
        initial_stop: float,
        current_active_stop: float,
        current_price: float,
        highest_price_since_entry: float,
        current_atr: float,
        current_sma50: float,
        days_held: int,
        has_taken_partial: bool = False,
    ) -> ExitEvaluation:
        r0 = entry_price - initial_stop
        if r0 <= 0:
            r0 = current_atr

        # 1. Hard Stop
        if current_price <= current_active_stop:
            return ExitEvaluation(
                action="SELL_ALL",
                new_active_stop=current_active_stop,
                reason=f"Hard stop triggered: price {current_price:.2f} <= active stop {current_active_stop:.2f}",
                exit_qty_fraction=1.0,
            )

        # 2. Trend Break: daily close < SMA50
        if current_price < current_sma50:
            return ExitEvaluation(
                action="SELL_ALL",
                new_active_stop=current_active_stop,
                reason=f"Trend break: price {current_price:.2f} closed below 50 SMA ({current_sma50:.2f})",
                exit_qty_fraction=1.0,
            )

        # 3. Time Stop: held >= 15 sessions and price < entry + 0.5R
        if days_held >= self.cfg.time_stop_sessions and current_price < (entry_price + self.cfg.time_stop_min_R * r0):
            return ExitEvaluation(
                action="SELL_ALL",
                new_active_stop=current_active_stop,
                reason=f"Time stop: held {days_held} sessions without progress (> 0.5R). Capital freed.",
                exit_qty_fraction=1.0,
            )

        # 4. Partial Profit: at entry + 2R
        target2r = entry_price + self.cfg.partial_at_R * r0
        if not has_taken_partial and current_price >= target2r:
            new_stop = max(current_active_stop, entry_price)  # move to breakeven
            return ExitEvaluation(
                action="SELL_PARTIAL",
                new_active_stop=round(new_stop, 2),
                reason=f"Partial target 2R ({target2r:.2f}) reached! Sell {int(self.cfg.partial_fraction*100)}% and trail the remainder.",
                exit_qty_fraction=self.cfg.partial_fraction,
            )

        # 5. Breakeven + Chandelier Trail
        if highest_price_since_entry >= (entry_price + self.cfg.breakeven_at_R * r0):
            chandelier_stop = highest_price_since_entry - (self.cfg.trail_atr_mult * current_atr)
            new_trail_stop = max(initial_stop, entry_price, chandelier_stop)
            if new_trail_stop > current_active_stop:
                return ExitEvaluation(
                    action="TRAIL_UPDATE",
                    new_active_stop=round(new_trail_stop, 2),
                    reason=f"Trailing stop raised to {new_trail_stop:.2f} based on chandelier trail ({highest_price_since_entry:.2f} - 3*ATR)",
                    exit_qty_fraction=0.0,
                )

        return ExitEvaluation(
            action="HOLD",
            new_active_stop=current_active_stop,
            reason="Position active within normal volatility bounds",
            exit_qty_fraction=0.0,
        )


exit_manager = ExitManager()

