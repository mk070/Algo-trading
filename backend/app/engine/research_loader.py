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

def load_research_bars_for_paper(
    db=None,
    min_history_bars: int = 220,
) -> Tuple[Dict[str, pd.DataFrame], Optional[datetime.date]]:
    """Load bars for forward paper evaluation from Neon PostgreSQL (most current).

    Returns (bars_dict, data_through_date):
    - bars_dict: symbol → DataFrame with columns [date, open, high, low, close, volume]
                 sorted ascending by date, filtered to IN-market symbols only.
    - data_through_date: the max date available across all symbols (or None if no data).

    Falls back gracefully to parquet if Neon query fails.
    Does NOT use _cached_parquet_df so as never to pollute the backtest cache with live data.
    """
    bars_dict: Dict[str, pd.DataFrame] = {}
    data_through_date: Optional[datetime.date] = None

    # Prefer Neon DB as the authoritative live source
    _db = db
    _owns_ctx = False
    if _db is None:
        try:
            from app.db import transaction_context
            _owns_ctx = True
        except ImportError:
            pass

    def _query_db(session) -> Tuple[Dict[str, pd.DataFrame], Optional[datetime.date]]:
        """Query bars_daily from Neon, return (bars_dict, max_date)."""
        try:
            # Only IN-market instruments to avoid US symbols in NSE universe
            from app.models import Instrument
            # Try to restrict to IN market
            try:
                in_symbols = {
                    r.symbol for r in session.query(Instrument.symbol).filter(
                        Instrument.market == "IN"
                    ).all()
                }
            except Exception:
                in_symbols = set()  # fallback: accept everything

            query = session.query(DailyBar).order_by(DailyBar.symbol, DailyBar.date.asc())
            rows = query.all()
            if not rows:
                return {}, None

            result_dict: Dict[str, list] = {}
            max_date: Optional[datetime.date] = None

            for r in rows:
                # Skip US symbols if we have an in_symbols set
                if in_symbols and r.symbol not in in_symbols:
                    continue
                row_dict = {
                    "date": r.date,
                    "open": float(r.split_adj_open or r.open or 0),
                    "high": float(r.split_adj_high or r.high or 0),
                    "low": float(r.split_adj_low or r.low or 0),
                    "close": float(r.split_adj_close or r.close or 0),
                    "volume": float(r.volume or 0),
                }
                result_dict.setdefault(r.symbol, []).append(row_dict)
                if r.date and (max_date is None or r.date > max_date):
                    max_date = r.date

            # Build DataFrames and filter to minimum history
            out: Dict[str, pd.DataFrame] = {}
            for sym, rows_list in result_dict.items():
                df = pd.DataFrame(rows_list)
                df["date"] = pd.to_datetime(df["date"]).dt.date
                df = df.sort_values("date").reset_index(drop=True)
                if len(df) >= min_history_bars:
                    out[sym] = df

            return out, max_date

        except Exception as e:
            logger.warning(f"[paper_loader] DB query failed: {e}")
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

    # Fall back to parquet if DB unavailable
    if not bars_dict:
        logger.warning("[paper_loader] DB unavailable — falling back to parquet snapshot")
        snapshot_path = get_research_snapshot_path()
        if snapshot_path and snapshot_path.exists():
            try:
                raw = pd.read_parquet(snapshot_path)
                if "date" in raw.columns:
                    raw["date"] = pd.to_datetime(raw["date"]).dt.date
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
