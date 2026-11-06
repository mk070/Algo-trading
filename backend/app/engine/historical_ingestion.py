import datetime
import json
import logging
import time
import uuid
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.engine.calendars import get_expected_trading_days, is_exchange_holiday
from app.engine.corporate_actions import apply_verified_corporate_actions
from app.engine.universe import universe_manager
from app.models import DailyBar, IngestionCheckpoint, IngestionRun
from app.providers.alpaca_provider import AlpacaProvider
from app.providers.angelone_provider import AngelOneProvider
from app.providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

# Quality precedence tiers: higher tier can overwrite lower tier, but lower cannot overwrite higher
SOURCE_QUALITY_TIER = {
    "angelone": 3,
    "alpaca_iex": 3,
    "alpaca_sip": 4,
    "yfinance": 2,
    "synthetic_fixture": 1,
    "mock": 1,
}


def validate_ohlcv_dataframe(df: pd.DataFrame, symbol: str) -> Tuple[pd.DataFrame, List[str]]:
    """Strictly validates OHLC integrity:
    - High >= max(Open, Close)
    - Low <= min(Open, Close)
    - Positive prices
    - Non-negative volume
    - No duplicate dates
    Returns cleaned DataFrame and list of validation anomaly warnings.
    """
    warnings: List[str] = []
    if df.empty:
        return df, ["Empty dataframe"]

    df = df.copy()
    if "date" not in df.columns:
        return pd.DataFrame(), [f"Missing date column for {symbol}"]

    # Standardize dates
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    # Filter corrupt / non-positive prices
    valid_mask = (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)
    if not valid_mask.all():
        invalid_count = int((~valid_mask).sum())
        warnings.append(f"Dropped {invalid_count} non-positive price bars for {symbol}")
        df = df[valid_mask].copy()

    if df.empty:
        return df, warnings

    # High / Low boundary sanity check
    bad_hl = (df["high"] < df["open"]) | (df["high"] < df["close"]) | (df["low"] > df["open"]) | (df["low"] > df["close"])
    if bad_hl.any():
        bad_count = int(bad_hl.sum())
        warnings.append(f"Repaired {bad_count} High/Low boundary violations for {symbol}")
        # Repair boundaries to maintain candle containment
        df.loc[bad_hl, "high"] = df.loc[bad_hl, ["open", "close", "high"]].max(axis=1)
        df.loc[bad_hl, "low"] = df.loc[bad_hl, ["open", "close", "low"]].min(axis=1)

    # Zero volume warning
    zero_vol = (df["volume"] <= 0).sum()
    if zero_vol > 0:
        warnings.append(f"{symbol} has {int(zero_vol)} zero-volume bars")

    return df, warnings


