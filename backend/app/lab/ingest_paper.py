"""Strategy Lab — Incremental Market Data Ingestion for Forward Paper.

Refreshes Indian daily bars prior to paper study evaluation.
Reuses the existing Angel One SmartAPI daily bars provider with YFinance fallback,
split adjustments, and batch upsert into Neon PostgreSQL.
"""

import datetime
import logging
import time
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy.orm import Session

from app.engine.historical_ingestion import historical_ingestion_engine, validate_ohlcv_dataframe
from app.engine.research_loader import get_indian_paper_universe_symbols

logger = logging.getLogger(__name__)


def refresh_indian_paper_bars(
    db: Session,
    symbols: Optional[List[str]] = None,
    lookback_sessions: int = 20,
) -> Dict[str, Any]:
    """Ingest latest daily bars for Indian forward paper universe.

    Ensures recent bars (up to today/last completed session) are present in Neon PostgreSQL
    so that evaluate_study() never operates on stale bars.

    Returns dict with summary statistics.
    """
    target_symbols = symbols or get_indian_paper_universe_symbols()
    if not target_symbols:
        logger.warning("[ingest_paper] No symbols found for paper universe refresh.")
        return {"status": "NO_SYMBOLS", "symbols_updated": 0, "bars_upserted": 0}

    logger.info(f"[ingest_paper] Refreshing latest daily bars for {len(target_symbols)} Indian symbols...")
    start_t = time.perf_counter()

    updated = 0
    total_bars = 0
    errors: List[str] = []

    for sym in target_symbols:
        try:
            # Fetch recent bars using existing provider hierarchy (Angel One -> YFinance)
            df, provider, err = historical_ingestion_engine.fetch_historical_bars_for_symbol(
                symbol=sym,
                market="IN",
                target_sessions=lookback_sessions,
            )
            if df is None or df.empty:
                if err:
                    errors.append(f"{sym}: {err}")
                continue

            clean_df, _ = validate_ohlcv_dataframe(df, sym)
            if clean_df.empty:
                continue

            # Batch upsert into Neon DB
            n = historical_ingestion_engine.batch_upsert_bars(db, sym, clean_df, source=provider)
            updated += 1
            total_bars += n

        except Exception as e:
            logger.warning(f"[ingest_paper] Error ingesting {sym}: {e}")
            errors.append(f"{sym}: {str(e)}")

    db.commit()
    elapsed = time.perf_counter() - start_t
    logger.info(
        f"[ingest_paper] Completed refresh: {updated}/{len(target_symbols)} symbols updated, "
        f"{total_bars} bars upserted in {elapsed:.1f}s."
    )

    return {
        "status": "OK",
        "symbols_attempted": len(target_symbols),
        "symbols_updated": updated,
        "bars_upserted": total_bars,
        "duration_seconds": round(elapsed, 2),
        "error_count": len(errors),
    }
