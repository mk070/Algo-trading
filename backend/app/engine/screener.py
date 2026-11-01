from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel

from app.settings import settings


class ChecklistItem(BaseModel):
    rule: str
    passed: bool
    actual_value: str
    expected_value: str


class TrendTemplateResult(BaseModel):
    symbol: str
    passed: bool
    checklist: List[ChecklistItem]
    rs_score: float
    rs_rank: float
    is_extended: bool
    extension_reason: Optional[str] = None


class ScreenerEngine:
    """Evaluates Minervini-inspired Trend Template rules, RS percentile ranking, and overextension."""

    def __init__(self):
        self.tt_cfg = settings.get_trend_template_config()
        self.screen_cfg = settings.strategy_config.get("screen", {})

    def evaluate_trend_template(
        self,
        symbol: str,
        df: pd.DataFrame,
        rs_rank: float = 0.75,
        index_ret126: float = 0.0,
    ) -> TrendTemplateResult:
        checklist: List[ChecklistItem] = []

        if df is None or len(df) < 50:
            return TrendTemplateResult(
                symbol=symbol,
                passed=False,
                checklist=[
                    ChecklistItem(
                        rule="History Length",
                        passed=False,
                        actual_value=f"{len(df) if df is not None else 0} bars",
                        expected_value=">= 50 bars",
                    )
                ],
                rs_score=0.0,
                rs_rank=rs_rank,
                is_extended=False,
            )

        row = df.iloc[-1]
        close = float(row["close"])
        sma50 = float(row.get("sma50", close))
        sma150 = float(row.get("sma150", close))
        sma200 = float(row.get("sma200", close))
        ema20 = float(row.get("ema20", close))
        ema50 = float(row.get("ema50", close))
        high252 = float(row.get("high252", close))
        low252 = float(row.get("low252", close * 0.7))
        ret21 = float(row.get("ret21", 0.0))
        ret63 = float(row.get("ret63", 0.0))
        ret126 = float(row.get("ret126", 0.0))

        # Check SMA200 rising over 21 bars
        sma200_rising = True
        if len(df) > 21 and "sma200" in df.columns:
            sma200_prev = df["sma200"].iloc[-21]
            if pd.notna(sma200_prev) and pd.notna(sma200):
                sma200_rising = sma200 > float(sma200_prev)

        # 1. close > SMA150 and close > SMA200
        r1 = close > sma150 and close > sma200
        checklist.append(
            ChecklistItem(
                rule="Price > SMA150 & SMA200",
                passed=bool(r1),
                actual_value=f"{close:.2f}",
                expected_value=f"> {sma150:.2f} & {sma200:.2f}",
            )
        )

        # 2. SMA150 > SMA200
        r2 = sma150 > sma200
        checklist.append(
            ChecklistItem(
                rule="SMA150 > SMA200",
                passed=bool(r2),
                actual_value=f"{sma150:.2f}",
                expected_value=f"> {sma200:.2f}",
            )
        )

        # 3. SMA200 rising: SMA200[t] > SMA200[t-21]
        checklist.append(
            ChecklistItem(
                rule="SMA200 Rising (21 bars)",
                passed=bool(sma200_rising),
                actual_value="Rising" if sma200_rising else "Falling",
                expected_value="Rising",
            )
        )

        # 4. SMA50 > SMA150 and SMA50 > SMA200
        r4 = sma50 > sma150 and sma50 > sma200
        checklist.append(
            ChecklistItem(
                rule="SMA50 > SMA150 & SMA200",
                passed=bool(r4),
                actual_value=f"{sma50:.2f}",
                expected_value=f"> {sma150:.2f} & {sma200:.2f}",
            )
        )

        # 5. close > SMA50 and EMA20 > EMA50
        r5 = close > sma50 and ema20 > ema50
        checklist.append(
            ChecklistItem(
                rule="Price > SMA50 & EMA20 > EMA50",
                passed=bool(r5),
                actual_value=f"Close: {close:.2f}, EMA20: {ema20:.2f}",
                expected_value=f"> SMA50: {sma50:.2f}, > EMA50: {ema50:.2f}",
            )
        )

        # 6. close >= 1.30 * low252
        min_low_thresh = self.tt_cfg.min_above_52w_low * low252
        r6 = close >= min_low_thresh
        checklist.append(
            ChecklistItem(
                rule="Price >= 30% Above 52w Low",
                passed=bool(r6),
                actual_value=f"{close:.2f} (+{(close/low252 - 1)*100:.1f}%)",
                expected_value=f">= {min_low_thresh:.2f}",
            )
        )

        # 7. close >= 0.75 * high252 (within 25% of 52w high)
        max_high_thresh = (1.0 - self.tt_cfg.max_below_52w_high) * high252
        r7 = close >= max_high_thresh
        checklist.append(
            ChecklistItem(
                rule="Price Within 25% of 52w High",
                passed=bool(r7),
                actual_value=f"{close:.2f} ({(1 - close/high252)*100:.1f}% below)",
                expected_value=f">= {max_high_thresh:.2f}",
            )
        )

        # 8. Relative strength: rs_rank >= 0.70 and ret126 > index_ret126
        min_rs_rank = float(self.screen_cfg.get("rs_min_rank", 0.70))
        r8 = (rs_rank >= min_rs_rank) and (ret126 >= index_ret126)
        checklist.append(
            ChecklistItem(
                rule=f"Relative Strength Rank >= {min_rs_rank:.2f} & Outperforming Index",
                passed=bool(r8),
                actual_value=f"RS Rank: {rs_rank:.2f}, Ret126: {ret126*100:.1f}%",
                expected_value=f">= {min_rs_rank:.2f} & >= Index {index_ret126*100:.1f}%",
            )
        )

        # Overextension Guard
        is_extended = False
        ext_reason = None
        if close > (self.tt_cfg.max_above_sma50 * sma50):
            is_extended = True
            ext_reason = f"Price {close:.2f} is > 25% above SMA50 ({sma50:.2f})"
        elif ret21 > self.tt_cfg.extension_ret21_max:
            is_extended = True
            ext_reason = f"1-month return ({ret21*100:.1f}%) exceeds max extension ({self.tt_cfg.extension_ret21_max*100:.0f}%)"

        checklist.append(
            ChecklistItem(
                rule="Not Overextended",
                passed=not is_extended,
                actual_value=ext_reason if is_extended else "Normal extension",
                expected_value="Close <= 1.25*SMA50 & ret21 <= 30%",
            )
        )

        all_rules_passed = all(item.passed for item in checklist)
        rs_score = 0.5 * ret63 + 0.5 * ret126

        return TrendTemplateResult(
            symbol=symbol,
            passed=all_rules_passed,
            checklist=checklist,
            rs_score=rs_score,
            rs_rank=rs_rank,
            is_extended=is_extended,
            extension_reason=ext_reason,
        )

    def calculate_universe_rs_ranks(
        self, data_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, float]:
        """Calculates RS percentile ranks across all universe stocks."""
        scores: Dict[str, float] = {}
        for sym, df in data_dict.items():
            if df is not None and len(df) >= 126:
                ret63 = float(df["close"].pct_change(63).iloc[-1])
                ret126 = float(df["close"].pct_change(126).iloc[-1])
                if pd.notna(ret63) and pd.notna(ret126):
                    scores[sym] = 0.5 * ret63 + 0.5 * ret126
                else:
                    scores[sym] = 0.0
            else:
                scores[sym] = 0.0

        if not scores:
            return {}

        sorted_syms = sorted(scores.keys(), key=lambda s: scores[s])
        n = len(sorted_syms)
        ranks: Dict[str, float] = {}
        for idx, sym in enumerate(sorted_syms):
            ranks[sym] = (idx + 1) / n  # percentile rank between 0.0 and 1.0

        return ranks


screener_engine = ScreenerEngine()

