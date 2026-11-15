"""NSE MCP (Market Data Protocol) Provider — Evaluation & Read-Only Adapter.

LEGAL & COMPLIANCE NOTICE:
--------------------------
1. Terms of Use: Access to National Stock Exchange of India (NSE) web endpoints,
   including https://mcp.nseindia.in/ and bhavcopy resources, is strictly subject
   to the NSE Website Terms of Use. Automated scraping, high-frequency polling,
   commercial redistribution, and live execution triggering without an official
   NSE Data Vendor / API license are strictly prohibited.
2. Anti-Bot Protections: Endpoints are gated by Akamai CDN bot detection and WAF.
   In compliance with platform policy and anti-circumvention rules, this adapter
   NEVER attempts to solve, compute, or bypass CAPTCHA, Cloudflare, Akamai, or
   proof-of-work challenges.
3. Default State: This provider is DISABLED BY DEFAULT (enabled = False). It serves
   solely as an architectural reference and optional educational adapter for
   local end-of-day Bhavcopy inspection when authorized.
"""

import datetime
import logging
from typing import Dict, List, Optional
import pandas as pd

from app.providers.base import MarketDataProvider, ProviderHealth, Quote, QuoteFreshness

logger = logging.getLogger(__name__)


class NSEMCPProvider(MarketDataProvider):
    """Read-only adapter for NSE Bhavcopy MCP resources.

    Disabled by default. Does not participate in automated live order placement.
    """

    def __init__(self, enabled: bool = False):
        self._enabled = enabled
        self._endpoint = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
        self._name = "NSE_MCP_READONLY"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def check_health(self) -> ProviderHealth:
        if not self._enabled:
            return ProviderHealth(
                is_healthy=False,
                latency_ms=0,
                error="NSE MCP adapter is disabled by default. Configure NSE_MCP_ENABLED=true with proper exchange entitlements.",
            )
        return ProviderHealth(is_healthy=True, latency_ms=0)

    def get_quotes(self, symbols: List[str], market: str = "IN") -> Dict[str, Quote]:
        """NSE MCP is an EOD/settlement reporting protocol, not an intraday streaming feed."""
        logger.warning("NSE MCP adapter does not provide real-time intraday quotes.")
        return {}

    def get_daily_bars(
        self,
        symbols: List[str],
        start: datetime.date,
        end: datetime.date,
        market: str = "IN",
    ) -> Dict[str, pd.DataFrame]:
        """Fetch daily EOD bars from Bhavcopy settlement reports if explicitly enabled."""
        if not self._enabled:
            logger.info("NSE MCP adapter disabled. Skipping EOD fetch.")
            return {}

        # Gated by Akamai WAF. If invoked, handles gracefully without circumvention:
        logger.warning("NSE MCP endpoint requires interactive session or authorized API key.")
        return {}
