import datetime
import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class EntityResolver:
    """Disambiguates company mentions to prevent false positives from common word collisions
    (e.g., TCS = Tax Collected at Source, BEL = Bel Air / Belgium, IT = Information Technology).
    """

    KNOWN_COLLISION_TICKERS = {
        "TCS": ["tax collected at source", "tax collection", "treasury", "tcs rate"],
        "BEL": ["belgium", "bel air", "bel canto", "bel-air"],
        "IT": ["information technology", "income tax"],
        "OIL": ["crude oil", "oil prices", "oil spills", "edible oil"],
        "COAL": ["coal production", "coal prices", "coking coal"],
        "POWER": ["power cut", "power outage", "solar power", "hydropower"],
        "GAIL": ["gail storm", "gale"],
        "SAIL": ["set sail", "sailing", "boat"],
    }

    def resolve(
        self,
        symbol: str,
        company_name: str,
        aliases: Optional[List[str]] = None,
        text: str = "",
    ) -> Tuple[bool, str, float]:
        """Returns: (is_match, match_confidence, numeric_score)
        match_confidence: "EXACT_NAME" (1.0), "ALIAS" (0.85), "TICKER_ONLY" (0.4-0.6)
        """
        if not text:
            return False, "NO_MATCH", 0.0

        clean_text = text.lower()
        clean_name = company_name.lower().strip()
        stripped_name = re.sub(r"\b(limited|ltd|inc|corp|corporation|plc)\b", "", clean_name).strip()

        # 1. Check exact official company name (full or stripped of legal entity suffixes)
        if (clean_name and clean_name in clean_text) or (stripped_name and len(stripped_name) >= 4 and stripped_name in clean_text):
            return True, "EXACT_NAME", 1.0

        # Collision guard check for known collision tickers
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper().strip()
        if clean_sym in self.KNOWN_COLLISION_TICKERS:
            for p_ctx in self.KNOWN_COLLISION_TICKERS[clean_sym]:
                if p_ctx in clean_text:
                    return False, "COLLISION_DISCARD", 0.0

        # 2. Check aliases / subsidiaries
        if aliases:
            for alias in aliases:
                clean_alias = alias.lower().strip()
                if len(clean_alias) >= 3 and clean_alias in clean_text:
                    return True, "ALIAS", 0.85

        # 3. Check ticker symbol with boundary
        sym_pattern = re.compile(rf"\b{re.escape(clean_sym)}\b")

        if sym_pattern.search(text):
            if clean_sym in self.KNOWN_COLLISION_TICKERS:
                return True, "TICKER_ONLY", 0.40

            confidence = 0.60 if len(clean_sym) <= 3 else 0.75
            return True, "TICKER_ONLY", confidence

        return False, "NO_MATCH", 0.0


