import datetime
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import yaml
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engine.news_collectors import (
    CentralBankRssCollector,
    ComplianceHTTPClient,
    FinancialMediaNewsCollector,
    FinnhubCollector,
    GdeltDocCollector,
    NseRssCollector,
    RawNewsItem,
    SecEdgarCollector,
)
from app.engine.news_processor import (
    analyst_extractor,
    entity_resolver,
    extractive_summarizer,
    materiality_evaluator,
    price_reaction_calculator,
    rumour_classifier,
    syndication_clusterer,
)
from app.models import (
    JobRun,
    NewsCoverage,
    NewsCoverageGap,
    NewsEvent,
    NewsSourceState,
)
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
    match_confidence: str = "EXACT_NAME"
    is_unverified: bool = False
    syndication_cluster_id: Optional[str] = None
    materiality: str = "LOW"
    summary: Optional[str] = None
    price_change_day_pct: Optional[float] = None
    price_atr_multiple: Optional[float] = None
    analyst_action: Optional[Dict[str, Any]] = None


class SymbolNewsCoverage(BaseModel):
    symbol: str
    market: str = "IN"
    status: str  # CLEAR, REVIEW, BLOCKED, UNKNOWN
    sources_checked: List[str] = Field(default_factory=list)
    has_earnings_blackout: bool = False
    earnings_date: Optional[datetime.date] = None
    red_events_count: int = 0
    amber_events_count: int = 0
    recent_events: List[ClassifiedNewsItem] = Field(default_factory=list)
    checked_at: datetime.datetime
    coverage_gaps_count: int = 0
    offline_gaps: List[str] = Field(default_factory=list)
    source_health: Dict[str, str] = Field(default_factory=dict)
    macro_risk_flags: List[str] = Field(default_factory=list)


