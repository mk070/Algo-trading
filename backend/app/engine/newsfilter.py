import datetime
import hashlib
import json
import logging
import re
from typing import Dict, List, Optional, Tuple
import yaml
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import NewsCoverage, NewsEvent
from app.settings import CONFIG_DIR, settings

logger = logging.getLogger(__name__)


class ClassifiedNewsItem(BaseModel):
    symbol: str
    source: str
    title: str
    url: Optional[str] = None
    published_at: datetime.datetime
    ingested_at: datetime.datetime
    severity: str  # RED, AMBER, GREEN
    category: Optional[str] = None
    dedupe_key: str
    canonical_event_id: Optional[str] = None
    ai_summary: Optional[str] = None
    latency_sec: float


class SymbolNewsCoverage(BaseModel):
    symbol: str
    status: str  # CLEAR, REVIEW, BLOCKED, UNKNOWN
    sources_checked: List[str]
    has_earnings_blackout: bool
    earnings_date: Optional[datetime.date] = None
    red_events_count: int
    amber_events_count: int
    recent_events: List[ClassifiedNewsItem]
    checked_at: datetime.datetime


class NewsIntelligenceEngine:
    """Classifies announcements, enforces earnings blackout, handles deduplication, and calculates coverage."""

    def __init__(self):
        self.rules = self._load_rules()
        self.cfg = settings.get_news_config()

    def _load_rules(self) -> Dict:
        rules_path = CONFIG_DIR / "news_rules.yaml"
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading news rules: {e}")
        return {}

    def classify_severity(self, text: str) -> Tuple[str, str]:
        """Deterministic keyword matching for severity (RED, AMBER, GREEN)."""
        lower = text.lower()
        rules = self.rules.get("severity_rules", {})

        # Check RED first (highest priority)
        red_words = rules.get("RED", {}).get("keywords", [])
        for kw in red_words:
            if kw.lower() in lower:
                return "RED", f"Matched critical keyword: '{kw}'"

        # Check AMBER
        amber_words = rules.get("AMBER", {}).get("keywords", [])
        for kw in amber_words:
            if kw.lower() in lower:
                return "AMBER", f"Matched caution keyword: '{kw}'"

        # Check GREEN
        green_words = rules.get("GREEN", {}).get("keywords", [])
        for kw in green_words:
            if kw.lower() in lower:
                return "GREEN", f"Matched positive operational keyword: '{kw}'"

        return "GREEN", "Informational announcement"

    def compute_dedupe_key(
        self, symbol: str, title: str, published_at: datetime.datetime
    ) -> str:
        """Normalized token + 48h time-bucket deduplication key."""
        clean_tokens = sorted(list(set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", title.lower()))))
        token_str = " ".join(clean_tokens[:10])
        # 48-hour bucket
        hours_bucket = int(published_at.timestamp() // (self.cfg.dedupe_window_hours * 3600))
        raw = f"{symbol.upper()}_{token_str}_{hours_bucket}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def process_raw_announcement(
        self,
        symbol: str,
        source: str,
        title: str,
        url: Optional[str],
        published_at: datetime.datetime,
        raw_payload: Optional[Dict] = None,
        db: Optional[Session] = None,
    ) -> ClassifiedNewsItem:
        ingested_at = datetime.datetime.utcnow()
        latency_sec = max(0.0, (ingested_at - published_at).total_seconds())
        severity, category = self.classify_severity(title)
        dedupe_key = self.compute_dedupe_key(symbol, title, published_at)

        item = ClassifiedNewsItem(
            symbol=symbol.upper(),
            source=source,
            title=title,
            url=url,
            published_at=published_at,
            ingested_at=ingested_at,
            severity=severity,
            category=category,
            dedupe_key=dedupe_key,
            canonical_event_id=dedupe_key,
            ai_summary=None,
            latency_sec=latency_sec,
        )

        if db is not None:
            # Check duplicate
            existing = db.query(NewsEvent).filter(NewsEvent.dedupe_key == dedupe_key).first()
            if not existing:
                evt = NewsEvent(
                    symbol=item.symbol,
                    source=item.source,
                    source_id=url,
                    title=item.title,
                    url=item.url,
                    published_at=item.published_at,
                    ingested_at=item.ingested_at,
                    severity=item.severity,
                    category=item.category,
                    dedupe_key=item.dedupe_key,
                    canonical_event_id=item.canonical_event_id,
                    raw_json=json.dumps(raw_payload) if raw_payload else None,
                )
                db.add(evt)
                db.commit()

        return item

    def check_symbol_coverage(
        self,
        symbol: str,
        market: str = "IN",
        earnings_date: Optional[datetime.date] = None,
        asof_date: Optional[datetime.date] = None,
        db: Optional[Session] = None,
    ) -> SymbolNewsCoverage:
        now = datetime.datetime.utcnow()
        ref_date = asof_date or datetime.date.today()
        sources_checked = ["NSE_DISCLOSURES", "BSE_ANNOUNCEMENTS"] if market == "IN" else ["SEC_EDGAR"]
        recent_items: List[ClassifiedNewsItem] = []
        red_count = 0
        amber_count = 0

        # Check DB for events in last 14 days
        if db is not None:
            cutoff = datetime.datetime.combine(ref_date - datetime.timedelta(days=14), datetime.time.min)
            db_evts = (
                db.query(NewsEvent)
                .filter(NewsEvent.symbol == symbol, NewsEvent.published_at >= cutoff)
                .order_by(NewsEvent.published_at.desc())
                .all()
            )
            for e in db_evts:
                item = ClassifiedNewsItem(
                    symbol=e.symbol,
                    source=e.source,
                    title=e.title,
                    url=e.url,
                    published_at=e.published_at,
                    ingested_at=e.ingested_at,
                    severity=e.severity,
                    category=e.category,
                    dedupe_key=e.dedupe_key,
                    canonical_event_id=e.canonical_event_id,
                    ai_summary=e.ai_summary,
                    latency_sec=(e.ingested_at - e.published_at).total_seconds(),
                )
                recent_items.append(item)
                if e.severity == "RED":
                    red_count += 1
                elif e.severity == "AMBER":
                    amber_count += 1

        # Check Earnings Blackout
        has_blackout = False
        if earnings_date:
            days_to_earnings = (earnings_date - ref_date).days
            if 0 <= days_to_earnings <= self.cfg.earnings_block_days:
                has_blackout = True

        # Determine Coverage Status: CLEAR, REVIEW, BLOCKED, UNKNOWN
        if red_count > 0 or has_blackout:
            status = "BLOCKED"
        elif amber_count > 0:
            status = "REVIEW"
        else:
            # If no data sources were checked or no earnings info is known, mark UNKNOWN
            # Per Rule 11: "Unknown is not clear."
            if not sources_checked:
                status = "UNKNOWN"
            else:
                status = "CLEAR"

        return SymbolNewsCoverage(
            symbol=symbol,
            status=status,
            sources_checked=sources_checked,
            has_earnings_blackout=has_blackout,
            earnings_date=earnings_date,
            red_events_count=red_count,
            amber_events_count=amber_count,
            recent_events=recent_items,
            checked_at=now,
        )


news_engine = NewsIntelligenceEngine()