class WireSyndicationClusterer:
    """Clusters syndicated wire agency stories across multiple publishers into ONE report.
    Recognizes wire attributions: Reuters, PTI, ANI, IANS, Bloomberg, PR Newswire.
    Uses Jaccard token overlap within 24h date bucket.
    """

    WIRE_SIGNATURES = [
        "reuters",
        "pti",
        "press trust of india",
        "ani",
        "asian news international",
        "ians",
        "bloomberg",
        "pr newswire",
        "business wire",
    ]

    STOP_WORDS = {
        "a", "an", "the", "in", "on", "at", "by", "for", "with", "about",
        "against", "between", "into", "through", "during", "before", "after",
        "above", "below", "to", "from", "up", "down", "of", "and", "or",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "shares", "stock", "stocks", "market", "markets",
    }

    def __init__(self):
        self._clusters: Dict[str, List[Tuple[Set[str], str]]] = {}

    def detect_wire_agency(self, text: str, domain: Optional[str] = None) -> Optional[str]:
        clean_text = text.lower() if text else ""
        domain_str = domain.lower() if domain else ""

        for sig in self.WIRE_SIGNATURES:
            if sig in domain_str or f"({sig})" in clean_text or f"/{sig}/" in clean_text or f"source: {sig}" in clean_text or f"by {sig}" in clean_text or f": {sig}" in clean_text:
                return sig.upper().replace(" ", "_")
        return None

    def generate_cluster_id(
        self,
        title: str,
        published_at: datetime.datetime,
        wire_agency: Optional[str] = None,
    ) -> str:
        """Generates or resolves a stable syndication cluster ID based on normalized significant words
        and 24-hour date window.
        """
        words = set(re.findall(r"[a-z0-9]+", title.lower()))
        sig_words = {w for w in words if w not in self.STOP_WORDS and len(w) > 2}

        date_bucket = published_at.strftime("%Y%m%d")
        agency_prefix = wire_agency or "IND"
        bucket_key = f"{agency_prefix}_{date_bucket}"

        existing_list = self._clusters.setdefault(bucket_key, [])
        for existing_tokens, existing_id in existing_list:
            if not existing_tokens or not sig_words:
                continue
            intersection = len(sig_words & existing_tokens)
            union = len(sig_words | existing_tokens)
            jaccard = intersection / union if union > 0 else 0.0
            if jaccard >= 0.40:  # Syndication overlap threshold
                return existing_id

        # New cluster
        sorted_tokens = sorted(list(sig_words))
        hasher = hashlib.sha256("-".join(sorted_tokens).encode("utf-8")).hexdigest()[:12]
        new_id = f"CLUSTER_{agency_prefix}_{date_bucket}_{hasher}"
        existing_list.append((sig_words, new_id))
        return new_id


class RumourClassifier:
    """Detects speculative, unverified, or rumour headlines using hedged language patterns.
    Official exchange or SEC filings are never marked as rumours.
    """

    HEDGED_PATTERNS = [
        re.compile(r"\b(sources\s+said|sources\s+say|people\s+familiar|according\s+to\s+sources)\b", re.IGNORECASE),
        re.compile(r"\b(reportedly|speculation|in\s+talks\s+to|may\s+consider|rumoured|unconfirmed)\b", re.IGNORECASE),
        re.compile(r"\b(sources\s+familiar\s+with|could\s+acquire|weighing\s+(?:bid|sale|options))\b", re.IGNORECASE),
        re.compile(r"\b(likely\s+to|is\s+said\s+to|mulls|considering\s+a)\b", re.IGNORECASE),
    ]

    def is_unverified(self, title: str, text: str = "", is_official_filing: bool = False) -> bool:
        if is_official_filing:
            return False

        full_content = f"{title} {text}"
        for pat in self.HEDGED_PATTERNS:
            if pat.search(full_content):
                return True
        return False


