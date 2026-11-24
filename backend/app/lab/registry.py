"""Strategy Lab — Registry Sync.

Loads swing_registry.yaml and synchronizes it into the lab_strategies DB table.
The DB is never the canonical source; YAML is.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy.orm import Session

from app.lab.engine import compute_config_hash

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent.parent / "research" / "swing_registry.yaml"


def load_registry_yaml() -> List[Dict[str, Any]]:
    """Load and return the strategies list from swing_registry.yaml."""
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry not found: {REGISTRY_PATH}")
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("strategies", [])


def _make_config_hash(params: Dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def sync_registry_to_db(db: Session) -> Dict[str, Any]:
    """
    Sync swing_registry.yaml → lab_strategies table.
    Returns summary of upserted/skipped records.
    Does NOT delete strategies that are still in the DB but removed from YAML
    (soft-disable: sets enabled=False).
    """
    from app.lab.models_lab import LabStrategy

    strategies = load_registry_yaml()
    yaml_ids = set()
    upserted = []
    skipped = []

    for s in strategies:
        sid = s["id"]
        yaml_ids.add(sid)
        params = s.get("parameters", {})
        config_hash = _make_config_hash(params)

        existing = db.query(LabStrategy).filter(LabStrategy.id == sid).first()
        if existing:
            if existing.config_hash != config_hash:
                existing.name = s["name"]
                existing.description = s.get("description", "")
                existing.enabled = s.get("enabled", True)
                existing.parameters_json = json.dumps(params)
                existing.config_hash = config_hash
                existing.min_history_bars = s.get("min_history_bars", 70)
                db.add(existing)
                upserted.append(sid)
            else:
                skipped.append(sid)
        else:
            rec = LabStrategy(
                id=sid,
                name=s["name"],
                description=s.get("description", ""),
                enabled=s.get("enabled", True),
                parameters_json=json.dumps(params),
                config_hash=config_hash,
                min_history_bars=s.get("min_history_bars", 70),
            )
            db.add(rec)
            upserted.append(sid)

    # Soft-disable removed strategies
    all_db = db.query(LabStrategy).all()
    for rec in all_db:
        if rec.id not in yaml_ids and rec.enabled:
            rec.enabled = False
            db.add(rec)
            upserted.append(f"{rec.id}(disabled)")

    db.commit()
    return {"upserted": upserted, "skipped": skipped}


def get_strategy_params(db: Session, strategy_id: str) -> Optional[Dict[str, Any]]:
    """Return parsed parameters dict for a strategy, or None if not found."""
    from app.lab.models_lab import LabStrategy
    rec = db.query(LabStrategy).filter(LabStrategy.id == strategy_id).first()
    if rec is None:
        return None
    return json.loads(rec.parameters_json) if rec.parameters_json else {}