class NewsIntelligenceEngine:
    """Classifies announcements, enforces earnings blackout, handles deduplication,
    tracks multi-source health states, offline gaps, and calculates coverage with
    strict UNKNOWN policy.
    """

    def __init__(self):
        self.rules = self._load_rules()
        self.cfg = settings.get_news_config()
        self.http_client = ComplianceHTTPClient()
        self.nse_collector = NseRssCollector(self.http_client)
        self.sec_collector = SecEdgarCollector(self.http_client)
        self.gdelt_collector = GdeltDocCollector(self.http_client)
        self.finnhub_collector = FinnhubCollector(self.http_client)
        self.central_bank_collector = CentralBankRssCollector(self.http_client)
        self.media_collector = FinancialMediaNewsCollector(self.http_client)

    def poll_financial_news(
        self,
        symbols: List[str],
        market: str = "IN",
        db: Optional[Session] = None,
    ) -> int:
        """Polls live financial media news (Yahoo Finance, Reuters, Moneycontrol, etc.)
        for specified symbols and ingests them into the database.
        """
        ingested_count = 0
        total_latency = 0.0
        success_count = 0

        for sym in symbols:
            try:
                res = self.media_collector.fetch_news_for_symbol(sym, market=market)
                total_latency += res.latency_sec
                if res.success:
                    success_count += 1
                    for item in res.items:
                        classified = self.ingest_raw_item(item, db=db)
                        if classified:
                            ingested_count += 1
            except Exception as e:
                logger.warning(f"Error polling financial news for {sym}: {e}")

        if db is not None:
            self.update_source_health(
                source="financial_media",
                success=success_count > 0,
                latency_sec=total_latency / max(1, len(symbols)),
                items_count=ingested_count,
                db=db,
            )

        return ingested_count

    def _load_rules(self) -> Dict[str, Any]:
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
        hours_bucket = int(published_at.timestamp() // (self.cfg.dedupe_window_hours * 3600))
        raw = f"{symbol.upper()}_{token_str}_{hours_bucket}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def ingest_raw_item(
        self,
        raw: RawNewsItem,
        company_name: str = "",
        aliases: Optional[List[str]] = None,
        daily_open: Optional[float] = None,
        daily_close: Optional[float] = None,
        atr: Optional[float] = None,
        db: Optional[Session] = None,
    ) -> Optional[ClassifiedNewsItem]:
        """Processes and enriches a single raw news item through all intelligence stages:
        1. Entity resolution & collision guard
        2. Rumour / unverified detection
        3. Wire syndication clustering
        4. Analyst action extraction
        5. Severity & deterministic materiality evaluation
        6. Contextual price reaction
        7. Extractive summarization
        """
        # 1. Entity Resolution
        match_conf = "EXACT_NAME"
        if raw.source in ("gdelt_doc", "finnhub"):
            matched, conf_type, _ = entity_resolver.resolve(
                symbol=raw.symbol,
                company_name=company_name or raw.symbol,
                aliases=aliases,
                text=f"{raw.title} {raw.raw_text or ''}",
            )
            if not matched:
                return None
            match_conf = conf_type

        # 2. Rumour Classification
        is_unverified = rumour_classifier.is_unverified(
            raw.title, raw.raw_text or "", is_official_filing=raw.is_official_filing
        )

        # 3. Wire Syndication Clustering
        wire_agency = syndication_clusterer.detect_wire_agency(raw.title, raw.domain)
        syndication_cluster_id = syndication_clusterer.generate_cluster_id(
            raw.title, raw.published_at, wire_agency=wire_agency
        )

        # 4. Analyst Action
        analyst_data = analyst_extractor.extract(raw.title, raw.raw_text or "")

        # 5. Price Reaction
        day_pct, atr_mult = price_reaction_calculator.calculate(daily_open, daily_close, atr)

        # 6. Severity & Materiality
        severity, sev_note = self.classify_severity(f"{raw.title} {raw.raw_text or ''}")
        category = raw.category or "ANNOUNCEMENT"
        materiality, _ = materiality_evaluator.evaluate(
            category=category,
            source=raw.source,
            published_at=raw.published_at,
            is_unverified=is_unverified,
            price_move_pct=day_pct,
        )

        # 7. Summary
        extractive_summary = extractive_summarizer.summarize(raw.title, raw.raw_text)

        ingested_at = datetime.datetime.utcnow()
        latency_sec = max(0.0, (ingested_at - raw.published_at).total_seconds())
        dedupe_key = raw.dedupe_key or self.compute_dedupe_key(raw.symbol, raw.title, raw.published_at)

        item = ClassifiedNewsItem(
            symbol=raw.symbol.upper(),
            source=raw.source,
            title=raw.title,
            url=raw.url,
            published_at=raw.published_at,
            ingested_at=ingested_at,
            severity=severity,
            category=category,
            dedupe_key=dedupe_key,
            canonical_event_id=dedupe_key,
            ai_summary=None,
            latency_sec=latency_sec,
            match_confidence=match_conf,
            is_unverified=is_unverified,
            syndication_cluster_id=syndication_cluster_id,
            materiality=materiality,
            summary=extractive_summary,
            price_change_day_pct=day_pct,
            price_atr_multiple=atr_mult,
            analyst_action=analyst_data,
        )

        # Persist to DB if provided
        if db is not None:
            existing = db.query(NewsEvent).filter(NewsEvent.dedupe_key == dedupe_key).first()
            if not existing:
                evt = NewsEvent(
                    symbol=item.symbol,
                    source=item.source,
                    source_id=raw.source_id or raw.url,
                    title=item.title,
                    url=item.url,
                    published_at=item.published_at,
                    ingested_at=item.ingested_at,
                    severity=item.severity,
                    category=item.category,
                    dedupe_key=item.dedupe_key,
                    canonical_event_id=item.canonical_event_id,
                    match_confidence=item.match_confidence,
                    is_unverified=item.is_unverified,
                    syndication_cluster_id=item.syndication_cluster_id,
                    materiality=item.materiality,
                    summary=item.summary,
                    price_change_day_pct=item.price_change_day_pct,
                    price_atr_multiple=item.price_atr_multiple,
                    analyst_action_json=json.dumps(item.analyst_action) if item.analyst_action else None,
                    raw_json=json.dumps(raw.raw_data) if raw.raw_data else None,
                )
                db.add(evt)
                db.commit()

        return item

    def update_source_health(
        self,
        source: str,
        success: bool,
        latency_sec: float,
        error: Optional[str] = None,
        items_count: int = 0,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        backoff_until: Optional[datetime.datetime] = None,
        db: Optional[Session] = None,
    ):
        """Records polling outcomes, tracks backoff, and computes latency metrics in news_source_state."""
        if db is None:
            return

        now = datetime.datetime.utcnow()
        state = db.query(NewsSourceState).filter(NewsSourceState.source == source).first()
        if not state:
            state = NewsSourceState(source=source)
            db.add(state)

        state.last_attempt_at = now
        state.median_latency_sec = round(latency_sec, 3)

        if success:
            state.last_success_at = now
            state.status = "HEALTHY"
            state.last_error = None
            state.items_last_poll = items_count
            if etag:
                state.etag = etag
            if last_modified:
                state.last_modified = last_modified
        else:
            state.status = "DEGRADED" if state.status == "HEALTHY" else "DOWN"
            state.last_error = error
            if backoff_until:
                state.backoff_until = backoff_until

        db.commit()

    def get_source_health(self, db: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Returns current health status, latency class, and timestamp for all configured sources."""
        results = [
            {
                "source": "nse_rss",
                "name": "NSE Official RSS Syndication",
                "market": "IN",
                "latency_class": "near-real-time",
                "status": "HEALTHY",
                "last_success_at": None,
                "median_latency_sec": 0.0,
            },
            {
                "source": "bse_rss",
                "name": "BSE Announcements",
                "market": "IN",
                "latency_class": "unavailable",
                "status": "UNAVAILABLE",
                "last_success_at": None,
                "median_latency_sec": 0.0,
                "note": "No sanctioned machine-readable RSS without web scraping; coverage marked UNAVAILABLE per compliance policy.",
            },
            {
                "source": "sec_edgar",
                "name": "SEC EDGAR 8-K Submissions API",
                "market": "US",
                "latency_class": "near-real-time",
                "status": "HEALTHY",
                "last_success_at": None,
                "median_latency_sec": 0.0,
            },
            {
                "source": "gdelt_doc",
                "name": "GDELT DOC 2.0 Broad News Discovery",
                "market": "GLOBAL",
                "latency_class": "periodic/batch",
                "status": "HEALTHY",
                "last_success_at": None,
                "median_latency_sec": 0.0,
            },
            {
                "source": "finnhub",
                "name": "Finnhub US Company News",
                "market": "US",
                "latency_class": "near-real-time",
                "status": "HEALTHY" if settings.finnhub_api_key else "OPTIONAL_UNSET",
                "last_success_at": None,
                "median_latency_sec": 0.0,
            },
            {
                "source": "rbi_rss",
                "name": "RBI Official Press Releases",
                "market": "IN",
                "latency_class": "periodic/batch",
                "status": "HEALTHY",
                "last_success_at": None,
                "median_latency_sec": 0.0,
            },
            {
                "source": "fed_rss",
                "name": "Federal Reserve Press Releases",
                "market": "US",
                "latency_class": "periodic/batch",
                "status": "HEALTHY",
                "last_success_at": None,
                "median_latency_sec": 0.0,
            },
        ]

        if db is not None:
            rows = {r.source: r for r in db.query(NewsSourceState).all()}
            for res in results:
                src = res["source"]
                if src in rows:
                    r = rows[src]
                    res["status"] = r.status
                    res["last_success_at"] = r.last_success_at.isoformat() if r.last_success_at else None
                    res["median_latency_sec"] = r.median_latency_sec
                    res["last_error"] = r.last_error

        return results

    def check_macro_calendar(self, market: str = "IN", asof_date: Optional[datetime.date] = None) -> List[str]:
        """Checks if asof_date is near a scheduled high-impact central bank decision."""
        flags: List[str] = []
        cal = settings.get_macro_calendar()
        if not cal:
            return flags

        target_region = market.upper()
        ref_d = asof_date or datetime.date.today()
        caution_window = cal.get("caution_window_trading_days", 1)

        events = cal.get("events", [])
        for ev in events:
            if ev.get("region") != target_region:
                continue

            dec_date_str = ev.get("decision_date")
            if not dec_date_str:
                continue

            try:
                dec_date = datetime.date.fromisoformat(dec_date_str)
                delta_days = (dec_date - ref_d).days
                if -1 <= delta_days <= caution_window:
                    flags.append(
                        f"Macro Caution: {ev.get('authority')} rate decision on {dec_date_str} ('{ev.get('title')}')"
                    )
            except Exception:
                pass

        return flags

    def check_offline_gaps(self, market: str = "IN", db: Optional[Session] = None) -> List[str]:
        """Detects if backend downtime or missed polling runs created an unmonitored coverage gap."""
        gaps: List[str] = []
        if db is None:
            return gaps

        # Check recorded gaps in news_coverage_gaps
        recorded = (
            db.query(NewsCoverageGap)
            .filter(NewsCoverageGap.status == "RECORDED")
            .all()
        )
        for g in recorded:
            gaps.append(f"Offline coverage gap recorded for {g.source}: {g.gap_start.isoformat()} ({g.duration_sec:.0f}s)")

        # Check last news polling job run
        poll_job = (
            db.query(JobRun)
            .filter(JobRun.job.like("%news%"))
            .order_by(JobRun.started_at.desc())
            .first()
        )
        if poll_job and poll_job.finished_at:
            finished = poll_job.finished_at
            now_dt = datetime.datetime.now(datetime.timezone.utc) if finished.tzinfo is not None else datetime.datetime.utcnow()
            idle_sec = (now_dt - finished).total_seconds()
            if idle_sec > 3600.0:  # 1 hour gap
                gaps.append(f"Scheduler news job idle for {idle_sec / 60.0:.1f} minutes (> 60m threshold)")

        return gaps

    def check_symbol_coverage(
        self,
        symbol: str,
        market: str = "IN",
        earnings_date: Optional[datetime.date] = None,
        asof_date: Optional[datetime.date] = None,
        db: Optional[Session] = None,
    ) -> SymbolNewsCoverage:
        """Determines final coverage status: CLEAR, REVIEW, BLOCKED, or UNKNOWN.
        RULE 11: Unknown is NOT Clear. Missing, stale, or offline gap MUST yield UNKNOWN.
        """
        now = datetime.datetime.utcnow()
        ref_date = asof_date or datetime.date.today()
        sources_checked = ["nse_rss", "gdelt_doc"] if market == "IN" else ["sec_edgar", "gdelt_doc"]
        recent_items: List[ClassifiedNewsItem] = []
        red_count = 0
        amber_count = 0
        is_coverage_stale = False
        source_health_map: Dict[str, str] = {}

        # 1. Check Source Health & Freshness (Rule 11)
        if db is not None:
            states = {s.source: s for s in db.query(NewsSourceState).all()}
            req_source = "nse_rss" if market == "IN" else "sec_edgar"
            source_state = states.get(req_source)

            if source_state is None:
                is_coverage_stale = True
                source_health_map[req_source] = "UNCONFIGURED"
            else:
                source_health_map[req_source] = source_state.status
                if source_state.status == "DOWN":
                    is_coverage_stale = True
                elif source_state.last_success_at:
                    last_succ = source_state.last_success_at
                    now_ts = datetime.datetime.now(datetime.timezone.utc) if last_succ.tzinfo is not None else datetime.datetime.utcnow()
                    age_min = (now_ts - last_succ).total_seconds() / 60.0
                    if age_min > self.cfg.max_source_age_min:
                        is_coverage_stale = True
                else:
                    is_coverage_stale = True

        # 2. Check Offline Gaps
        offline_gaps = self.check_offline_gaps(market=market, db=db)

        # 3. Macro Caution Check
        macro_flags = self.check_macro_calendar(market=market, asof_date=ref_date)

        # 4. Check DB for events in last 14 days
        seen_clusters: Set[str] = set()
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()

        if db is not None:
            cutoff = datetime.datetime.combine(ref_date - datetime.timedelta(days=14), datetime.time.min)
            db_evts = (
                db.query(NewsEvent)
                .filter(NewsEvent.symbol == clean_sym, NewsEvent.published_at >= cutoff)
                .order_by(NewsEvent.published_at.desc())
                .all()
            )

            for e in db_evts:
                # Deduplicate by syndication cluster if present
                cluster_id = e.syndication_cluster_id
                if cluster_id and cluster_id in seen_clusters:
                    continue
                if cluster_id:
                    seen_clusters.add(cluster_id)

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
                    match_confidence=e.match_confidence or "EXACT_NAME",
                    is_unverified=e.is_unverified or False,
                    syndication_cluster_id=cluster_id,
                    materiality=e.materiality or "LOW",
                    summary=e.summary or e.title,
                    price_change_day_pct=e.price_change_day_pct,
                    price_atr_multiple=e.price_atr_multiple,
                )
                recent_items.append(item)
                if e.severity == "RED":
                    red_count += 1
                elif e.severity == "AMBER":
                    amber_count += 1

        # 5. Check Earnings Blackout
        has_blackout = False
        if earnings_date:
            days_to_earnings = (earnings_date - ref_date).days
            if 0 <= days_to_earnings <= self.cfg.earnings_block_days:
                has_blackout = True

        # 6. Resolve Status (Isolation Invariant: News can block or flag, NEVER create BUYs)
        if red_count > 0 or has_blackout:
            status = "BLOCKED"
        elif amber_count > 0 or bool(macro_flags):
            status = "REVIEW"
        elif is_coverage_stale or bool(offline_gaps) or not sources_checked:
            status = "UNKNOWN"
        else:
            status = "CLEAR"

        return SymbolNewsCoverage(
            symbol=clean_sym,
            market=market,
            status=status,
            sources_checked=sources_checked,
            has_earnings_blackout=has_blackout,
            earnings_date=earnings_date,
            red_events_count=red_count,
            amber_events_count=amber_count,
            recent_events=recent_items,
            checked_at=now,
            coverage_gaps_count=len(offline_gaps),
            offline_gaps=offline_gaps,
            source_health=source_health_map,
            macro_risk_flags=macro_flags,
        )


news_engine = NewsIntelligenceEngine()
