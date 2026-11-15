"""New Neon Project Database Migration & Verification Orchestrator.

Orchestrates Phase 2 (schema creation), Phase 3 (real backup restoration),
and Phase 4 (instruments reconstruction and verification) on a target Neon Free database.
"""

import argparse
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# Ensure project root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from alembic.config import Config
from alembic import command
from app.db_backup import restore_database_backup
from app.engine.universe import universe_manager
from app.models import Base, Instrument, Position, Journal, Fill, Signal, DecisionAudit, DecisionStageResult, NewsEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("neon_migration")


def run_migration_pipeline(target_url: str, backup_path: Optional[Path] = None) -> Dict[str, Any]:
    """Executes complete migration pipeline against target_url without modifying old databases."""
    backup_file = backup_path or (ROOT_DIR / "data" / "backups" / "neon_pg_backup_20261106_182900.json")
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found at {backup_file}")

    logger.info("================================================================================")
    logger.info("PHASE 1: Verifying connectivity to target database...")
    logger.info("================================================================================")

    # Use direct unpooled connection for schema creation and transactional imports
    import re
    direct_url = re.sub(r"[?&]channel_binding=[^&]+", "", target_url)
    direct_url = direct_url.replace("-pooler", "").strip()
    if direct_url.startswith("postgres://"):
        direct_url = direct_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif direct_url.startswith("postgresql://") and not direct_url.startswith("postgresql+"):
        direct_url = direct_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(direct_url, pool_pre_ping=True)
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1;"))
        assert res.scalar() == 1, "Connectivity check failed"
    logger.info("Target database connectivity verified.")

    logger.info("================================================================================")
    logger.info("PHASE 2: Applying Alembic schema migrations (001 -> 005 head)...")
    logger.info("================================================================================")
    os.environ["MIGRATION_DATABASE_URL"] = direct_url
    alembic_cfg = Config(str(ROOT_DIR / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")

    # Verify tables against Base.metadata
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables
    if missing_tables:
        raise RuntimeError(f"Migration completed but tables are missing: {missing_tables}")
    logger.info(f"All {len(existing_tables)} database tables successfully created.")

    logger.info("================================================================================")
    logger.info("PHASE 3: Restoring verified research evidence and operational backup...")
    logger.info("================================================================================")
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        restore_result = restore_database_backup(backup_file, db=session)
        logger.info(f"Restored {restore_result['total_records_restored']} records from backup.")

        logger.info("================================================================================")
        logger.info("PHASE 4: Reconstructing missing instruments from scrip master...")
        logger.info("================================================================================")
        inst_res = universe_manager.refresh_instrument_master(market="IN", db=session)
        logger.info(f"Instrument reconstruction completed: {inst_res}")

        logger.info("================================================================================")
        logger.info("PHASE 5: Verifying application state & representative records...")
        logger.info("================================================================================")
        # Verify row counts
        counts = {
            "instruments": session.query(Instrument).count(),
            "positions": session.query(Position).count(),
            "fills": session.query(Fill).count(),
            "journal": session.query(Journal).count(),
            "signals": session.query(Signal).count(),
            "decision_audits": session.query(DecisionAudit).count(),
            "decision_stage_results": session.query(DecisionStageResult).count(),
            "news_events": session.query(NewsEvent).count(),
        }

        assert counts["instruments"] >= 2700, f"Expected >= 2700 instruments, got {counts['instruments']}"
        assert counts["positions"] == 1, f"Expected 1 position, got {counts['positions']}"
        assert counts["fills"] == 2, f"Expected 2 fills, got {counts['fills']}"
        assert counts["journal"] == 1, f"Expected 1 journal entry, got {counts['journal']}"
        assert counts["signals"] == 108, f"Expected 108 signals, got {counts['signals']}"
        assert counts["decision_audits"] == 2331, f"Expected 2331 audits, got {counts['decision_audits']}"
        assert counts["decision_stage_results"] == 16317, f"Expected 16317 stage results, got {counts['decision_stage_results']}"
        assert counts["news_events"] == 5200, f"Expected 5200 news events, got {counts['news_events']}"

        logger.info("All representative records verified successfully!")
        return {
            "status": "SUCCESS",
            "sha256": restore_result["sha256"],
            "restoration": restore_result,
            "instrument_reconstruction": inst_res,
            "final_counts": counts,
        }
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Swing Trading Platform to New Neon Project")
    parser.add_argument("--url", help="Target database URL (or via MIGRATION_DATABASE_URL environment variable)")
    parser.add_argument("--backup", help="Path to backup JSON snapshot")
    args = parser.parse_args()

    db_url = args.url or os.environ.get("MIGRATION_DATABASE_URL")
    if not db_url:
        print("Error: Target database URL must be provided via --url or MIGRATION_DATABASE_URL.")
        print("Example: python -m app.migrate_new_db --url 'postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require'")
        sys.exit(1)

    backup_path = Path(args.backup) if args.backup else None
    result = run_migration_pipeline(db_url, backup_path=backup_path)
    print("\nMigration Pipeline Summary:")
    print(f"Status: {result['status']}")
    print(f"Total Records Restored: {result['restoration']['total_records_restored']}")
    print(f"Instruments Reconstructed: {result['instrument_reconstruction']['inserted']}")
    print(f"Final Counts: {result['final_counts']}")
