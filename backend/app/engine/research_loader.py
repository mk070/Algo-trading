"""Research Data Loader Module.

Switches between local Parquet snapshot and Neon PostgreSQL via the
RESEARCH_DATA_SOURCE configuration setting (default: 'parquet').
Guarantees that research workloads, backtests, and audit metrics do not
exhaust Neon PostgreSQL compute or egress allowances.

load_research_bars_for_paper() always queries Neon PostgreSQL directly
so that forward paper evaluation uses the most recent market data, not
a stale parquet snapshot.
"""

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy.orm import Session

from app.models import DailyBar
from app.settings import DATA_DIR, settings

logger = logging.getLogger(__name__)

# In-memory cache for research snapshot DataFrame
_cached_parquet_df: Optional[pd.DataFrame] = None


def get_research_snapshot_path() -> Optional[Path]:
    p = DATA_DIR / "research" / "research_snapshot_20261106.parquet"
    if p.exists():
        return p
    # Fallback to any parquet in data/research
    candidates = list((DATA_DIR / "research").glob("*.parquet"))
    for c in candidates:
        if "snapshot" in c.name:
            return c
    return candidates[0] if candidates else None


def load_research_bars(
    symbols: List[str],
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    db: Optional[Session] = None,
) -> Dict[str, pd.DataFrame]:
    """Loads daily bars for research workloads.
    Uses local Parquet if RESEARCH_DATA_SOURCE='parquet' (default),
    otherwise queries PostgreSQL via db session.
    """
    global _cached_parquet_df
    source = settings.research_data_source.lower().strip()

    if source == "parquet":
        snapshot_path = get_research_snapshot_path()
        if snapshot_path:
            try:
                if _cached_parquet_df is None:
                    logger.info(f"Loading local research snapshot from {snapshot_path.name}...")
                    _cached_parquet_df = pd.read_parquet(snapshot_path)
                    if "date" in _cached_parquet_df.columns:
                        _cached_parquet_df["date"] = pd.to_datetime(_cached_parquet_df["date"]).dt.date

                df = _cached_parquet_df
                if symbols:
                    df = df[df["symbol"].isin(symbols)]
                if start_date:
                    df = df[df["date"] >= start_date]
                if end_date:
                    df = df[df["date"] <= end_date]

                results: Dict[str, pd.DataFrame] = {}
                for sym, grp in df.groupby("symbol"):
                    results[sym] = grp.sort_values("date").copy()
                return results
            except Exception as e:
                logger.warning(f"Failed to load research parquet ({e}), falling back to database.")

    # Fallback to DB if parquet unavailable or source is 'db'
    if db is None:
        return {}

    query = db.query(DailyBar).filter(DailyBar.symbol.in_(symbols))
    if start_date:
        query = query.filter(DailyBar.date >= start_date)
    if end_date:
        query = query.filter(DailyBar.date <= end_date)

    rows = query.order_by(DailyBar.symbol, DailyBar.date.asc()).all()
    results = {}
    for r in rows:
        row_dict = {
            "date": r.date,
            "open": r.split_adj_open or r.open,
            "high": r.split_adj_high or r.high,
            "low": r.split_adj_low or r.low,
            "close": r.split_adj_close or r.close,
            "adj_close": r.adj_close or r.close,
            "volume": r.volume,
            "source": r.source,
        }
        results.setdefault(r.symbol, []).append(row_dict)

    return {sym: pd.DataFrame(items) for sym, items in results.items()}


# ─── Forward Paper Evaluation Loader ─────────────────────────────────────────

_paper_bars_cache: Dict[str, Any] = {
    "cached_at": None,
    "bars_dict": None,
    "data_through_date": None,
}
PAPER_CACHE_TTL_SECONDS = 600  # 10 minutes


