import datetime
import logging
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy.orm import Session

from app.models import DailyBar
from app.providers.alpaca_provider import AlpacaProvider
from app.providers.angelone_provider import AngelOneProvider
from app.providers.base import MarketDataProvider, ProviderHealth, Quote, validate_candle_data
from app.providers.kite_provider import KitePortfolioReader
from app.providers.yfinance_provider import YFinanceProvider
from app.settings import settings

logger = logging.getLogger(__name__)


class ProviderManager:
    """Orchestrates market data providers, failovers, freshness monitoring, and caching."""

    def __init__(self):
        self.angelone = AngelOneProvider()
        self.yfinance = YFinanceProvider()
        self.alpaca = AlpacaProvider()
        self.kite = KitePortfolioReader()

    def get_provider_chain(self, market: str) -> List[MarketDataProvider]:
        if market.upper() == "IN":
            return [self.angelone, self.yfinance]
        else:
            return [self.alpaca, self.yfinance]

    def get_daily_bars(
        self,
        symbols: List[str],
        start: datetime.date,
        end: datetime.date,
        market: str = "IN",
        db: Optional[Session] = None,
    ) -> Dict[str, pd.DataFrame]:
        results: Dict[str, pd.DataFrame] = {}
        missing_symbols = list(symbols)

        # 1. Try reading from PostgreSQL cache if DB session is provided
        if db is not None:
            cached_dfs = {}
            for sym in symbols:
                rows = (
                    db.query(DailyBar)
                    .filter(
                        DailyBar.symbol == sym,
                        DailyBar.date >= start,
                        DailyBar.date <= end,
                    )
                    .order_by(DailyBar.date.asc())
                    .all()
                )
                if rows and len(rows) >= 20:  # reasonable minimum cached window
                    df = pd.DataFrame(
                        [
                            {
                                "date": r.date,
                                "open": r.open,
                                "high": r.high,
                                "low": r.low,
                                "close": r.close,
                                "adj_close": r.adj_close,
                                "volume": r.volume,
                                "source": r.source,
                            }
                            for r in rows
                        ]
                    )
                    cached_dfs[sym] = df
            for sym, df in cached_dfs.items():
                results[sym] = df
                if sym in missing_symbols:
                    missing_symbols.remove(sym)

        if not missing_symbols:
            return results

        # 2. Fetch missing symbols via provider chain
        chain = self.get_provider_chain(market)
        for provider in chain:
            try:
                bars = provider.daily_bars(missing_symbols, start, end)
                for sym, df in bars.items():
                    if df is not None and not df.empty:
                        results[sym] = df
                        if sym in missing_symbols:
                            missing_symbols.remove(sym)
                        # Save to DB cache
                        if db is not None:
                            self._cache_bars_to_db(db, sym, df)
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for {market}: {e}")

            if not missing_symbols:
                break

        return results

    def _cache_bars_to_db(self, db: Session, symbol: str, df: pd.DataFrame):
        try:
            for _, row in df.iterrows():
                row_date = row["date"]
                if isinstance(row_date, str):
                    row_date = datetime.date.fromisoformat(row_date)
                elif isinstance(row_date, pd.Timestamp):
                    row_date = row_date.date()

                existing = (
                    db.query(DailyBar)
                    .filter(DailyBar.symbol == symbol, DailyBar.date == row_date)
                    .first()
                )
                if not existing:
                    bar = DailyBar(
                        symbol=symbol,
                        date=row_date,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        adj_close=float(row.get("adj_close", row["close"])),
                        volume=float(row["volume"]),
                        source=str(row.get("source", "unknown")),
                    )
                    db.add(bar)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Error caching bars for {symbol}: {e}")

    def get_quotes(self, symbols: List[str], market: str = "IN") -> Dict[str, Quote]:
        """Fetch quotes enforcing freshness checks."""
        chain = self.get_provider_chain(market)
        quotes: Dict[str, Quote] = {}
        missing = list(symbols)

        for provider in chain:
            try:
                res = provider.quotes(missing)
                now = datetime.datetime.utcnow()
                for sym, q in res.items():
                    # Strict freshness check
                    age_sec = (now - q.timestamp).total_seconds()
                    max_age = 20 if q.is_realtime else 60
                    if age_sec > max_age:
                        q.is_stale = True

                    quotes[sym] = q
                    if sym in missing:
                        missing.remove(sym)
            except Exception as e:
                logger.warning(f"Provider {provider.name} quote failed: {e}")

            if not missing:
                break

        return quotes

    def check_health(self) -> Dict[str, ProviderHealth]:
        return {
            "angelone": self.angelone.health(),
            "yfinance": self.yfinance.health(),
            "alpaca": self.alpaca.health(),
            "kite_personal": ProviderHealth(
                name="kite_personal",
                status="HEALTHY" if self.kite.is_authenticated() else ("CONFIGURED_NOT_AUTH" if self.kite.is_configured() else "NOT_CONFIGURED"),
                is_realtime=False,
                message="Zerodha Kite Personal connected" if self.kite.is_authenticated() else "Daily login required via /portfolio/kite/login-url",
            ),
        }


provider_manager = ProviderManager()

