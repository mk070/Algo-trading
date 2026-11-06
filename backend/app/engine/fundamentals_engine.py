import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import SessionLocal
from app.models import FundamentalSnapshot, Instrument
from app.settings import settings
from app.engine.fundamentals import evaluate_fundamentals

logger = logging.getLogger(__name__)


class FundamentalsEngine:
    """Manages fundamental snapshots, multi-source ingestion (yfinance, owner CSV, manual),
    sector median benchmarks, traffic-light rules, and honest coverage tracking.
    """

    def __init__(self):
        self.cfg = settings.fundamentals_config
        self.thresholds = self.cfg.get("thresholds", {})

    def get_latest_snapshot(self, symbol: str, market: str = "IN", db: Optional[Session] = None) -> Optional[FundamentalSnapshot]:
        clean_sym = symbol.strip().upper()
        session = db or SessionLocal()
        try:
            return (
                session.query(FundamentalSnapshot)
                .filter(FundamentalSnapshot.symbol == clean_sym, FundamentalSnapshot.market == market)
                .order_by(FundamentalSnapshot.as_of.desc(), FundamentalSnapshot.id.desc())
                .first()
            )
        finally:
            if db is None:
                session.close()

    def get_all_latest_snapshots(self, market: str = "IN", db: Optional[Session] = None) -> Dict[str, FundamentalSnapshot]:
        session = db or SessionLocal()
        try:
            rows = (
                session.query(FundamentalSnapshot)
                .filter(FundamentalSnapshot.market == market)
                .order_by(FundamentalSnapshot.symbol, FundamentalSnapshot.as_of.desc())
                .all()
            )
            result = {}
            for r in rows:
                if r.symbol not in result:
                    result[r.symbol] = r
            return result
        finally:
            if db is None:
                session.close()

    def calculate_completeness(self, snap_dict: Dict[str, Any]) -> str:
        """Determines snapshot completeness:
        COMPLETE: >= 5 primary metrics available
        PARTIAL: 1 to 4 primary metrics available
        NONE: 0 metrics available
        """
        metrics = [
            snap_dict.get("revenue_yoy"),
            snap_dict.get("profit_yoy"),
            snap_dict.get("op_margin"),
            snap_dict.get("roce") or snap_dict.get("roe"),
            snap_dict.get("pe"),
            snap_dict.get("debt_equity"),
            snap_dict.get("promoter_holding"),
        ]
        non_null_count = sum(1 for m in metrics if m is not None)
        if non_null_count >= 5:
            return "COMPLETE"
        elif non_null_count >= 1:
            return "PARTIAL"
        return "NONE"

    def save_snapshot(
        self,
        symbol: str,
        data: Dict[str, Any],
        market: str = "IN",
        source: str = "yfinance",
        as_of: Optional[datetime.date] = None,
        db: Optional[Session] = None,
    ) -> FundamentalSnapshot:
        clean_sym = symbol.strip().upper()
        as_of_date = as_of or datetime.date.today()
        completeness = self.calculate_completeness(data)

        lights_result = self.evaluate_traffic_lights(clean_sym, data, market=market)
        lights_json = json.dumps(lights_result, default=str)

        session = db or SessionLocal()
        try:
            snapshot = FundamentalSnapshot(
                symbol=clean_sym,
                market=market,
                as_of=as_of_date,
                period_end=data.get("period_end"),
                source=source,
                revenue_yoy=data.get("revenue_yoy"),
                profit_yoy=data.get("profit_yoy"),
                op_margin=data.get("op_margin"),
                roce=data.get("roce"),
                roe=data.get("roe"),
                debt_equity=data.get("debt_equity"),
                interest_coverage=data.get("interest_coverage"),
                pe=data.get("pe"),
                sector_median_pe=data.get("sector_median_pe"),
                promoter_holding=data.get("promoter_holding"),
                pledge_pct=data.get("pledge_pct"),
                completeness=completeness,
                lights_json=lights_json,
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            return snapshot
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save fundamental snapshot for {clean_sym}: {e}")
            raise
        finally:
            if db is None:
                session.close()

    def evaluate_traffic_lights(
        self, symbol: str, data: Dict[str, Any], sector: str = "Unknown", market: str = "IN"
    ) -> Dict[str, Any]:
        """Translates raw snapshot fields into standard traffic light metrics via app.engine.fundamentals."""
        clean_sym = symbol.strip().upper()
        is_financial = any(x in sector.lower() for x in ("financial", "bank", "insurance"))

        # Compute PE vs sector median if both exist
        pe = data.get("pe")
        sec_pe = data.get("sector_median_pe")
        pe_ratio = None
        if pe is not None and sec_pe is not None and sec_pe > 0:
            pe_ratio = round(pe / sec_pe, 2)

        raw_payload = {
            "symbol": clean_sym,
            "source": data.get("source", "UNKNOWN"),
            "period": data.get("period_end", "Latest available"),
            "sector": sector,
            "profit_growth_yoy_pct": data.get("profit_yoy"),
            "revenue_growth_yoy_pct": data.get("revenue_yoy"),
            "operating_margin_change_pp": data.get("op_margin"),
            "roce_pct": data.get("roce"),
            "roe_pct": data.get("roe"),
            "debt_equity": data.get("debt_equity"),
            "interest_coverage": data.get("interest_coverage"),
            "pe_vs_sector_median": pe_ratio,
            "pb_vs_sector_median": pe_ratio if is_financial else None,
            "negative_earnings": (pe is not None and pe < 0),
            "pledge_pct": data.get("pledge_pct"),
            "promoter_holding_change_4q_pp": data.get("promoter_holding_change_4q_pp"),
            "last_two_net_profits": data.get("last_two_net_profits"),
            "last_two_profit_yoy_changes_pct": data.get("last_two_profit_yoy_changes_pct"),
        }

        result = evaluate_fundamentals(raw_payload, sector=sector, financial=is_financial)
        # Add Tijori & Screener link-out URLs
        screener_tmpl = self.cfg.get("sector_url_templates", {}).get("screener", "https://www.screener.in/company/{symbol}/")
        tijori_tmpl = self.cfg.get("sector_url_templates", {}).get("tijori", "https://www.tijorifinance.com/company/{symbol}/")
        result["screener_url"] = screener_tmpl.format(symbol=clean_sym)
        result["tijori_url"] = tijori_tmpl.format(symbol=clean_sym)
        return result

    def get_coverage_report(self, market: str = "IN", db: Optional[Session] = None) -> Dict[str, Any]:
        """Honest reporting of fundamentals coverage across the scanned universe."""
        session = db or SessionLocal()
        try:
            snapshots = self.get_all_latest_snapshots(market=market, db=session)
            # Count instruments
            inst_count = session.query(Instrument).filter(Instrument.market == market, Instrument.active == True).count()
            if inst_count == 0:
                inst_count = len(snapshots) or 1

            complete_count = sum(1 for s in snapshots.values() if s.completeness == "COMPLETE")
            partial_count = sum(1 for s in snapshots.values() if s.completeness == "PARTIAL")
            none_count = max(0, inst_count - (complete_count + partial_count))

            return {
                "market": market,
                "total_instruments": inst_count,
                "snapshots_recorded": len(snapshots),
                "complete_count": complete_count,
                "complete_pct": round((complete_count / inst_count) * 100.0, 1) if inst_count > 0 else 0.0,
                "partial_count": partial_count,
                "partial_pct": round((partial_count / inst_count) * 100.0, 1) if inst_count > 0 else 0.0,
                "none_count": none_count,
                "none_pct": round((none_count / inst_count) * 100.0, 1) if inst_count > 0 else 0.0,
                "disclosure": "Fundamentals sourced without scraping. Missing fields remain UNKNOWN.",
            }
        finally:
            if db is None:
                session.close()

    def import_owner_csv(self, csv_content: str, market: str = "IN", db: Optional[Session] = None) -> Dict[str, Any]:
        """Allows owner to import CSV export from Screener / Excel / Bloomberg.
        Required columns: symbol
        Optional columns: revenue_yoy, profit_yoy, op_margin, roce, roe, debt_equity, interest_coverage, pe, sector_median_pe, promoter_holding, pledge_pct
        """
        import io, csv
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        imported = 0
        session = db or SessionLocal()
        try:
            for row in reader:
                sym = (row.get("symbol") or row.get("Symbol") or "").strip().upper()
                if not sym:
                    continue
                def parse_f(k):
                    v = row.get(k) or row.get(k.lower()) or row.get(k.capitalize())
                    if v is not None and v != "":
                        try:
                            return float(str(v).replace("%", "").replace(",", "").strip())
                        except ValueError:
                            return None
                    return None

                data = {
                    "revenue_yoy": parse_f("revenue_yoy"),
                    "profit_yoy": parse_f("profit_yoy"),
                    "op_margin": parse_f("op_margin"),
                    "roce": parse_f("roce"),
                    "roe": parse_f("roe"),
                    "debt_equity": parse_f("debt_equity"),
                    "interest_coverage": parse_f("interest_coverage"),
                    "pe": parse_f("pe"),
                    "sector_median_pe": parse_f("sector_median_pe"),
                    "promoter_holding": parse_f("promoter_holding"),
                    "pledge_pct": parse_f("pledge_pct"),
                    "period_end": row.get("period_end") or row.get("Quarter") or "Imported CSV",
                }
                self.save_snapshot(sym, data, market=market, source="Owner CSV Export", db=session)
                imported += 1
            return {"status": "SUCCESS", "rows_imported": imported}
        finally:
            if db is None:
                session.close()


fundamentals_engine = FundamentalsEngine()

