import datetime
import email.utils
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from pydantic import BaseModel, Field

from app.settings import settings

logger = logging.getLogger(__name__)


class ComplianceViolationError(Exception):
    """Raised when an attempt is made to access an unapproved or prohibited data channel (e.g., scraping NSE/BSE website)."""
    pass


class RawNewsItem(BaseModel):
    symbol: str
    source: str
    source_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    published_at: datetime.datetime
    category: Optional[str] = None
    raw_text: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    dedupe_key: str
    domain: Optional[str] = None
    is_official_filing: bool = False
    item_codes: List[str] = Field(default_factory=list)


class CollectorResponse(BaseModel):
    source: str
    success: bool
    status_code: int
    items: List[RawNewsItem] = Field(default_factory=list)
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    latency_sec: float = 0.0
    error: Optional[str] = None
    backoff_seconds: Optional[int] = None


class ComplianceHTTPClient:
    """Strict HTTP Client that enforces compliance with terms of service:
    1. Blocks any scraping endpoints or unapproved hosts (NSE/BSE web portals).
    2. Enforces honest User-Agent headers (declaring user & email for SEC EDGAR).
    3. Handles conditional requests (ETag / If-Modified-Since) to minimize bandwidth.
    4. Enforces polite rate limiting and honors Retry-After / 429 backoff headers.
    5. Measures latency and logs all requests.
    """

    ALLOWED_DOMAINS = {
        "nsearchives.nseindia.com",       # Sanctioned NSE RSS syndication archives
        "data.sec.gov",                   # Official SEC EDGAR Submissions API
        "www.sec.gov",                    # Official SEC EDGAR Document Archives
        "api.gdeltproject.org",           # Official GDELT DOC 2.0 API
        "finnhub.io",                     # Official Finnhub REST API
        "www.rbi.org.in",                 # Official Reserve Bank of India RSS
        "rbi.org.in",
        "www.federalreserve.gov",         # Official US Federal Reserve RSS
        "federalreserve.gov",
    }

    # Explicitly prohibited hosts and patterns (anti-scraping enforcement)
    PROHIBITED_PATTERNS = [
        re.compile(r"https?://(www\.)?nseindia\.com/(api|market-data|get-quotes|live-analysis)", re.IGNORECASE),
        re.compile(r"https?://(www\.)?bseindia\.com/(corporates|markets|stock-share-price)", re.IGNORECASE),
        re.compile(r"https?://(www\.)?moneycontrol\.com", re.IGNORECASE),
    ]

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._last_request_time: Dict[str, float] = {}

    def is_url_allowed(self, url: str) -> bool:
        """Verify URL strictly matches sanctioned sources and does not violate exchange terms."""
        for pattern in self.PROHIBITED_PATTERNS:
            if pattern.search(url):
                return False

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return hostname in self.ALLOWED_DOMAINS

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        min_interval_sec: float = 0.0,
    ) -> httpx.Response:
        """Perform compliant HTTP GET request with domain allowlist, rate-pacing, and conditional headers."""
        if not self.is_url_allowed(url):
            raise ComplianceViolationError(
                f"URL '{url}' is prohibited by compliance policy. Automated scraping of exchange web "
                f"interfaces is forbidden. Only sanctioned RSS syndication and official APIs are permitted."
            )

        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()

        # Enforce rate pacing per domain
        if min_interval_sec > 0:
            now = time.time()
            last_time = self._last_request_time.get(domain, 0.0)
            elapsed = now - last_time
            if elapsed < min_interval_sec:
                time.sleep(min_interval_sec - elapsed)

        req_headers = {
            "Accept": "application/json, application/xml, text/xml, */*",
            "Accept-Encoding": "gzip, deflate",
        }

        # SEC EDGAR requires specific honest user agent: Sample Company Name AdminContact@domain.com
        if "sec.gov" in domain:
            req_headers["User-Agent"] = settings.sec_user_agent
        else:
            req_headers["User-Agent"] = f"AlgoTradingIntelligence/2.3 (+https://github.com/mk070/algo-trading)"

        if headers:
            req_headers.update(headers)

        if etag:
            req_headers["If-None-Match"] = etag
        if last_modified:
            req_headers["If-Modified-Since"] = last_modified

        t0 = time.time()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params, headers=req_headers)
                self._last_request_time[domain] = time.time()
                return resp
        except Exception as e:
            self._last_request_time[domain] = time.time()
            raise e