class HistoricalIngestionEngine:
    """Incremental, resumable historical OHLCV ingestion pipeline.
    Targets 1,250 trading sessions (approx 5 years) per eligible symbol.
    """

    def __init__(self):
        self.angelone = AngelOneProvider()
        self.alpaca = AlpacaProvider()
        self.yfinance = YFinanceProvider()

    def get_or_create_run(
        self, db: Session, market: str = "IN", target_sessions: int = 1250, run_id: Optional[str] = None
    ) -> IngestionRun:
        """Retrieves existing active run or creates a new tracked ingestion run."""
        if run_id:
            run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
            if run:
                return run

        # Create new run
        new_id = f"run_{market.lower()}_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        symbols = self.get_symbols_for_market(market)

        run = IngestionRun(
            id=new_id,
            market=market.upper(),
            target_sessions=target_sessions,
            status="RUNNING",
            total_symbols=len(symbols),
            completed_symbols=0,
            failed_symbols=0,
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(run)
        db.commit()

        # Seed checkpoints for all symbols with resolved market (IN or US)
        us_set = set(s.symbol for s in universe_manager.load_universe("US"))
        for sym in symbols:
            sym_mkt = "US" if sym in us_set else "IN"
            existing_chk = (
                db.query(IngestionCheckpoint)
                .filter(IngestionCheckpoint.run_id == new_id, IngestionCheckpoint.symbol == sym)
                .first()
            )
            if not existing_chk:
                chk = IngestionCheckpoint(
                    run_id=new_id,
                    symbol=sym,
                    market=sym_mkt,
                    provider="pending",
                    status="PENDING",
                    expected_sessions=target_sessions,
                )
                db.add(chk)
        db.commit()
        return run

    def get_symbols_for_market(self, market: str) -> List[str]:
        """Loads canonical symbol universe for market."""
        m = market.upper()
        if m in ("IN", "NSE"):
            stocks = universe_manager.load_universe("IN")
            return [s.symbol for s in stocks]
        elif m == "US":
            stocks = universe_manager.load_universe("US")
            return [s.symbol for s in stocks]
        elif m == "ALL":
            in_stocks = [s.symbol for s in universe_manager.load_universe("IN")]
            us_stocks = [s.symbol for s in universe_manager.load_universe("US")]
            return sorted(list(set(in_stocks + us_stocks)))
        return []

    def fetch_historical_bars_for_symbol(
        self, symbol: str, market: str, target_sessions: int = 1250
    ) -> Tuple[Optional[pd.DataFrame], str, Optional[str]]:
        """Fetches historical bars with rate-limiting, retries, and fallback handling.
        Returns: (DataFrame, provider_name, error_message).
        """
        end_date = datetime.date.today()
        # Approx 5 years of calendar days to yield ~1,250 trading sessions
        start_date = end_date - datetime.timedelta(days=int(target_sessions * 1.55))

        m = market.upper()
        if m not in ("IN", "NSE", "US"):
            us_set = set(s.symbol for s in universe_manager.load_universe("US"))
            m = "US" if symbol in us_set else "IN"

        if m in ("IN", "NSE"):
            # 1. Try Angel One SmartAPI (Primary)
            if self.angelone.is_configured():
                try:
                    time.sleep(0.35)  # Enforce 3 req/sec rate limit
                    bars_dict = self.angelone.daily_bars([symbol], start=start_date, end=end_date)
                    df = bars_dict.get(symbol)
                    if df is not None and not df.empty and len(df) >= 50:
                        # Apply corporate actions split factors if needed
                        df = self._apply_split_adjustments(df, symbol, market="IN")
                        return df, "angelone", None
                except Exception as e:
                    logger.warning(f"Angel One fetch failed for {symbol}: {e}")

            # 2. Fallback to YFinance
            try:
                time.sleep(0.2)
                bars_dict = self.yfinance.daily_bars([symbol], start=start_date, end=end_date, market="IN")
                df = bars_dict.get(symbol)
                if df is not None and not df.empty:
                    df = self._apply_split_adjustments(df, symbol, market="IN")
                    return df, "yfinance", None
            except Exception as e:
                logger.error(f"YFinance fallback failed for {symbol}: {e}")
                return None, "failed", str(e)

        elif m == "US":
            # 1. Try Alpaca IEX (Primary with split adjustments)
            if self.alpaca.is_configured():
                try:
                    bars_dict = self.alpaca.daily_bars([symbol], start=start_date, end=end_date, adjustment="split")
                    df = bars_dict.get(symbol)
                    if df is not None and not df.empty and len(df) >= 50:
                        return df, "alpaca_iex", None
                except Exception as e:
                    logger.warning(f"Alpaca fetch failed for {symbol}: {e}")

            # 2. Fallback to YFinance
            try:
                time.sleep(0.2)
                bars_dict = self.yfinance.daily_bars([symbol], start=start_date, end=end_date, market="US")
                df = bars_dict.get(symbol)
                if df is not None and not df.empty:
                    df = self._apply_split_adjustments(df, symbol, market="US")
                    return df, "yfinance", None
            except Exception as e:
                logger.error(f"YFinance fallback failed for US symbol {symbol}: {e}")
                return None, "failed", str(e)

        return None, "none", "No provider returned historical bars"

    def _apply_split_adjustments(self, df: pd.DataFrame, symbol: str, market: str) -> pd.DataFrame:
        """Calculates and applies consistent split-adjusted OHLC prices across all 4 price points:
        O_adj = O * S, H_adj = H * S, L_adj = L * S, C_adj = C * S.
        Keeps dividend adjustment separate in dividend_factor = adj_close / split_adj_close.
        """
        df = df.copy()
        if "adj_close" not in df.columns:
            df["adj_close"] = df["close"]

        # If already split adjusted by Alpaca
        if "split_adj_close" in df.columns and "is_split_adjusted" in df.columns and df["is_split_adjusted"].iloc[0]:
            return df

        # Apply verified corporate actions master first (exact circular dates and ratios)
        df, applied = apply_verified_corporate_actions(df, symbol, market)
        if applied:
            return df

        # Detect splits via ratio between close and adj_close or via ratio changes
        # When unadjusted (like Angel One raw), check if yfinance split factor exists or check for large gap ratios
        # Default: if no external split calendar available, split_adj equals close, dividend_factor equals 1.0
        df["split_adj_open"] = df["open"]
        df["split_adj_high"] = df["high"]
        df["split_adj_low"] = df["low"]
        df["split_adj_close"] = df["close"]
        df["dividend_factor"] = 1.0
        df["is_split_adjusted"] = True

        # If adj_close exists and reflects both splits & dividends (as in yfinance)
        # Check if ratio between close and adj_close contains discrete integer split jumps (e.g. 2.0, 3.0, 5.0, 10.0)
        try:
            ratios = df["close"] / df["adj_close"].replace(0, 1)
            # Find significant split-like ratio jumps > 1.45 (indicates 2:1, 3:1, 5:1 bonus/split)
            if ratios.max() >= 1.45:
                # Approximate cumulative split multiplier
                cum_split = ratios.round(1)
                df["split_adj_open"] = round(df["open"] / cum_split, 4)
                df["split_adj_high"] = round(df["high"] / cum_split, 4)
                df["split_adj_low"] = round(df["low"] / cum_split, 4)
                df["split_adj_close"] = round(df["close"] / cum_split, 4)
                # Dividend factor isolates cash dividends from share dilution
                df["dividend_factor"] = round(df["adj_close"] / df["split_adj_close"].replace(0, 1), 4)
        except Exception:
            pass

        return df

    def batch_upsert_bars(self, db: Session, symbol: str, df: pd.DataFrame, source: str) -> int:
        """High-speed PostgreSQL bulk upsert respecting provider quality precedence.
        Prevents lower-quality fallback sources from overwriting higher-quality primary data.
        """
        if df.empty:
            return 0

        incoming_tier = SOURCE_QUALITY_TIER.get(source, 2)
        records = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        for _, row in df.iterrows():
            r_date = row["date"]
            if isinstance(r_date, pd.Timestamp):
                r_date = r_date.date()
            elif isinstance(r_date, str):
                r_date = datetime.date.fromisoformat(r_date[:10])

            records.append({
                "symbol": symbol,
                "date": r_date,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "adj_close": float(row.get("adj_close", row["close"])),
                "volume": float(row["volume"]),
                "source": source,
                "split_adj_open": float(row.get("split_adj_open", row["open"])),
                "split_adj_high": float(row.get("split_adj_high", row["high"])),
                "split_adj_low": float(row.get("split_adj_low", row["low"])),
                "split_adj_close": float(row.get("split_adj_close", row["close"])),
                "dividend_factor": float(row.get("dividend_factor", 1.0)),
                "is_split_adjusted": bool(row.get("is_split_adjusted", True)),
                "ingested_at": now_utc,
            })

        stmt = pg_insert(DailyBar).values(records)
        # Conditional update: only overwrite if incoming source is of equal or higher quality tier
        update_dict = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "adj_close": stmt.excluded.adj_close,
            "volume": stmt.excluded.volume,
            "source": stmt.excluded.source,
            "split_adj_open": stmt.excluded.split_adj_open,
            "split_adj_high": stmt.excluded.split_adj_high,
            "split_adj_low": stmt.excluded.split_adj_low,
            "split_adj_close": stmt.excluded.split_adj_close,
            "dividend_factor": stmt.excluded.dividend_factor,
            "is_split_adjusted": stmt.excluded.is_split_adjusted,
            "ingested_at": stmt.excluded.ingested_at,
        }

        # Universal quality precedence guard in SQL:
        # Incoming tier can overwrite existing row if and only if: existing_tier <= incoming_tier.
        # This protects primary data (e.g. SIP Tier 4 cannot be overwritten by IEX Tier 3 or YFinance Tier 2),
        # while permitting legitimate corrections from the same primary provider (Tier 3 <= Tier 3)
        # and upgrades from fallback to primary (Tier 2 <= Tier 3).
        precedence_sql = text(
            f"""
            (CASE bars_daily.source
                WHEN 'alpaca_sip' THEN 4
                WHEN 'angelone' THEN 3
                WHEN 'alpaca_iex' THEN 3
                WHEN 'yfinance' THEN 2
                ELSE 1
            END) <= {incoming_tier}
            """
        )

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "date"],
            set_=update_dict,
            where=precedence_sql,
        )

        res = db.execute(upsert_stmt)
        db.commit()
        return len(records)

    def ingest_symbol(
        self, db: Session, checkpoint: IngestionCheckpoint, target_sessions: int = 1250
    ) -> IngestionCheckpoint:
        """Executes resilient ingestion for a single symbol checkpoint."""
        symbol = checkpoint.symbol
        market = checkpoint.market
        checkpoint.status = "IN_PROGRESS"
        checkpoint.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()

        df, provider, error = self.fetch_historical_bars_for_symbol(symbol, market, target_sessions)
        if df is None or df.empty:
            checkpoint.status = "FAILED"
            checkpoint.error_message = error or "No bars returned by provider"
            checkpoint.updated_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return checkpoint

        # Validate OHLCV
        clean_df, val_warnings = validate_ohlcv_dataframe(df, symbol)
        if clean_df.empty:
            checkpoint.status = "FAILED"
            checkpoint.error_message = f"Validation failed: {'; '.join(val_warnings)}"
            checkpoint.updated_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return checkpoint

        # Persist to database
        self.batch_upsert_bars(db, symbol, clean_df, source=provider)

        # Exchange calendar reconciliation
        dates = sorted(clean_df["date"].tolist())
        earliest_d, latest_d = dates[0], dates[-1]
        expected_days = get_expected_trading_days(market, earliest_d, latest_d)
        actual_date_set = set(dates)
        missing_sessions = [d for d in expected_days if d not in actual_date_set]

        n_bars = len(dates)
        checkpoint.provider = provider
        checkpoint.available_sessions = n_bars
        checkpoint.expected_sessions = len(expected_days)
        checkpoint.missing_sessions_count = len(missing_sessions)
        checkpoint.earliest_date = earliest_d
        checkpoint.latest_date = latest_d
        checkpoint.meets_300 = (n_bars >= 300)
        checkpoint.meets_750 = (n_bars >= 750)
        checkpoint.meets_1250 = (n_bars >= 1250)
        checkpoint.split_adjusted = bool(clean_df.get("is_split_adjusted", pd.Series([False])).iloc[0])
        checkpoint.error_message = "; ".join(val_warnings) if val_warnings else None
        checkpoint.provenance_json = json.dumps({
            "feed": provider,
            "entitlement": "IEX (~2.5% US tape)" if "alpaca" in provider else "Angel One SmartAPI (100% NSE tape)",
            "survivorship_bias": "Present: current constituent",
            "val_warnings": val_warnings,
        })

        if n_bars >= 1250:
            checkpoint.status = "COMPLETED"
        elif n_bars >= 300:
            checkpoint.status = "PARTIAL"
        else:
            checkpoint.status = "INSUFFICIENT_DATA"

        checkpoint.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        return checkpoint

    def run_pipeline(
        self, market: str = "IN", target_sessions: int = 1250, run_id: Optional[str] = None
    ) -> IngestionRun:
        """Executes full resumable pipeline across all eligible universe symbols."""
        db = SessionLocal()
        try:
            run = self.get_or_create_run(db, market=market, target_sessions=target_sessions, run_id=run_id)
            run_id = run.id

            checkpoints = (
                db.query(IngestionCheckpoint)
                .filter(IngestionCheckpoint.run_id == run_id, IngestionCheckpoint.status.in_(["PENDING", "IN_PROGRESS"]))
                .all()
            )

            for chk in checkpoints:
                logger.info(f"Ingesting historical data for {chk.symbol} ({chk.market})...")
                self.ingest_symbol(db, chk, target_sessions=target_sessions)

            # Update run totals
            all_chks = db.query(IngestionCheckpoint).filter(IngestionCheckpoint.run_id == run_id).all()
            completed = sum(1 for c in all_chks if c.status in ("COMPLETED", "PARTIAL"))
            failed = sum(1 for c in all_chks if c.status == "FAILED")

            run.completed_symbols = completed
            run.failed_symbols = failed
            run.status = "COMPLETED" if failed == 0 else "PARTIAL_COMPLETION"
            run.finished_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return run
        finally:
            db.close()


historical_ingestion_engine = HistoricalIngestionEngine()

