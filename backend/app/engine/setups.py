import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.settings import settings

logger = logging.getLogger(__name__)


def is_broke_out_today(signal_high: float, signal_close: float, prior_pivot: float, enabled: bool) -> bool:
    """Classify a confirmed signal-day close above a prior, signal-excluded pivot."""
    return bool(enabled and signal_high > prior_pivot and signal_close >= prior_pivot)


class SetupCandidate(BaseModel):
    symbol: str
    setup: str  # VCP or PULLBACK
    pivot: float
    trigger: float
    entry_zone_high: float
    stop: float
    target1: float
    risk_per_share: float
    risk_r: float
    atr: float
    reasons: List[str]
    is_experimental: bool = False
    shadow_mode: bool = False
    classification: str = "PRE_BREAKOUT"  # PRE_BREAKOUT | BROKE_OUT_TODAY


class SetupEngine:
    """Detects Setup V (VCP / Tight-Base Breakout) and Setup P (Pullback to 20/50 EMA)."""

    def __init__(self):
        self.vcp_cfg = settings.get_vcp_config()
        self.pullback_cfg = settings.get_pullback_config()

    def round_to_tick(self, val: float, tick: float = 0.05) -> float:
        return round(round(val / tick) * tick, 2)

    def evaluate_vcp_breakout(
        self, symbol: str, df: pd.DataFrame, tick: float = 0.05
    ) -> Optional[SetupCandidate]:
        """Evaluates Setup V: Objective tight-base VCP breakout rules."""
        if df is None or len(df) < self.vcp_cfg.base_max_bars + 15:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]
        atr_series = df["atr14"]
        sma50_series = df["sma50"]

        last_idx = len(df) - 1
        last_close = float(close.iloc[-1])
        last_atr = float(atr_series.iloc[-1])
        if last_atr <= 0:
            return None

        # Search for best fitting base window N in [base_min_bars, base_max_bars]
        best_candidate = None

        for n in range(self.vcp_cfg.base_min_bars, self.vcp_cfg.base_max_bars + 1):
            # The compatibility flag deliberately changes only the experimental
            # classification path.  It avoids treating today's new high as the
            # base pivot, which otherwise makes a completed breakout appear new.
            if self.vcp_cfg.pivot_excludes_signal_day:
                if len(df) < n + 1:
                    continue
                base_slice = df.iloc[-n - 1:-1]
            else:
                base_slice = df.iloc[-n:]
            pivot = float(base_slice["high"].max())
            base_low = float(base_slice["low"].min())

            # 1. Base Depth <= max_base_depth_pct (20%)
            depth_pct = (pivot - base_low) / pivot * 100.0
            if depth_pct > self.vcp_cfg.max_base_depth_pct:
                continue

            # 2. Support: no daily close below SMA50 inside the base
            if (base_slice["close"] < base_slice["sma50"]).any():
                continue

            # 3. Tightness: last 5 bars high-low range <= tight_5d_pct (5%) of close
            last5 = df.iloc[-5:]
            range_5d = (last5["high"].max() - last5["low"].min()) / last_close * 100.0
            if range_5d > self.vcp_cfg.tight_5d_pct:
                continue

            # 4. Proximity: close within pivot_proximity_pct (3%) below pivot
            broke_out_today = is_broke_out_today(float(high.iloc[-1]), last_close, pivot, self.vcp_cfg.pivot_excludes_signal_day)
            if last_close > pivot:
                dist_pct = (last_close - pivot) / pivot * 100.0
                if dist_pct > 1.5 and not broke_out_today:  # already broke out too far
                    continue
            else:
                dist_below = (pivot - last_close) / pivot * 100.0
                if dist_below > self.vcp_cfg.pivot_proximity_pct:
                    continue

            # 5. Volatility contraction (if require_contraction is True)
            if self.vcp_cfg.require_contraction:
                # ATR contraction vs 25 bars ago
                if len(df) >= 26 and pd.notna(atr_series.iloc[-26]):
                    prev_atr = float(atr_series.iloc[-26])
                    if prev_atr > 0 and (last_atr / prev_atr) > self.vcp_cfg.atr_contraction_ratio:
                        continue
                # 3-part base range contraction: last 3rd range <= 0.7x 1st 3rd range
                third = n // 3
                if third >= 3:
                    range_first = base_slice["high"].iloc[:third].max() - base_slice["low"].iloc[:third].min()
                    range_last = base_slice["high"].iloc[-third:].max() - base_slice["low"].iloc[-third:].min()
                    if range_first > 0 and (range_last / range_first) > 0.70:
                        continue

            # 6. Volume dry-up: mean volume of last 10 bars <= 0.9 * avg_vol50
            avg_vol50 = float(df["avg_vol50"].iloc[-1])
            vol_last10 = float(vol.iloc[-10:].mean())
            if avg_vol50 > 0 and vol_last10 > (self.vcp_cfg.volume_dryup_ratio * avg_vol50):
                continue

            # Calculate Trigger, Stop, and Targets
            trigger = self.round_to_tick(pivot + self.vcp_cfg.trigger_atr_buffer * last_atr, tick)
            entry_zone_high = self.round_to_tick(
                min(trigger + self.vcp_cfg.entry_zone_atr * last_atr, trigger * 1.02), tick
            )

            # Structural Stop: lowest low of last 10 bars - 0.2*ATR14
            lowest_10 = float(df["low"].iloc[-self.vcp_cfg.stop_bars :].min())
            stop = self.round_to_tick(lowest_10 - self.vcp_cfg.stop_atr_buffer * last_atr, tick)

            risk_per_share = trigger - stop
            if risk_per_share <= 0:
                continue

            # Constraints: 1.0*ATR <= risk <= 2.5*ATR, and stop <= 8% of trigger
            if risk_per_share < (self.vcp_cfg.min_risk_atr * last_atr):
                continue
            if risk_per_share > (self.vcp_cfg.max_risk_atr * last_atr):
                continue
            if (risk_per_share / trigger * 100.0) > self.vcp_cfg.max_stop_pct:
                continue

            # Target 1 = trigger + 2R
            target1 = self.round_to_tick(trigger + 2.0 * risk_per_share, tick)

            reasons = [
                f"Tight base consolidation of {n} sessions with depth {depth_pct:.1f}%",
                f"Volatility contraction: 5-day price range tightened to {range_5d:.1f}%",
                f"Volume dry-up: 10-day volume is {(vol_last10/avg_vol50)*100:.0f}% of 50-day average",
                f"Support confirmed above 50 SMA with pivot at {pivot:.2f}",
                f"Calculated 2R target at {target1:.2f} with structural invalidation at {stop:.2f}",
            ]

            best_candidate = SetupCandidate(
                symbol=symbol,
                setup="VCP",
                pivot=pivot,
                trigger=trigger,
                entry_zone_high=entry_zone_high,
                stop=stop,
                target1=target1,
                risk_per_share=risk_per_share,
                risk_r=risk_per_share,
                atr=last_atr,
                reasons=reasons,
                is_experimental=False,
                shadow_mode=False,
                classification="BROKE_OUT_TODAY" if broke_out_today else "PRE_BREAKOUT",
            )
            break  # found tightest valid base window

        return best_candidate

    def evaluate_pullback(
        self, symbol: str, df: pd.DataFrame, tick: float = 0.05
    ) -> Optional[SetupCandidate]:
        """Evaluates Setup P: Pullback to 20/50 EMA in uptrend (Experimental, shadow mode)."""
        if df is None or len(df) < 55:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        ema20 = df["ema20"]
        sma50 = df["sma50"]
        rsi14 = df["rsi14"]
        atr14 = df["atr14"]
        high55 = df["high55"]

        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_atr = float(atr14.iloc[-1])
        if last_atr <= 0:
            return None

        # 1. Within last 5 bars: low <= EMA20 * 1.01
        last5_low = low.iloc[-5:]
        last5_ema20 = ema20.iloc[-5:]
        touched_ema20 = (last5_low <= (last5_ema20 * self.pullback_cfg.touch_tolerance)).any()
        if not touched_ema20:
            return None

        # 2. min(RSI14 over last 5 bars) < 45
        min_rsi5 = float(rsi14.iloc[-5:].min())
        if min_rsi5 >= self.pullback_cfg.rsi_dip_below:
            return None

        # 3. Turning up: RSI14[t] > RSI14[t-1] and close[t] > close[t-1]
        if not (rsi14.iloc[-1] > rsi14.iloc[-2] and close.iloc[-1] > close.iloc[-2]):
            return None

        # 4. close > SMA50 and close < 0.97 * high55 (real pullback)
        h55 = float(high55.iloc[-1])
        if not (last_close > sma50.iloc[-1] and last_close < (0.97 * h55)):
            return None

        # Trigger (buy-stop): high[t] + 0.1 * ATR14
        trigger = self.round_to_tick(last_high + self.pullback_cfg.trigger_atr_buffer * last_atr, tick)
        entry_zone_high = self.round_to_tick(trigger + 0.5 * last_atr, tick)

        # Initial stop: min(lowest low last 7 bars - 0.2*ATR, trigger - 1.0*ATR)
        swing_low_7 = float(low.iloc[-self.pullback_cfg.swing_low_bars :].min())
        stop1 = swing_low_7 - self.pullback_cfg.stop_atr_buffer * last_atr
        stop2 = trigger - self.pullback_cfg.min_risk_atr * last_atr
        stop = self.round_to_tick(min(stop1, stop2), tick)

        # Never wider than trigger - 3.0*ATR
        max_stop_boundary = trigger - self.pullback_cfg.max_risk_atr * last_atr
        if stop < max_stop_boundary:
            stop = self.round_to_tick(max_stop_boundary, tick)

        risk_per_share = trigger - stop
        if risk_per_share <= 0:
            return None

        target1 = self.round_to_tick(trigger + 2.0 * risk_per_share, tick)

        reasons = [
            f"Pullback tested the 20-day EMA support zone within the last 5 sessions",
            f"RSI(14) dipped to {min_rsi5:.1f} and turned back up with bullish candle reversal",
            f"Holding comfortably above rising 50 SMA with healthy pullback from 55-day high",
            f"Provisional trigger at {trigger:.2f} with 2R target at {target1:.2f}",
        ]

        return SetupCandidate(
            symbol=symbol,
            setup="PULLBACK",
            pivot=last_high,
            trigger=trigger,
            entry_zone_high=entry_zone_high,
            stop=stop,
            target1=target1,
            risk_per_share=risk_per_share,
            risk_r=risk_per_share,
            atr=last_atr,
            reasons=reasons,
            is_experimental=True,
            shadow_mode=self.pullback_cfg.shadow_mode,
        )


setup_engine = SetupEngine()