def get_indian_paper_universe_symbols() -> List[str]:
    """Returns canonical list of Indian symbols for forward paper evaluation.

    Reads symbols from research snapshot manifest if available, fallback to liquid universe.
    """
    manifest_path = DATA_DIR / "research" / "research_snapshot_manifest.json"
    if manifest_path.exists():
        try:
            import json
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Manifest contains both US and IN; filter out obvious US symbols
            us_known = {
                "AAPL", "ABBV", "AMD", "AMZN", "AVGO", "BLDR", "BRK.B", "COST",
                "CRM", "CVX", "DECK", "ELF", "FIX", "FND", "GOOGL", "HD", "HUBB",
                "IBKR", "ISRG", "LLY", "META", "MSFT", "NVDA", "NVO", "ORCL", "PANW",
                "PLTR", "PWR", "SMCI", "TSLA", "V", "VRT", "WMT", "BSE:SENSEX"
            }
            symbols = [s for s in data.get("symbols", []) if s not in us_known]
            if symbols:
                return sorted(symbols)
        except Exception as e:
            logger.warning(f"[paper_loader] Failed to read manifest symbols: {e}")

    # Fallback to liquid Indian equities
    try:
        from app.engine.universe import universe_manager
        univ = universe_manager.load_universe("IN")
        if univ:
            return sorted([s.symbol for s in univ[:100]])
    except Exception:
        pass

    return []


