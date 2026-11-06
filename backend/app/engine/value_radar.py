import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import FundamentalSnapshot, Instrument, DailyBar
from app.settings import settings
from app.engine.fundamentals_engine import fundamentals_engine

logger = logging.getLogger(__name__)


class ValueRadarEngine:
    """Evaluates value opportunities across the entire scanned universe using stored
    fundamental snapshots and technical trend stabilization criteria.
    Includes transparent 'Why Zero' exclusion metrics.
    """

    def __init__(self):
        self.cfg = settings.fundamentals_config

    def evaluate_universe(
        self,
        market: str = "IN",
        candidate_symbols: Optional[List[str]] = None,
        bars_dict: Optional[Dict[str, pd.DataFrame]] = None,
        setups_dict: Optional[Dict[str, Any]] = None,
        min_tier: str = "Small",  # Large, Mid, Small
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        session = db or SessionLocal()
        try:
            # 1. Fetch universe symbols if not provided
            symbols = candidate_symbols
            instrument_map = {}
            if not symbols:
                inst_rows = session.query(Instrument).filter(Instrument.market == market, Instrument.active == True).all()
                if inst_rows:
                    symbols = [r.symbol for r in inst_rows]
                    instrument_map = {r.symbol: r for r in inst_rows}
                else:
                    # Fallback to distinct symbols in DailyBar
                    bars_syms = session.query(DailyBar.symbol).distinct().all()
                    symbols = [r[0] for r in bars_syms]

            # 2. Fetch all latest fundamental snapshots
            snapshots = fundamentals_engine.get_all_latest_snapshots(market=market, db=session)

            total_scanned = len(symbols)
            with_fundamentals = 0
            no_fundamentals = 0
            passed_tier = 0
            excluded_tier = 0
            passed_valuation = 0
            excluded_valuation = 0
            passed_quality = 0
            excluded_quality = 0
            passed_growth = 0
            excluded_growth = 0
            passed_stabilizing = 0
            excluded_stabilizing = 0

            tier_weights = {"Large": 3, "Mid": 2, "Small": 1}
            min_tier_val = tier_weights.get(min_tier, 1)

            ideas = []

            for sym in symbols:
                inst = instrument_map.get(sym)
                tier = getattr(inst, "universe_tier", "Small") if inst else "Small"
                sector = getattr(inst, "sector", "General") if inst else "General"
                curr_tier_val = tier_weights.get(tier, 1)

                # Tier check
                if curr_tier_val < min_tier_val:
                    excluded_tier += 1
                    continue
                passed_tier += 1

                # Fundamental snapshot check
                snap = snapshots.get(sym)
                if not snap:
                    no_fundamentals += 1
                    continue
                with_fundamentals += 1

                lights_dict = {}
                if snap.lights_json:
                    try:
                        lights_dict = json.loads(snap.lights_json)
                    except Exception:
                        lights_dict = {}
                if not lights_dict:
                    lights_dict = fundamentals_engine.evaluate_traffic_lights(sym, {
                        "revenue_yoy": snap.revenue_yoy,
                        "profit_yoy": snap.profit_yoy,
                        "op_margin": snap.op_margin,
                        "roce": snap.roce,
                        "roe": snap.roe,
                        "debt_equity": snap.debt_equity,
                        "interest_coverage": snap.interest_coverage,
                        "pe": snap.pe,
                        "sector_median_pe": snap.sector_median_pe,
                        "promoter_holding": snap.promoter_holding,
                        "pledge_pct": snap.pledge_pct,
                    }, sector=sector, market=market)

                lights = {l.get("metric"): l for l in lights_dict.get("lights", [])}

                # 1. Valuation Criterion: GREEN or YELLOW versus sector median
                val_light = next((l for name, l in lights.items() if "Valuation:" in name), None)
                val_status = val_light.get("status") if val_light else "UNKNOWN"
                if val_status not in ("GREEN", "YELLOW"):
                    excluded_valuation += 1
                    continue
                passed_valuation += 1

                # 2. Quality Criterion: ROCE or ROE at least YELLOW
                quality_light = next((l for name, l in lights.items() if name in ("ROCE", "ROE")), None)
                quality_status = quality_light.get("status") if quality_light else "UNKNOWN"
                if quality_status not in ("GREEN", "YELLOW"):
                    excluded_quality += 1
                    continue
                passed_quality += 1

                # 3. Growth Criterion: Profit & Revenue not RED
                growth_lights = [l for name, l in lights.items() if name in ("Latest-quarter profit growth YoY", "Revenue growth YoY")]
                if any(l.get("status") == "RED" for l in growth_lights):
                    excluded_growth += 1
                    continue
                passed_growth += 1

                # 4. Technical Stabilising Condition: Above 200 SMA or valid base forming
                df = bars_dict.get(sym) if bars_dict else None
                cand = setups_dict.get(sym) if setups_dict else None

                above_200 = False
                base_forming = False

                if df is not None and len(df) >= 200 and "close" in df.columns:
                    last_close = float(df["close"].iloc[-1])
                    sma200 = float(df["close"].rolling(200).mean().iloc[-1] or 0.0)
                    above_200 = (last_close >= sma200)

                if cand is not None and getattr(cand, "trigger", 0) > 0:
                    base_forming = True

                if not (above_200 or base_forming):
                    excluded_stabilizing += 1
                    continue
                passed_stabilizing += 1

                # Cyclical business check
                cyclical_sectors = [s.lower() for s in self.cfg.get("cyclical_sectors", [])]
                is_cyclical = any(cs in sector.lower() for cs in cyclical_sectors)
                cyclical_warning = (
                    "Cyclical stock: valuation may appear artificially low at peak earnings."
                    if is_cyclical else None
                )

                stabilizing_label = "ABOVE_200_SMA" if above_200 else "VALID_BASE"

                ideas.append({
                    "symbol": sym,
                    "market": market,
                    "tag": "VALUE_RADAR",
                    "source": "VALUE_RADAR",
                    "tier": tier,
                    "sector": sector,
                    "valuation": val_light or {},
                    "quality": quality_light or {},
                    "growth": growth_lights,
                    "stabilizing": stabilizing_label,
                    "detail_url": lights_dict.get("detail_url") or f"https://www.screener.in/company/{sym}/",
                    "label": "Research idea, not a trade signal; cheap stocks can stay cheap.",
                    "warning": "Check for value traps and cyclical peak earnings. A value idea still requires the normal DecisionPipeline and Risk Validator.",
                    "is_cyclical": is_cyclical,
                    "cyclical_note": cyclical_warning,
                })

            summary = {
                "total_scanned": total_scanned,
                "with_fundamentals": with_fundamentals,
                "no_fundamentals": no_fundamentals,
                "passed_tier": passed_tier,
                "excluded_tier": excluded_tier,
                "passed_valuation": passed_valuation,
                "excluded_valuation": excluded_valuation,
                "passed_quality": passed_quality,
                "excluded_quality": excluded_quality,
                "passed_growth": passed_growth,
                "excluded_growth": excluded_growth,
                "passed_stabilizing": passed_stabilizing,
                "excluded_stabilizing": excluded_stabilizing,
                "total_ideas": len(ideas),
            }

            explanation = (
                f"{total_scanned} scanned, {with_fundamentals} with fundamentals, "
                f"{passed_valuation} cheap (val Green/Yellow), {passed_quality} quality OK, "
                f"{passed_growth} growth OK, {passed_stabilizing} stabilising. "
                f"Generated {len(ideas)} research ideas."
            )

            return {
                "market": market,
                "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "summary": summary,
                "explanation": explanation,
                "ideas": ideas,
            }
        finally:
            if db is None:
                session.close()


value_radar_engine = ValueRadarEngine()