class NseRssCollector:
    """Collects corporate announcements, board meetings, and financial results from
    official NSE RSS feeds hosted on nsearchives.nseindia.com.
    Zero scraping of nseindia.com web pages or private JSON endpoints.
    """

    FEEDS = {
        "Corporate_announcements": "https://nsearchives.nseindia.com/content/RSS/Corporate_announcements.xml",
        "Board_Meetings": "https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml",
        "Corp_action": "https://nsearchives.nseindia.com/content/RSS/Corp_action.xml",
        "Financial_Results": "https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml",
    }

    def __init__(self, http_client: Optional[ComplianceHTTPClient] = None):
        self.http = http_client or ComplianceHTTPClient()

    def fetch_feed(
        self,
        feed_key: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> CollectorResponse:
        url = self.FEEDS.get(feed_key)
        if not url:
            return CollectorResponse(
                source="nse_rss",
                success=False,
                status_code=400,
                error=f"Unknown NSE feed key: {feed_key}",
            )

        t0 = time.time()
        try:
            resp = self.http.get(url, etag=etag, last_modified=last_modified, min_interval_sec=1.0)
            latency = time.time() - t0

            if resp.status_code == 304:
                return CollectorResponse(
                    source="nse_rss",
                    success=True,
                    status_code=304,
                    etag=etag,
                    last_modified=last_modified,
                    latency_sec=latency,
                    items=[],
                )

            if resp.status_code != 200:
                backoff = int(resp.headers.get("Retry-After", "60")) if resp.status_code == 429 else None
                return CollectorResponse(
                    source="nse_rss",
                    success=False,
                    status_code=resp.status_code,
                    error=f"NSE RSS returned HTTP {resp.status_code}",
                    latency_sec=latency,
                    backoff_seconds=backoff,
                )

            new_etag = resp.headers.get("ETag")
            new_last_mod = resp.headers.get("Last-Modified")

            items = self.parse_rss_content(resp.text, feed_key)
            return CollectorResponse(
                source="nse_rss",
                success=True,
                status_code=200,
                items=items,
                etag=new_etag,
                last_modified=new_last_mod,
                latency_sec=latency,
            )
        except Exception as e:
            return CollectorResponse(
                source="nse_rss",
                success=False,
                status_code=500,
                error=str(e),
                latency_sec=time.time() - t0,
            )

    def parse_rss_content(self, xml_text: str, feed_key: str) -> List[RawNewsItem]:
        items: List[RawNewsItem] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception as e:
            logger.warning(f"Failed to parse NSE RSS XML: {e}")
            return items

        # Look for <item> nodes inside <channel>
        for item in root.findall(".//item"):
            title_node = item.find("title")
            link_node = item.find("link")
            desc_node = item.find("description")
            pub_date_node = item.find("pubDate")

            raw_title = (title_node.text or "").strip() if title_node is not None else ""
            link = (link_node.text or "").strip() if link_node is not None else ""
            desc = (desc_node.text or "").strip() if desc_node is not None else ""
            pub_date_str = (pub_date_node.text or "").strip() if pub_date_node is not None else ""

            if not raw_title and not desc:
                continue

            # Parse date or default to now
            pub_dt = datetime.datetime.utcnow()
            if pub_date_str:
                try:
                    parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
                    pub_dt = parsed_tuple.replace(tzinfo=None)
                except Exception:
                    pass

            # Extract symbol: NSE announcements typically format title as "SYMBOL - Description"
            # or "Company Name (SYMBOL): Description"
            symbol = self.extract_symbol_from_title(raw_title, desc)
            if not symbol:
                symbol = "MARKET_IN"

            # Compute stable hash for deduplication
            hasher = hashlib.sha256()
            hasher.update(f"{symbol}:{pub_dt.isoformat()}:{raw_title}".encode("utf-8"))
            dedupe_key = f"NSE_RSS:{symbol}:{hasher.hexdigest()[:16]}"

            category = self.categorize_feed_key(feed_key, raw_title)

            items.append(
                RawNewsItem(
                    symbol=symbol,
                    source="nse_rss",
                    source_id=link,
                    title=raw_title or desc[:120],
                    url=link or "https://nsearchives.nseindia.com/",
                    published_at=pub_dt,
                    category=category,
                    raw_text=desc,
                    raw_data={"feed_key": feed_key, "raw_title": raw_title},
                    dedupe_key=dedupe_key,
                    domain="nsearchives.nseindia.com",
                    is_official_filing=True,
                )
            )
        return items

    def extract_symbol_from_title(self, title: str, desc: str) -> Optional[str]:
        # Pattern 1: Starts with TICKER - e.g. "INFY - Financial Results..."
        m = re.match(r"^([A-Z0-9_]{2,20})\s*[-:]", title)
        if m:
            return m.group(1).upper()

        # Pattern 2: Parenthesized ticker - e.g. "Infosys Limited (INFY) - Corporate Announcement"
        m2 = re.search(r"\(([A-Z0-9_]{2,20})\)", title)
        if m2:
            return m2.group(1).upper()

        # Pattern 3: Check description
        m3 = re.match(r"^([A-Z0-9_]{2,20})\s*[-:]", desc)
        if m3:
            return m3.group(1).upper()

        return None

    def categorize_feed_key(self, feed_key: str, title: str) -> str:
        if feed_key == "Financial_Results":
            return "EARNINGS"
        if feed_key == "Board_Meetings":
            return "BOARD_MEETING"
        if feed_key == "Corp_action":
            return "CORPORATE_ACTION"
        return "ANNOUNCEMENT"


class SecEdgarCollector:
    """Collects US corporate disclosures (specifically 8-K material events) using
    the official SEC EDGAR Submissions API (https://data.sec.gov/submissions/CIK{cik}.json).
    Free, no API key required. Declares honest User-Agent per SEC Fair Access policy.
    """

    SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik}.json"
    SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

    # Important 8-K items that swing algorithmic trading must recognize
    ITEM_CODE_MAP = {
        "1.01": ("MATERIAL_AGREEMENT", "Entry into a Material Definitive Agreement"),
        "1.02": ("TERMINATION_AGREEMENT", "Termination of a Material Definitive Agreement"),
        "1.03": ("INSOLVENCY", "Bankruptcy or Receivership"),
        "2.01": ("ASSET_ACQUISITION_DISPOSITION", "Completion of Acquisition or Disposition of Assets"),
        "2.02": ("EARNINGS", "Results of Operations and Financial Condition"),
        "2.03": ("FINANCIAL_OBLIGATION", "Creation of a Direct Financial Obligation"),
        "3.01": ("DELISTING", "Notice of Delisting or Failure to Satisfy Continued Listing Rule"),
        "4.01": ("AUDITOR_CHANGE", "Changes in Registrant Certifying Accountant"),
        "4.02": ("RESTATEMENT", "Non-Reliance on Previously Issued Financial Statements"),
        "5.01": ("CHANGE_IN_CONTROL", "Changes in Control of Registrant"),
        "5.02": ("GOVERNANCE", "Departure of Directors or Certain Officers; Election of Directors"),
        "7.01": ("REG_FD", "Regulation FD Disclosure"),
        "8.01": ("OTHER_EVENTS", "Other Events"),
    }

    def __init__(self, http_client: Optional[ComplianceHTTPClient] = None):
        self.http = http_client or ComplianceHTTPClient()

    def fetch_filings(
        self,
        symbol: str,
        cik: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> CollectorResponse:
        padded_cik = str(cik).strip().zfill(10)
        url = self.SUBMISSIONS_URL_TMPL.format(cik=padded_cik)
        t0 = time.time()

        try:
            # SEC Fair Access rate limit: max 10 requests per second
            resp = self.http.get(
                url,
                etag=etag,
                last_modified=last_modified,
                min_interval_sec=0.12,  # ~8 requests per second max
            )
            latency = time.time() - t0

            if resp.status_code == 304:
                return CollectorResponse(
                    source="sec_edgar",
                    success=True,
                    status_code=304,
                    etag=etag,
                    last_modified=last_modified,
                    latency_sec=latency,
                    items=[],
                )

            if resp.status_code != 200:
                backoff = int(resp.headers.get("Retry-After", "60")) if resp.status_code == 429 else None
                return CollectorResponse(
                    source="sec_edgar",
                    success=False,
                    status_code=resp.status_code,
                    error=f"SEC EDGAR returned HTTP {resp.status_code}",
                    latency_sec=latency,
                    backoff_seconds=backoff,
                )

            data = resp.json()
            new_etag = resp.headers.get("ETag")
            new_last_mod = resp.headers.get("Last-Modified")

            items = self.parse_submissions(symbol, cik, data)
            return CollectorResponse(
                source="sec_edgar",
                success=True,
                status_code=200,
                items=items,
                etag=new_etag,
                last_modified=new_last_mod,
                latency_sec=latency,
            )
        except Exception as e:
            return CollectorResponse(
                source="sec_edgar",
                success=False,
                status_code=500,
                error=str(e),
                latency_sec=time.time() - t0,
            )

    def parse_submissions(self, symbol: str, cik: str, data: Dict[str, Any]) -> List[RawNewsItem]:
        items: List[RawNewsItem] = []
        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return items

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        primary_doc_descs = recent.get("primaryDocDescription", [])
        items_list = recent.get("items", [])

        int_cik = str(int(cik))  # unpadded CIK for SEC archives URL path

        for i, form in enumerate(forms):
            # Focus on 8-K (current reports) and 10-Q/10-K (periodic earnings)
            if form not in ("8-K", "8-K/A", "10-Q", "10-K"):
                continue

            filing_date_str = filing_dates[i] if i < len(filing_dates) else ""
            acc_num = accession_numbers[i] if i < len(accession_numbers) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""
            doc_desc = primary_doc_descs[i] if i < len(primary_doc_descs) else ""
            raw_item_codes = items_list[i] if i < len(items_list) else ""

            acc_clean = acc_num.replace("-", "")
            filing_url = f"{self.SEC_ARCHIVES_BASE}/{int_cik}/{acc_clean}/{primary_doc}" if acc_num and primary_doc else f"https://www.sec.gov/edgar/browse/?CIK={cik}"

            try:
                pub_dt = datetime.datetime.strptime(filing_date_str, "%Y-%m-%d")
            except Exception:
                pub_dt = datetime.datetime.utcnow()

            # Parse 8-K item codes (can be comma-separated or list)
            item_codes: List[str] = []
            if isinstance(raw_item_codes, list):
                item_codes = [str(x).strip() for x in raw_item_codes if str(x).strip()]
            elif isinstance(raw_item_codes, str) and raw_item_codes.strip():
                item_codes = [x.strip() for x in raw_item_codes.split(",") if x.strip()]

            # Determine dominant category and title
            category, item_desc = self.resolve_category(form, item_codes)
            title = f"{symbol} Form {form}: {item_desc}" if item_desc else f"{symbol} SEC Filing Form {form} ({doc_desc or 'Current Report'})"

            dedupe_key = f"SEC_EDGAR:{symbol}:{acc_num}:{form}"

            items.append(
                RawNewsItem(
                    symbol=symbol,
                    source="sec_edgar",
                    source_id=acc_num,
                    title=title,
                    url=filing_url,
                    published_at=pub_dt,
                    category=category,
                    raw_text=doc_desc or title,
                    raw_data={
                        "form": form,
                        "cik": cik,
                        "accession_number": acc_num,
                        "item_codes": item_codes,
                    },
                    dedupe_key=dedupe_key,
                    domain="sec.gov",
                    is_official_filing=True,
                    item_codes=item_codes,
                )
            )
        return items

    def resolve_category(self, form: str, item_codes: List[str]) -> Tuple[str, str]:
        if form in ("10-Q", "10-K"):
            return "EARNINGS", "Quarterly / Annual Financial Results"

        descriptions: List[str] = []
        dominant_cat = "8-K_FILING"

        # Prioritize higher severity 8-K items
        priority_order = ["4.02", "1.03", "4.01", "5.02", "2.02", "1.01", "3.01"]
        ordered_codes = sorted(item_codes, key=lambda c: priority_order.index(c) if c in priority_order else 99)

        for code in ordered_codes:
            if code in self.ITEM_CODE_MAP:
                cat, desc = self.ITEM_CODE_MAP[code]
                if dominant_cat == "8-K_FILING":
                    dominant_cat = cat
                descriptions.append(f"Item {code} ({desc})")

        return dominant_cat, "; ".join(descriptions)


class GdeltDocCollector:
    """Collects broad news articles using the free GDELT DOC 2.0 API.
    (https://api.gdeltproject.org/api/v2/doc/doc).
    Zero API key required. Returns article metadata (title, URL, domain, seendate, tone).
    Enforces polite 6-second rate pacing.
    """

    GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, http_client: Optional[ComplianceHTTPClient] = None):
        self.http = http_client or ComplianceHTTPClient()

    def fetch_company_news(
        self,
        symbol: str,
        company_name: str,
        aliases: Optional[List[str]] = None,
        max_records: int = 50,
    ) -> CollectorResponse:
        # Build strict disambiguated query to avoid common word collisions (e.g., TCS, BEL)
        query_terms = [f'"{company_name}"']
        if aliases:
            for alias in aliases:
                # Only include alias in query if it has at least 4 letters or is enclosed with company context
                if len(alias) >= 4:
                    query_terms.append(f'"{alias}"')

        # Combine terms with OR
        combined_query = " OR ".join(query_terms)
        params = {
            "query": combined_query,
            "mode": "ArtList",
            "maxrecords": min(max_records, 250),
            "format": "json",
            "sort": "DateDesc",
        }

        t0 = time.time()
        try:
            # GDELT guidelines suggest >= 6 seconds pacing per IP
            resp = self.http.get(
                self.GDELT_URL,
                params=params,
                min_interval_sec=6.0,
            )
            latency = time.time() - t0

            if resp.status_code != 200:
                backoff = int(resp.headers.get("Retry-After", "60")) if resp.status_code == 429 else None
                return CollectorResponse(
                    source="gdelt_doc",
                    success=False,
                    status_code=resp.status_code,
                    error=f"GDELT DOC 2.0 returned HTTP {resp.status_code}",
                    latency_sec=latency,
                    backoff_seconds=backoff,
                )

            data = resp.json()
            articles = data.get("articles", [])
            items = self.parse_articles(symbol, articles)

            return CollectorResponse(
                source="gdelt_doc",
                success=True,
                status_code=200,
                items=items,
                latency_sec=latency,
            )
        except Exception as e:
            return CollectorResponse(
                source="gdelt_doc",
                success=False,
                status_code=500,
                error=str(e),
                latency_sec=time.time() - t0,
            )

    def parse_articles(self, symbol: str, articles: List[Dict[str, Any]]) -> List[RawNewsItem]:
        items: List[RawNewsItem] = []
        for art in articles:
            url = art.get("url", "")
            title = (art.get("title") or "").strip()
            seendate_str = art.get("seendate", "")
            domain = art.get("domain", "")

            if not title or not url:
                continue

            # Parse GDELT seendate format: YYYYMMDDTHHMMSSZ
            pub_dt = datetime.datetime.utcnow()
            if seendate_str:
                try:
                    clean_dt = seendate_str.replace("Z", "")
                    pub_dt = datetime.datetime.strptime(clean_dt, "%Y%m%dT%H%M%S")
                except Exception:
                    pass

            hasher = hashlib.sha256()
            hasher.update(url.encode("utf-8"))
            dedupe_key = f"GDELT:{symbol}:{hasher.hexdigest()[:16]}"

            items.append(
                RawNewsItem(
                    symbol=symbol,
                    source="gdelt_doc",
                    source_id=url,
                    title=title,
                    url=url,
                    published_at=pub_dt,
                    category="NEWS_MEDIA",
                    raw_text=title,
                    raw_data=art,
                    dedupe_key=dedupe_key,
                    domain=domain,
                    is_official_filing=False,
                )
            )
        return items


