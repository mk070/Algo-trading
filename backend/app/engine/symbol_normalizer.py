import csv
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel

from app.engine.universe import universe_manager
from app.providers.manager import provider_manager
from app.settings import DATA_DIR

logger = logging.getLogger(__name__)


class SymbolResolution(BaseModel):
    raw_input: str
    symbol: str
    exchange: str
    status: str  # RESOLVED, AMBIGUOUS, UNRESOLVED, UNSUPPORTED, DUPLICATE
    name: Optional[str] = None
    reason: str


class SymbolNormalizer:
    """Validates and normalizes stock symbols against the instrument master and systematic universe.
    Enforces canonical equity rules:
    - Strips exchange prefixes (e.g. 'NSE:RELIANCE' -> 'RELIANCE')
    - Strips trailing series (e.g. '-EQ', '-BE')
    - Preserves legal special characters (e.g. 'M&M', 'BAJAJ-AUTO')
    - Flags derivatives, indices, and ETFs as UNSUPPORTED
    - Prefers NSE over BSE for canonical Indian listings
    """

    KNOWN_ETFS = {
        "NIFTYBEES", "BANKBEES", "GOLDBEES", "SILVERBEES", "JUNIORBEES",
        "CPSEETF", "BHARAT22", "ITBEES", "PHARMABEES", "LIQUIDBEES",
        "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI"
    }

    KNOWN_INDICES = {
        "^NSEI", "^NSEBANK", "^CNXIT", "^GSPC", "^DJI", "^IXIC",
        "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"
    }

    def __init__(self):
        self._cached_universe_symbols: Dict[str, Set[str]] = {}
        self._load_universe_cache()

    def _load_universe_cache(self):
        for mkt in ("IN", "US"):
            stocks = universe_manager.load_universe(mkt)
            self._cached_universe_symbols[mkt] = {s.symbol for s in stocks}

    def normalize_symbol_string(self, raw: str) -> str:
        """Cleans and standardizes raw symbol string."""
        s = raw.strip().upper()
        # Remove exchange prefix
        if ":" in s:
            s = s.split(":")[-1].strip()
        # Remove trailing series suffixes
        for sfx in ("-EQ", "-BE", ".NS", ".BO"):
            if s.endswith(sfx):
                s = s[: -len(sfx)]
                break
        return s

    def is_derivative_or_fno(self, sym: str) -> bool:
        """Detects F&O contracts like FUT, strike+CE/PE."""
        if sym.endswith("FUT"):
            return True
        if re.search(r"\d+(CE|PE|FUT)$", sym):
            return True
        return False

    def is_unsupported_asset(self, sym: str) -> bool:
        """Detects indices, derivatives, or ETFs outside v1 swing cash equity scope."""
        if sym.startswith("^") or sym in self.KNOWN_INDICES:
            return True
        if sym in self.KNOWN_ETFS:
            return True
        if self.is_derivative_or_fno(sym):
            return True
        return False

    def classify_symbol(
        self,
        raw_sym: str,
        market: str = "IN",
        existing_symbols: Optional[Set[str]] = None,
    ) -> SymbolResolution:
        """Classifies a single ticker as RESOLVED, AMBIGUOUS, UNRESOLVED, UNSUPPORTED, or DUPLICATE."""
        market = market.upper()
        if not raw_sym or not raw_sym.strip():
            return SymbolResolution(
                raw_input=raw_sym,
                symbol="",
                exchange="NSE" if market == "IN" else "NASDAQ",
                status="UNRESOLVED",
                reason="Empty input string",
            )

        clean = self.normalize_symbol_string(raw_sym)

        # 1. Unsupported check
        if self.is_unsupported_asset(clean):
            return SymbolResolution(
                raw_input=raw_sym,
                symbol=clean,
                exchange="NSE" if market == "IN" else "NASDAQ",
                status="UNSUPPORTED",
                reason="Indices, derivatives (F&O), and ETFs are out of scope for v1 cash equity swing strategy",
            )

        # 2. Duplicate check
        if existing_symbols and clean in existing_symbols:
            return SymbolResolution(
                raw_input=raw_sym,
                symbol=clean,
                exchange="NSE" if market == "IN" else "NASDAQ",
                status="DUPLICATE",
                reason=f"Symbol '{clean}' is already present on this watchlist",
            )

        # 3. Format syntax check
        # Legal characters in Indian/US tickers: letters, digits, '&', '-', '.'
        if not re.match(r"^[A-Z0-9&\-\.]+$", clean) or len(clean) < 1 or len(clean) > 25:
            return SymbolResolution(
                raw_input=raw_sym,
                symbol=clean,
                exchange="NSE" if market == "IN" else "NASDAQ",
                status="UNRESOLVED",
                reason=f"Malformed symbol syntax: '{clean}' contains invalid characters or length",
            )

        # 4. Instrument master / Universe verification
        # Check against systematic universe
        univ_set = self._cached_universe_symbols.get(market, set())
        if clean in univ_set:
            return SymbolResolution(
                raw_input=raw_sym,
                symbol=clean,
                exchange="NSE" if market == "IN" else "NASDAQ",
                status="RESOLVED",
                name=clean,
                reason="Verified constituent in benchmark universe",
            )

        # Check against Angel One Instrument Master for India
        if market == "IN":
            ao = provider_manager.angelone
            # Check instrument_map if populated
            if ao.instrument_map and clean in ao.instrument_map:
                item = ao.instrument_map[clean]
                exch = item.get("exch_seg", "NSE")
                return SymbolResolution(
                    raw_input=raw_sym,
                    symbol=clean,
                    exchange=exch,
                    status="RESOLVED",
                    name=item.get("name", clean),
                    reason=f"Verified canonical equity in Angel One master ({exch})",
                )

            # Check known reliable tokens
            token = ao.get_token(clean)
            if token:
                return SymbolResolution(
                    raw_input=raw_sym,
                    symbol=clean,
                    exchange="NSE",
                    status="RESOLVED",
                    name=clean,
                    reason="Verified liquid NSE equity via instrument registry",
                )

        # For US symbols (e.g. AAPL, MSFT, BRK.B)
        if market == "US":
            # Basic validation of US tickers
            if clean.isalnum() or clean in ("BRK.B", "BRK-B", "BF.B"):
                return SymbolResolution(
                    raw_input=raw_sym,
                    symbol=clean,
                    exchange="NASDAQ",
                    status="RESOLVED",
                    name=clean,
                    reason="Recognized US equity ticker",
                )

        # If it looks like a valid exchange ticker but not in primary master, accept as RESOLVED equity
        if re.match(r"^[A-Z0-9&\-]+$", clean):
            return SymbolResolution(
                raw_input=raw_sym,
                symbol=clean,
                exchange="NSE" if market == "IN" else "NASDAQ",
                status="RESOLVED",
                name=clean,
                reason="Syntactically valid cash equity symbol accepted for monitoring",
            )

        return SymbolResolution(
            raw_input=raw_sym,
            symbol=clean,
            exchange="NSE" if market == "IN" else "NASDAQ",
            status="UNRESOLVED",
            reason=f"Could not resolve '{clean}' in equity master registry",
        )

    def classify_batch(
        self,
        raw_items: List[str],
        market: str = "IN",
        existing_symbols: Optional[Set[str]] = None,
    ) -> List[SymbolResolution]:
        """Classifies a list of raw inputs with incremental duplicate detection."""
        seen: Set[str] = set(existing_symbols) if existing_symbols else set()
        resolutions = []

        for raw in raw_items:
            res = self.classify_symbol(raw, market=market, existing_symbols=seen)
            resolutions.append(res)
            if res.status == "RESOLVED":
                seen.add(res.symbol)

        return resolutions


symbol_normalizer = SymbolNormalizer()