class AnalystActionExtractor:
    """Extracts brokerage rating and target price changes from news text.
    STRICT RULE: Missing fields remain strictly None (null). Never guess or synthesize.
    """

    BROKERAGES = [
        "Morgan Stanley", "Goldman Sachs", "Jefferies", "JPMorgan", "Kotak",
        "ICICI Securities", "Motilal Oswal", "Nomura", "CLSA", "UBS",
        "Macquarie", "Bernstein", "HSBC", "Citi", "Citigroup", "BofA",
        "Bank of America", "Barclays", "Axis Capital", "Nuvama", "HDFC Securities",
        "Sharekhan", "Edelweiss", "Anand Rathi", "Emkay",
    ]

    ACTIONS = {
        "upgrade": "UPGRADE",
        "upgrades": "UPGRADE",
        "upgraded": "UPGRADE",
        "downgrade": "DOWNGRADE",
        "downgrades": "DOWNGRADE",
        "downgraded": "DOWNGRADE",
        "initiate": "INITIATE",
        "initiates": "INITIATE",
        "initiated": "INITIATE",
        "maintain": "MAINTAIN",
        "maintains": "MAINTAIN",
        "reiterate": "REITERATE",
        "reiterates": "REITERATE",
    }

    RATINGS = [
        "BUY", "OUTPERFORM", "OVERWEIGHT", "ADD", "ACCUMULATE",
        "HOLD", "NEUTRAL", "EQUAL-WEIGHT",
        "SELL", "UNDERPERFORM", "UNDERWEIGHT", "REDUCE",
    ]

    def extract(self, title: str, text: str = "") -> Optional[Dict[str, Any]]:
        full_content = f"{title} {text}"
        clean_content = full_content.strip()

        # 1. Identify brokerage
        found_brokerage = None
        for b in self.BROKERAGES:
            if re.search(rf"\b{re.escape(b)}\b", clean_content, re.IGNORECASE):
                found_brokerage = b
                break

        # 2. Identify action
        found_action = None
        for word, act in self.ACTIONS.items():
            if re.search(rf"\b{word}\b", clean_content, re.IGNORECASE):
                found_action = act
                break

        # If neither brokerage nor analyst action keyword found, this is not an analyst report
        if not found_brokerage and not found_action:
            return None

        # 3. Identify Ratings (old -> new or standalone new)
        new_rating = None
        old_rating = None

        # Pattern: from [OLD] to [NEW]
        rating_change_match = re.search(
            r"\bfrom\s+([A-Za-z-]+)\s+to\s+([A-Za-z-]+)\b", clean_content, re.IGNORECASE
        )
        if rating_change_match:
            r1 = rating_change_match.group(1).upper()
            r2 = rating_change_match.group(2).upper()
            if r1 in self.RATINGS and r2 in self.RATINGS:
                old_rating = r1
                new_rating = r2

        if not new_rating:
            # Standalone rating e.g., 'rating to BUY' or 'maintains BUY'
            for r in self.RATINGS:
                if re.search(rf"\b(?:rating\s+(?:to\s+)?|maintains\s+|upgrades\s+to\s+|downgrades\s+to\s+){r}\b", clean_content, re.IGNORECASE):
                    new_rating = r
                    break

        # 4. Identify Target Prices (old -> new or standalone new)
        new_target = None
        old_target = None

        # Pattern: target price from X to Y
        target_change_match = re.search(
            r"target\s+(?:price\s+)?(?:from\s+)?(?:rs\.?|inr|\$)?\s*([0-9]+(?:\.[0-9]+)?)\s+to\s+(?:rs\.?|inr|\$)?\s*([0-9]+(?:\.[0-9]+)?)",
            clean_content,
            re.IGNORECASE,
        )
        if target_change_match:
            try:
                old_target = float(target_change_match.group(1))
                new_target = float(target_change_match.group(2))
            except Exception:
                pass

        if new_target is None:
            # Standalone target: target Rs. 3500 / target price of $210
            target_match = re.search(
                r"target\s+(?:price\s+)?(?:of|to|raised to|cut to|at)?\s*(?:rs\.?|inr|\$)?\s*([0-9]+(?:\.[0-9]+)?)",
                clean_content,
                re.IGNORECASE,
            )
            if target_match:
                try:
                    new_target = float(target_match.group(1))
                except Exception:
                    pass

        return {
            "brokerage": found_brokerage,
            "action": found_action,
            "old_rating": old_rating,
            "new_rating": new_rating,
            "old_target": old_target,
            "new_target": new_target,
        }