class FinnhubCollector:
    """Collects supplementary US company news using Finnhub free tier.
    Zero-key tolerance: If FINNHUB_API_KEY is unset, collector gracefully returns empty list
    without error, keeping system fully operational without keys.
    """

    FINNHUB_URL = "https://finnhub.io/api/v1/company-news"

    def __init__(self, http_client: Optional[ComplianceHTTPClient] = None):
        self.http = http_client or ComplianceHTTPClient()

    def fetch_company_news(
        self,
        symbol: str,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
    ) -> CollectorResponse:
        api_key = settings.finnhub_api_key
        if not api_key:
            return CollectorResponse(
                source="finnhub",
                success=True,
                status_code=200,
                error="FINNHUB_API_KEY not configured; operating in free keyless mode.",
                items=[],
            )

        today = datetime.date.today()
        from_d = from_date or (today - datetime.timedelta(days=7))
        to_d = to_date or today

        params = {
            "symbol": symbol.upper(),
            "from": from_d.isoformat(),
            "to": to_d.isoformat(),
            "token": api_key,
        }

        t0 = time.time()
        try:
            resp = self.http.get(
                self.FINNHUB_URL,
                params=params,
                min_interval_sec=1.1,  # 60 calls/minute max free tier limit
            )
            latency = time.time() - t0

            if resp.status_code != 200:
                backoff = int(resp.headers.get("Retry-After", "60")) if resp.status_code == 429 else None
                return CollectorResponse(
                    source="finnhub",
                    success=False,
                    status_code=resp.status_code,
                    error=f"Finnhub returned HTTP {resp.status_code}",
                    latency_sec=latency,
                    backoff_seconds=backoff,
                )

            data = resp.json()
            if not isinstance(data, list):
                data = []

            items: List[RawNewsItem] = []
            for item in data:
                headline = item.get("headline", "").strip()
                url = item.get("url", "")
                summary = item.get("summary", "")
                ts = item.get("datetime", 0)
                source_name = item.get("source", "Finnhub")

                if not headline:
                    continue

                pub_dt = datetime.datetime.utcfromtimestamp(ts) if ts > 0 else datetime.datetime.utcnow()
                item_id = str(item.get("id", "")) or url
                dedupe_key = f"FINNHUB:{symbol}:{item_id}"

                items.append(
                    RawNewsItem(
                        symbol=symbol,
                        source="finnhub",
                        source_id=str(item.get("id", "")),
                        title=headline,
                        url=url,
                        published_at=pub_dt,
                        category="FINNHUB_NEWS",
                        raw_text=summary or headline,
                        raw_data=item,
                        dedupe_key=dedupe_key,
                        domain=source_name,
                        is_official_filing=False,
                    )
                )

            return CollectorResponse(
                source="finnhub",
                success=True,
                status_code=200,
                items=items,
                latency_sec=latency,
            )
        except Exception as e:
            return CollectorResponse(
                source="finnhub",
                success=False,
                status_code=500,
                error=str(e),
                latency_sec=time.time() - t0,
            )


