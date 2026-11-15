"""Research Data Loader Module.

Switches between local Parquet snapshot and Neon PostgreSQL via the
RESEARCH_DATA_SOURCE configuration setting (default: 'parquet').
Guarantees that research workloads, backtests, and audit metrics do not
exhaust Neon PostgreSQL compute or egress allowances.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
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