class MaterialityEvaluator:
    """Calculates deterministic materiality score based on category weight, source authority,
    recency decay, price reaction, and verified status.
    Formula: Materiality = CategoryWeight * SourceAuthority * RecencyDecay * PriceMultiplier
    """

    CATEGORY_WEIGHTS = {
        "FRAUD": 1.0,
        "INSOLVENCY": 1.0,
        "RESTATEMENT": 1.0,
        "DELISTING": 1.0,
        "AUDITOR_CHANGE": 0.9,
        "EARNINGS": 0.8,
        "GOVERNANCE": 0.8,
        "CENTRAL_BANK_POLICY": 0.8,
        "MATERIAL_AGREEMENT": 0.6,
        "CORPORATE_ACTION": 0.5,
        "BOARD_MEETING": 0.4,
        "ANNOUNCEMENT": 0.3,
        "NEWS_MEDIA": 0.2,
        "FINNHUB_NEWS": 0.2,
    }

    SOURCE_AUTHORITY = {
        "nse_rss": 1.0,
        "sec_edgar": 1.0,
        "rbi_rss": 1.0,
        "fed_rss": 1.0,
        "gdelt_doc": 0.5,
        "finnhub": 0.5,
    }

    def evaluate(
        self,
        category: str,
        source: str,
        published_at: datetime.datetime,
        is_unverified: bool = False,
        price_move_pct: Optional[float] = None,
    ) -> Tuple[str, float]:
        cat_weight = self.CATEGORY_WEIGHTS.get(category.upper(), 0.3)
        source_auth = self.SOURCE_AUTHORITY.get(source.lower(), 0.5)

        # Recency decay (half-life of 48 hours for market news)
        now = datetime.datetime.utcnow()
        hours_old = max(0.0, (now - published_at).total_seconds() / 3600.0)
        recency = max(0.2, 1.0 / (1.0 + (hours_old / 48.0)))

        # Price reaction multiplier
        price_mult = 1.0
        if price_move_pct is not None:
            abs_move = abs(price_move_pct)
            if abs_move >= 5.0:
                price_mult = 1.4
            elif abs_move >= 2.5:
                price_mult = 1.2

        score = cat_weight * source_auth * recency * price_mult

        # Unverified rumours discounted
        if is_unverified:
            score *= 0.5

        score = round(min(1.0, score), 3)

        if score >= 0.60:
            level = "HIGH"
        elif score >= 0.30:
            level = "MEDIUM"
        else:
            level = "LOW"

        return level, score


class ExtractiveSummarizer:
    """Fast, deterministic 2-sentence extractive summary interface.
    Zero hallucination risk, zero API dependency.
    """

    def summarize(self, title: str, text: Optional[str] = None, max_sentences: int = 2) -> str:
        clean_title = (title or "").strip()
        clean_text = (text or "").strip()

        # Remove html tags
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        if not clean_text or clean_text == clean_title:
            return clean_title

        # Sentence tokenizer
        sentences = re.split(r"(?<=[.!?])\s+", clean_text)
        non_empty = [s.strip() for s in sentences if len(s.strip()) > 10]

        summary_parts = [clean_title]
        for s in non_empty:
            if s != clean_title and len(summary_parts) < max_sentences:
                summary_parts.append(s)

        res = " ".join(summary_parts)
        if not res.endswith((".", "!", "?")):
            res += "."
        return res


class ContextualPriceReaction:
    """Calculates day's price movement in % and ATR multiples to contextualize the news."""

    def calculate(
        self,
        open_price: Optional[float],
        close_price: Optional[float],
        atr: Optional[float] = None,
    ) -> Tuple[Optional[float], Optional[float]]:
        if open_price is None or close_price is None or open_price <= 0:
            return None, None

        day_pct = round(((close_price - open_price) / open_price) * 100.0, 2)
        atr_mult = None
        if atr is not None and atr > 0:
            atr_mult = round(abs(close_price - open_price) / atr, 2)

        return day_pct, atr_mult


# Global singleton instances for easy re-use
entity_resolver = EntityResolver()
syndication_clusterer = WireSyndicationClusterer()
rumour_classifier = RumourClassifier()
analyst_extractor = AnalystActionExtractor()
materiality_evaluator = MaterialityEvaluator()
extractive_summarizer = ExtractiveSummarizer()
price_reaction_calculator = ContextualPriceReaction()