def load_research_bars_for_paper(
    db=None,
    symbols: Optional[List[str]] = None,
    min_history_bars: int = 220,
    max_sessions: int = 400,
    force_refresh: bool = False,
) -> Tuple[Dict[str, pd.DataFrame], Optional[datetime.date]]:
    """Load bars for forward paper evaluation from Neon PostgreSQL (most current).

    Optimized for Neon free plan:
    - Filters by Indian instruments in SQL.
    - Selects only required OHLCV columns.
    - Limits to last ~400 sessions (min_date ~600 calendar days ago).
    - In-process TTL cache (10 min) to avoid duplicate egress on repeated queries.
    - Tracks and logs egress byte/row count (target < 10 MB per run).

    Returns (bars_dict, data_through_date).
    """
    global _paper_bars_cache
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Check in-process cache
    if not force_refresh and _paper_bars_cache["cached_at"] is not None:
        age = (now - _paper_bars_cache["cached_at"]).total_seconds()
        if age < PAPER_CACHE_TTL_SECONDS and _paper_bars_cache["bars_dict"]:
            logger.debug(f"[paper_loader] Using in-process cache ({age:.0f}s old)")
            return _paper_bars_cache["bars_dict"], _paper_bars_cache["data_through_date"]

    bars_dict: Dict[str, pd.DataFrame] = {}
    data_through_date: Optional[datetime.date] = None

    target_symbols = symbols or get_indian_paper_universe_symbols()

    # Calculate min_date for ~400 trading sessions (approx 600 calendar days)
    today = datetime.date.today()
    min_date = today - datetime.timedelta(days=int(max_sessions * 1.5))

    _db = db
    _owns_ctx = False
    if _db is None:
        try:
            from app.db import transaction_context
            _owns_ctx = True
        except ImportError:
            pass

    def _query_db(session) -> Tuple[Dict[str, pd.DataFrame], Optional[datetime.date]]:
        try:
            from app.models import Instrument
            # Project only needed columns in SQL
            q = (
                session.query(
                    DailyBar.symbol,
                    DailyBar.date,
                    DailyBar.open,
                    DailyBar.high,
                    DailyBar.low,
                    DailyBar.close,
                    DailyBar.split_adj_open,
                    DailyBar.split_adj_high,
                    DailyBar.split_adj_low,
                    DailyBar.split_adj_close,
                    DailyBar.volume,
                )
                .join(Instrument, Instrument.symbol == DailyBar.symbol)
                .filter(
                    Instrument.market == "IN",
                    DailyBar.date >= min_date,
                )
            )
            if target_symbols:
                q = q.filter(DailyBar.symbol.in_(target_symbols))

            q = q.order_by(DailyBar.symbol.asc(), DailyBar.date.asc())
            rows = q.all()

            row_count = len(rows)
            # Estimate egress size: 11 fields * avg ~8 bytes = ~88 bytes/row
            egress_mb = (row_count * 88) / (1024 * 1024)
            logger.info(
                f"[paper_loader] Neon SQL egress: {row_count} rows (~{egress_mb:.2f} MB) "
                f"across requested symbols since {min_date}. Target: <10 MB."
            )

            if not rows:
                return {}, None

            result_dict: Dict[str, list] = {}
            max_d: Optional[datetime.date] = None

            for r in rows:
                row_dict = {
                    "date": r.date,
                    "open": float(r.split_adj_open or r.open or 0),
                    "high": float(r.split_adj_high or r.high or 0),
                    "low": float(r.split_adj_low or r.low or 0),
                    "close": float(r.split_adj_close or r.close or 0),
                    "volume": float(r.volume or 0),
                }
                result_dict.setdefault(r.symbol, []).append(row_dict)
                if r.date and (max_d is None or r.date > max_d):
                    max_d = r.date

            out: Dict[str, pd.DataFrame] = {}
            for sym, items in result_dict.items():
                df = pd.DataFrame(items)
                df["date"] = pd.to_datetime(df["date"]).dt.date
                df = df.sort_values("date").reset_index(drop=True)
                if len(df) >= min_history_bars:
                    out[sym] = df

            return out, max_d

        except Exception as e:
            logger.warning(f"[paper_loader] Neon SQL query failed: {e}")
            return {}, None

    if _db is not None:
        bars_dict, data_through_date = _query_db(_db)
    elif _owns_ctx:
        from app.db import transaction_context
        try:
            with transaction_context() as session:
                bars_dict, data_through_date = _query_db(session)
        except Exception as e:
            logger.warning(f"[paper_loader] DB session failed: {e}")

    # Fallback to local parquet snapshot if DB returned nothing
    if not bars_dict:
        logger.warning("[paper_loader] DB unavailable — falling back to local parquet snapshot")
        snapshot_path = get_research_snapshot_path()
        if snapshot_path and snapshot_path.exists():
            try:
                raw = pd.read_parquet(snapshot_path)
                if "date" in raw.columns:
                    raw["date"] = pd.to_datetime(raw["date"]).dt.date
                if target_symbols:
                    raw = raw[raw["symbol"].isin(target_symbols)]
                for sym, grp in raw.groupby("symbol"):
                    df = grp.sort_values("date").reset_index(drop=True)
                    if len(df) >= min_history_bars:
                        bars_dict[sym] = df
                if bars_dict:
                    all_dates = [d for df in bars_dict.values() for d in df["date"].tolist()]
                    data_through_date = max(all_dates) if all_dates else None
                    logger.info(f"[paper_loader] Parquet fallback loaded {len(bars_dict)} symbols through {data_through_date}")
            except Exception as e:
                logger.error(f"[paper_loader] Parquet fallback also failed: {e}")

    # Update cache
    if bars_dict:
        _paper_bars_cache = {
            "cached_at": now,
            "bars_dict": bars_dict,
            "data_through_date": data_through_date,
        }

    logger.info(f"[paper_loader] Loaded {len(bars_dict)} symbols for paper eval, data through {data_through_date}")
    return bars_dict, data_through_date


def get_paper_data_staleness(data_through_date: Optional[datetime.date]) -> int:
    """Return number of NSE trading sessions missed since data_through_date.

    Uses calendar weekday approximation (Mon–Fri). Public holidays are not modeled.
    Returns 0 if data is current, -1 if data_through_date is None.
    """
    if data_through_date is None:
        return -1
    today = datetime.date.today()
    if data_through_date >= today:
        return 0
    # Count weekdays between data_through_date and yesterday (inclusive)
    missed = 0
    cur = data_through_date + datetime.timedelta(days=1)
    while cur < today:
        if cur.weekday() < 5:  # Mon–Fri
            missed += 1
        cur += datetime.timedelta(days=1)
    return missed