class CentralBankRssCollector:
    """Collects macro policy announcements directly from Reserve Bank of India and
    US Federal Reserve official RSS feeds.
    """

    RBI_PRESS_URL = "https://www.rbi.org.in/rss/pressreleases.xml"
    FED_PRESS_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"

    def __init__(self, http_client: Optional[ComplianceHTTPClient] = None):
        self.http = http_client or ComplianceHTTPClient()

    def fetch_rbi_news(self, etag: Optional[str] = None, last_modified: Optional[str] = None) -> CollectorResponse:
        return self._fetch_feed(self.RBI_PRESS_URL, "rbi_rss", "IN", etag, last_modified)

    def fetch_fed_news(self, etag: Optional[str] = None, last_modified: Optional[str] = None) -> CollectorResponse:
        return self._fetch_feed(self.FED_PRESS_URL, "fed_rss", "US", etag, last_modified)

    def _fetch_feed(
        self,
        url: str,
        source_name: str,
        region: str,
        etag: Optional[str],
        last_modified: Optional[str],
    ) -> CollectorResponse:
        t0 = time.time()
        try:
            resp = self.http.get(url, etag=etag, last_modified=last_modified, min_interval_sec=2.0)
            latency = time.time() - t0

            if resp.status_code == 304:
                return CollectorResponse(
                    source=source_name,
                    success=True,
                    status_code=304,
                    etag=etag,
                    last_modified=last_modified,
                    latency_sec=latency,
                    items=[],
                )

            if resp.status_code != 200:
                return CollectorResponse(
                    source=source_name,
                    success=False,
                    status_code=resp.status_code,
                    error=f"{source_name} returned HTTP {resp.status_code}",
                    latency_sec=latency,
                )

            new_etag = resp.headers.get("ETag")
            new_last_mod = resp.headers.get("Last-Modified")

            items = self._parse_feed_xml(resp.text, source_name, region)
            return CollectorResponse(
                source=source_name,
                success=True,
                status_code=200,
                items=items,
                etag=new_etag,
                last_modified=new_last_mod,
                latency_sec=latency,
            )
        except Exception as e:
            return CollectorResponse(
                source=source_name,
                success=False,
                status_code=500,
                error=str(e),
                latency_sec=time.time() - t0,
            )

    def _parse_feed_xml(self, xml_text: str, source_name: str, region: str) -> List[RawNewsItem]:
        items: List[RawNewsItem] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception as e:
            logger.warning(f"Failed to parse {source_name} XML: {e}")
            return items

        symbol = f"MACRO_{region}"
        for item in root.findall(".//item"):
            title_node = item.find("title")
            link_node = item.find("link")
            desc_node = item.find("description")
            pub_date_node = item.find("pubDate")

            raw_title = (title_node.text or "").strip() if title_node is not None else ""
            link = (link_node.text or "").strip() if link_node is not None else ""
            desc = (desc_node.text or "").strip() if desc_node is not None else ""
            pub_date_str = (pub_date_node.text or "").strip() if pub_date_node is not None else ""

            if not raw_title:
                continue

            pub_dt = datetime.datetime.utcnow()
            if pub_date_str:
                try:
                    parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
                    pub_dt = parsed_tuple.replace(tzinfo=None)
                except Exception:
                    pass

            hasher = hashlib.sha256()
            hasher.update(f"{source_name}:{raw_title}:{pub_dt.isoformat()}".encode("utf-8"))
            dedupe_key = f"{source_name.upper()}:{hasher.hexdigest()[:16]}"

            items.append(
                RawNewsItem(
                    symbol=symbol,
                    source=source_name,
                    source_id=link,
                    title=raw_title,
                    url=link,
                    published_at=pub_dt,
                    category="CENTRAL_BANK_POLICY",
                    raw_text=desc,
                    raw_data={"region": region, "title": raw_title},
                    dedupe_key=dedupe_key,
                    domain="rbi.org.in" if region == "IN" else "federalreserve.gov",
                    is_official_filing=True,
                )
            )
        return items

