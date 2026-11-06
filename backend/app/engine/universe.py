import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.settings import settings, DATA_DIR
from app.models import Instrument, DailyBar

logger = logging.getLogger(__name__)


class UniverseStock(BaseModel):
    symbol: str
    name: str
    sector: str
    industry: str
    market: str
    tier: str = "Small"          # Large, Mid, Small
    series: str = "EQ"           # EQ, BE, SM, ST, etc.
    is_higher_risk: bool = False # Small/illiquid tier flagged higher risk
    provider_token: Optional[str] = None
    status: str = "SCANNED"      # SCANNED | NO_DATA | INSUFFICIENT_HISTORY (<252 bars) | ILLIQUID | PRICE_FLOOR | VOLATILITY_CAP | SERIES_EXCLUDED | DATA_ERROR


class UniverseFilterResult(BaseModel):
    symbol: str
    passed: bool
    rejection_reasons: List[str]
    status: str                  # Exactly one of the primary status codes
    last_price: float
    avg_turnover: float
    atr_pct: float
    is_affordable: bool
    tier: str = "Small"
    is_higher_risk: bool = False


class UniverseManager:
    """Manages full liquid equity universe coverage, compliant master list building
    from Angel One OpenAPI instrument master, series filtering, tiered liquidity classification,
    and transparent coverage funnel tracking.
    """

    def __init__(self):
        self.universe_dir = DATA_DIR / "universe"
        self.universe_dir.mkdir(parents=True, exist_ok=True)
        self.angelone_cache = DATA_DIR / "cache" / "angelone" / "instrument_master.json"

    def is_etf(self, symbol: str, name: str = "") -> bool:
        """Identifies Exchange Traded Funds, Index Funds, and InVITs/REITs."""
        sym_u = symbol.upper()
        name_u = name.upper()

        if any(sym_u.endswith(sfx) for sfx in ("BEES", "ETF")):
            return True
        if any(keyword in sym_u for keyword in ("GSEC", "INVIT", "REIT", "GOLD", "SILVER", "COMMODITY", "LIQUIDITY", "HEDGE")):
            return True
        if sym_u.startswith("NIFTY") and sym_u not in ("NIFTY",):
            return True
        if any(kw in name_u for kw in (" ETF", "GROWTH ETF", "BEES", "INDEX FUND", "INFRASTRUCTURE TRUST", "REAL ESTATE INVESTMENT")):
            return True
        return False

    def load_index_constituent_tags(self) -> Dict[str, str]:
        """Loads index constituent membership to tag market tiers (Large, Mid, Small)."""
        tier_map: Dict[str, str] = {}
        # 1. Nifty 100 -> Large
        n100_path = self.universe_dir / "nifty100.csv"
        if n100_path.exists():
            try:
                with open(n100_path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        sym = (row.get("symbol") or "").strip().upper()
                        if sym:
                            tier_map[sym] = "Large"
            except Exception as e:
                logger.warning(f"Error reading nifty100.csv: {e}")

        # 2. Nifty Midcap 150 -> Mid
        nmid_path = self.universe_dir / "niftymidcap150.csv"
        if nmid_path.exists():
            try:
                with open(nmid_path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        sym = (row.get("symbol") or "").strip().upper()
                        if sym and sym not in tier_map:
                            tier_map[sym] = "Mid"
            except Exception as e:
                logger.warning(f"Error reading niftymidcap150.csv: {e}")

        return tier_map

    def parse_master_scrip_list(self, market: str = "IN", bse_enabled: bool = False) -> List[Dict[str, Any]]:
        """Parses the Angel One scrip master and applies compliant series and instrument filters."""
        if market.upper() != "IN" or not self.angelone_cache.exists():
            return []

        try:
            with open(self.angelone_cache, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load Angel One scrip master: {e}")
            return []

        tier_tags = self.load_index_constituent_tags()
        parsed = []

        for clean_sym, info in data.items():
            exch = info.get("exch_seg", "NSE")
            raw_sym = info.get("raw_symbol") or f"{clean_sym}-EQ"
            name = info.get("name") or clean_sym

            # 1. Exchange filter: NSE only by default; BSE-only off unless enabled
            if exch != "NSE" and not (bse_enabled and exch == "BSE"):
                continue

            # 2. Series extraction
            series = "EQ"
            if "-" in raw_sym:
                series = raw_sym.split("-")[-1].upper()

            # 3. Check for series exclusions (-BE, -SM, -ST, etc.) or ETFs
            is_excluded_series = series not in ("EQ",)
            is_etf_item = self.is_etf(clean_sym, name)

            if is_excluded_series or is_etf_item:
                status = "SERIES_EXCLUDED"
                reason = "ETF instrument excluded" if is_etf_item else f"Series {series} excluded (-BE, -SM, -ST)"
            else:
                status = "SCANNED"
                reason = "Eligible equity series"

            tier = tier_tags.get(clean_sym, "Small")
            is_higher_risk = (tier == "Small")

            parsed.append({
                "symbol": clean_sym,
                "raw_symbol": raw_sym,
                "name": name,
                "series": series,
                "exch_seg": exch,
                "provider_token": str(info.get("token")),
                "tier": tier,
                "is_higher_risk": is_higher_risk,
                "status": status,
                "status_reason": reason,
                "sector": info.get("sector") or "General",
                "industry": info.get("industry") or "General",
            })

        return parsed

    def load_universe(self, market: str = "IN", db: Optional[Session] = None) -> List[UniverseStock]:
        """Loads all eligible liquid equities for screening."""
        stocks: List[UniverseStock] = []
        seen: Set[str] = set()

        if market.upper() == "IN":
            master_items = self.parse_master_scrip_list(market="IN")
            if master_items:
                for item in master_items:
                    if item["status"] == "SERIES_EXCLUDED":
                        continue
                    sym = item["symbol"]
                    if sym not in seen:
                        seen.add(sym)
                        stocks.append(
                            UniverseStock(
                                symbol=sym,
                                name=item["name"],
                                sector=item["sector"],
                                industry=item["industry"],
                                market="IN",
                                tier=item["tier"],
                                series=item["series"],
                                is_higher_risk=item["is_higher_risk"],
                                provider_token=item["provider_token"],
                                status="SCANNED",
                            )
                        )
                logger.info(f"Loaded {len(stocks)} liquid NSE equity candidates from Angel One master.")
                return stocks

            # Fallback to constituent CSVs if master file is unavailable
            files = ["nifty100.csv", "niftymidcap150.csv"]
        else:
            files = ["sp500.csv", "sp400.csv"]

        tier_tags = self.load_index_constituent_tags()
        for f_name in files:
            path = self.universe_dir / f_name
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for row in csv.DictReader(f):
                            sym = row.get("symbol", "").strip().upper()
                            if sym and sym not in seen:
                                seen.add(sym)
                                tier = tier_tags.get(sym, "Large" if "100" in f_name or "500" in f_name else "Mid")
                                stocks.append(
                                    UniverseStock(
                                        symbol=sym,
                                        name=row.get("name", sym),
                                        sector=row.get("sector", "General"),
                                        industry=row.get("industry", "General"),
                                        market=market.upper(),
                                        tier=tier,
                                        series="EQ",
                                        is_higher_risk=(tier == "Small"),
                                    )
                                )
                except Exception as e:
                    logger.error(f"Error reading universe file {path}: {e}")

        return stocks

    def filter_stock(
        self,
        symbol: str,
        df: pd.DataFrame,
        market: str = "IN",
        capital: Optional[float] = None,
        tier: str = "Small",
    ) -> UniverseFilterResult:
        """Applies liquidity, price floor, volatility cap and affordability filters.
        Assigns exactly one unambiguous status code:
        SCANNED | NO_DATA | INSUFFICIENT_HISTORY (<252 bars) | ILLIQUID | PRICE_FLOOR | VOLATILITY_CAP | DATA_ERROR
        """
        mkt_cfg = settings.get_market_config(market)
        risk_cfg = settings.get_risk_config()
        cap = capital or mkt_cfg.capital
        is_higher_risk = (tier == "Small")

        # 1. No Data check
        if df is None or len(df) == 0:
            return UniverseFilterResult(
                symbol=symbol,
                passed=False,
                rejection_reasons=["No daily candle data available"],
                status="NO_DATA",
                last_price=0.0,
                avg_turnover=0.0,
                atr_pct=0.0,
                is_affordable=False,
                tier=tier,
                is_higher_risk=is_higher_risk,
            )

        # 2. Insufficient History check (<252 bars for full annual lookback / 200 SMA / 52w range)
        if len(df) < 20:
            return UniverseFilterResult(
                symbol=symbol,
                passed=False,
                rejection_reasons=[f"Insufficient history ({len(df)} bars < 20 minimum)"],
                status="INSUFFICIENT_HISTORY (<252 bars)",
                last_price=float(df["close"].iloc[-1]) if "close" in df.columns else 0.0,
                avg_turnover=0.0,
                atr_pct=0.0,
                is_affordable=False,
                tier=tier,
                is_higher_risk=is_higher_risk,
            )

        try:
            last_row = df.iloc[-1]
            last_price = float(last_row["close"])

            # 3. Liquidity (20-day average traded value = close * volume)
            turnover_20d = (df["close"].iloc[-20:] * df["volume"].iloc[-20:]).mean()

            # 4. Volatility (ATR14 / price <= max_atr_pct)
            atr = float(last_row.get("atr14", 0.0))
            atr_pct = (atr / last_price * 100.0) if last_price > 0 else 0.0

            # 5. Affordability
            max_share_price = cap * (risk_cfg.max_share_price_pct_of_capital / 100.0)
            is_affordable = last_price <= max_share_price

            rejections = []
            primary_status = "SCANNED"

            # Check primary filters in strict hierarchical priority:
            if len(df) < 252:
                rejections.append(f"History length {len(df)} bars is less than full annual 252-bar requirement")
                primary_status = "INSUFFICIENT_HISTORY (<252 bars)"
            elif turnover_20d < mkt_cfg.min_avg_traded_value:
                rejections.append(f"Avg 20d turnover {turnover_20d:,.0f} below min {mkt_cfg.min_avg_traded_value:,.0f}")
                primary_status = "ILLIQUID"
            elif last_price < mkt_cfg.min_price:
                rejections.append(f"Price {last_price:.2f} below min price floor {mkt_cfg.min_price}")
                primary_status = "PRICE_FLOOR"
            elif atr_pct > risk_cfg.max_atr_pct:
                rejections.append(f"ATR% {atr_pct:.2f}% exceeds max volatility cap {risk_cfg.max_atr_pct}%")
                primary_status = "VOLATILITY_CAP"
            elif not is_affordable:
                rejections.append(f"Price {last_price:.2f} exceeds affordability cap {max_share_price:.2f}")

            passed = (len(rejections) == 0 and len(df) >= 20)
            if passed:
                primary_status = "SCANNED"

            return UniverseFilterResult(
                symbol=symbol,
                passed=passed,
                rejection_reasons=rejections,
                status=primary_status,
                last_price=last_price,
                avg_turnover=turnover_20d,
                atr_pct=atr_pct,
                is_affordable=is_affordable,
                tier=tier,
                is_higher_risk=is_higher_risk,
            )
        except Exception as e:
            logger.error(f"Data error filtering stock {symbol}: {e}")
            return UniverseFilterResult(
                symbol=symbol,
                passed=False,
                rejection_reasons=[f"Data error: {e}"],
                status="DATA_ERROR",
                last_price=0.0,
                avg_turnover=0.0,
                atr_pct=0.0,
                is_affordable=False,
                tier=tier,
                is_higher_risk=is_higher_risk,
            )

    def evaluate_coverage(
        self,
        market: str = "IN",
        data_map: Optional[Dict[str, pd.DataFrame]] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Provides full visibility across the universe coverage funnel:
        Listed -> has data -> enough history -> liquid -> passes filters -> scanned.
        Every single instrument is assigned exactly one status.
        """
        all_master = self.parse_master_scrip_list(market=market)
        if not all_master:
            # Fallback
            stocks = self.load_universe(market=market, db=db)
            all_master = [{"symbol": s.symbol, "name": s.name, "series": "EQ", "tier": s.tier, "is_higher_risk": s.is_higher_risk, "status": "SCANNED", "status_reason": ""} for s in stocks]

        total_listed = len(all_master)
        series_excluded = sum(1 for m in all_master if m["status"] == "SERIES_EXCLUDED")
        equities_eligible = total_listed - series_excluded

        # Evaluate status for every eligible equity
        items = []
        counts = {
            "SERIES_EXCLUDED": series_excluded,
            "NO_DATA": 0,
            "INSUFFICIENT_HISTORY (<252 bars)": 0,
            "ILLIQUID": 0,
            "PRICE_FLOOR": 0,
            "VOLATILITY_CAP": 0,
            "SCANNED": 0,
            "DATA_ERROR": 0,
        }

        tier_breakdown = {"Large": 0, "Mid": 0, "Small": 0}

        for m in all_master:
            sym = m["symbol"]
            tier = m.get("tier", "Small")
            if m["status"] == "SERIES_EXCLUDED":
                items.append({
                    "symbol": sym,
                    "name": m["name"],
                    "series": m["series"],
                    "tier": tier,
                    "status": "SERIES_EXCLUDED",
                    "reason": m["status_reason"],
                    "last_price": None,
                    "avg_turnover": None,
                    "atr_pct": None,
                    "bars_count": 0,
                })
                continue

            tier_breakdown[tier] = tier_breakdown.get(tier, 0) + 1
            df = data_map.get(sym) if data_map else None

            if df is None:
                counts["NO_DATA"] += 1
                items.append({
                    "symbol": sym,
                    "name": m["name"],
                    "series": m["series"],
                    "tier": tier,
                    "status": "NO_DATA",
                    "reason": "No daily candles cached or ingested",
                    "last_price": None,
                    "avg_turnover": None,
                    "atr_pct": None,
                    "bars_count": 0,
                })
            else:
                res = self.filter_stock(sym, df, market=market, tier=tier)
                st = res.status
                counts[st] = counts.get(st, 0) + 1
                items.append({
                    "symbol": sym,
                    "name": m["name"],
                    "series": m["series"],
                    "tier": tier,
                    "status": st,
                    "reason": "; ".join(res.rejection_reasons) or "Passed all universe filters",
                    "last_price": round(res.last_price, 2) if res.last_price > 0 else None,
                    "avg_turnover": round(res.avg_turnover, 0) if res.avg_turnover > 0 else None,
                    "atr_pct": round(res.atr_pct, 2) if res.atr_pct > 0 else None,
                    "bars_count": len(df),
                })

        # Calculate coverage funnel stages
        has_data_count = equities_eligible - counts["NO_DATA"]
        enough_history_count = has_data_count - counts["INSUFFICIENT_HISTORY (<252 bars)"]
        liquid_count = enough_history_count - counts["ILLIQUID"]
        passes_filters_count = liquid_count - counts["PRICE_FLOOR"] - counts["VOLATILITY_CAP"]
        scanned_count = counts["SCANNED"]

        pipeline_stages = [
            {"stage": "Listed Master", "count": total_listed, "description": "All NSE instruments in official scrip master"},
            {"stage": "Eligible Equities", "count": equities_eligible, "description": "NSE -EQ series excluding ETFs and SME series"},
            {"stage": "Has Daily Data", "count": has_data_count, "description": "Daily bars ingested into database"},
            {"stage": "Enough History", "count": enough_history_count, "description": "Meets 252-bar annual lookback requirement"},
            {"stage": "Liquid Tier", "count": liquid_count, "description": "20-day average traded value exceeds minimum"},
            {"stage": "Passes Filters", "count": passes_filters_count, "description": "Meets minimum price floor & volatility cap"},
            {"stage": "Scanned & Ranked", "count": scanned_count, "description": "Eligible universe for trend template & setup scans"},
        ]

        return {
            "market": market,
            "total_listed": total_listed,
            "series_excluded": series_excluded,
            "equities_eligible": equities_eligible,
            "status_counts": counts,
            "tier_breakdown": tier_breakdown,
            "pipeline": pipeline_stages,
            "items": items,
        }

    def generate_coverage_csv(self, coverage_dict: Dict[str, Any]) -> str:
        """Generates downloadable CSV string with full status and reasons for every symbol."""
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["symbol", "name", "series", "tier", "status", "reason", "last_price", "avg_turnover_20d", "atr_pct", "bars_count"])
        for item in coverage_dict.get("items", []):
            writer.writerow([
                item.get("symbol"),
                item.get("name"),
                item.get("series"),
                item.get("tier"),
                item.get("status"),
                item.get("reason"),
                item.get("last_price") or "",
                item.get("avg_turnover") or "",
                item.get("atr_pct") or "",
                item.get("bars_count") or 0,
            ])
        return output.getvalue()


universe_manager = UniverseManager()
