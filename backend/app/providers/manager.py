import datetime
import logging
from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy.orm import Session

from app.models import DailyBar, LatestQuote
from app.providers.alpaca_provider import AlpacaProvider
from app.providers.angelone_provider import AngelOneProvider
from app.providers.base import (
    DecisionQuote,
    IneligibleQuoteError,
    MarketDataProvider,
    ProviderHealth,
    Quote,
    QuoteFreshness,
    validate_candle_data,
)
from app.providers.kite_provider import KitePortfolioReader
from app.providers.request_layer import request_layers
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
                        DailyBar.source.notin_(['synthetic_fixture', 'mock', 'synthetic_fallback']),
                    )
                    .order_by(DailyBar.date.asc())
                    .all()
                )
                if rows and len(rows) >= 20:
                    latest_cached_date = rows[-1].date
                    if (end - latest_cached_date).days <= 3:
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

        # 2. Fetch missing symbols via provider chain wrapped in request layer
        chain = self.get_provider_chain(market)
        for provider in chain:
            try:
                rl = request_layers.get(provider.name)
                req_key = f"daily_bars:{provider.name}:{market}:{','.join(sorted(missing_symbols))}:{start}:{end}"
                def _fetch_bars(p=provider, syms=missing_symbols, s=start, e=end, m=market):
                    try:
                        return p.daily_bars(syms, s, e, market=m)
                    except TypeError:
                        return p.daily_bars(syms, s, e)

                if rl:
                    bars = rl.execute(req_key, _fetch_bars, ttl_sec=300.0)
                else:
                    bars = _fetch_bars()

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

    def get_intraday_bars(
        self,
        symbols: List[str],
        interval: str = "FIFTEEN_MINUTE",
        days: int = 5,
        market: str = "IN",
    ) -> Dict[str, pd.DataFrame]:
        results: Dict[str, pd.DataFrame] = {}
        missing_symbols = list(symbols)

        chain = self.get_provider_chain(market)
        for provider in chain:
            try:
                if hasattr(provider, "intraday_bars"):
                    yf_interval = "15m" if "FIFTEEN" in interval.upper() or interval == "15m" else interval
                    if provider.name == "yfinance":
                        bars = provider.intraday_bars(missing_symbols, interval=yf_interval, days=days, market=market)
                    else:
                        bars = provider.intraday_bars(missing_symbols, interval=interval, days=days)

                    for sym, df in bars.items():
                        if df is not None and not df.empty:
                            results[sym] = df
                            if sym in missing_symbols:
                                missing_symbols.remove(sym)
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed intraday bars for {market}: {e}")

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
                if existing:
                    existing.open = float(row['open'])
                    existing.high = float(row['high'])
                    existing.low = float(row['low'])
                    existing.close = float(row['close'])
                    existing.adj_close = float(row.get('adj_close', row['close']))
                    existing.volume = float(row['volume'])
                    existing.source = str(row.get('source', 'unknown'))
                else:
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

    def save_latest_quotes_to_db(self, quotes: Dict[str, Quote], market: str, db: Session):
        """Multi-worker state synchronization: upserts latest quotes into PostgreSQL."""
        try:
            for sym, q in quotes.items():
                if q.provider in ('synthetic_fallback', 'mock', 'synthetic_fixture'):
                    continue
                existing = (
                    db.query(LatestQuote)
                    .filter(LatestQuote.symbol == sym, LatestQuote.market == market)
                    .first()
                )
                if existing:
                    existing.price = q.price
                    existing.provider = q.provider
                    existing.exchange_ts = q.exchange_ts
                    existing.received_ts = q.received_ts
                    existing.freshness = q.freshness.value if isinstance(q.freshness, QuoteFreshness) else str(q.freshness)
                    existing.realtime = q.realtime
                    existing.day_volume = q.day_volume
                    existing.open = q.open
                    existing.high = q.high
                    existing.low = q.low
                    existing.close = q.close
                else:
                    new_q = LatestQuote(
                        symbol=sym,
                        market=market,
                        price=q.price,
                        provider=q.provider,
                        exchange_ts=q.exchange_ts,
                        received_ts=q.received_ts,
                        freshness=q.freshness.value if isinstance(q.freshness, QuoteFreshness) else str(q.freshness),
                        realtime=q.realtime,
                        day_volume=q.day_volume,
                        open=q.open,
                        high=q.high,
                        low=q.low,
                        close=q.close,
                    )
                    db.add(new_q)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"Error persisting latest quotes to DB: {e}")

    def get_quotes(
        self,
        symbols: List[str],
        market: str = "IN",
        db: Optional[Session] = None,
    ) -> Dict[str, Quote]:
        """Fetch quotes enforcing freshness checks, with multi-worker DB synchronization."""
        quotes: Dict[str, Quote] = {}
        missing = list(symbols)
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Multi-worker sync: check shared PostgreSQL latest_quotes table
        if db is not None:
            try:
                db_quotes = (
                    db.query(LatestQuote)
                    .filter(
                        LatestQuote.symbol.in_(symbols),
                        LatestQuote.market == market,
                    )
                    .all()
                )
                for row in db_quotes:
                    if row.provider in ('synthetic_fallback', 'mock', 'synthetic_fixture'):
                        continue
                    row_ex_ts = row.exchange_ts if row.exchange_ts.tzinfo else row.exchange_ts.replace(tzinfo=datetime.timezone.utc)
                    age_sec = (now - row_ex_ts).total_seconds()
                    max_age = 20.0 if row.realtime else 60.0
                    freshness = QuoteFreshness.FRESH if age_sec <= max_age else QuoteFreshness.STALE

                    prev_c = row.close or row.open or row.price
                    chg = round(row.price - prev_c, 2) if prev_c > 0 else 0.0
                    chg_pct = round(((row.price - prev_c) / prev_c) * 100.0, 2) if prev_c > 0 else 0.0

                    q = Quote(
                        symbol=row.symbol,
                        market=row.market,
                        price=row.price,
                        provider=row.provider,
                        exchange_ts=row_ex_ts,
                        received_ts=row.received_ts,
                        freshness=freshness,
                        realtime=row.realtime,
                        day_volume=row.day_volume,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        prev_close=row.close,
                        change=chg,
                        change_pct=chg_pct,
                    )
                    quotes[row.symbol] = q
                    if age_sec <= max_age and row.symbol in missing:
                        missing.remove(row.symbol)
            except Exception as e:
                logger.warning(f"Error fetching shared quotes from DB: {e}")

        if not missing:
            return quotes

        # 2. Query provider chain guarded by request layer
        chain = self.get_provider_chain(market)
        for provider in chain:
            try:
                rl = request_layers.get(provider.name)
                req_key = f"quotes:{provider.name}:{market}:{','.join(sorted(missing))}"
                def _fetch_quotes(p=provider, syms=missing, m=market):
                    try:
                        return p.quotes(syms, market=m)
                    except TypeError:
                        return p.quotes(syms)

                if rl:
                    res = rl.execute(req_key, _fetch_quotes, ttl_sec=5.0)
                else:
                    res = _fetch_quotes()

                for sym, raw_q in res.items():
                    ts = raw_q.timestamp if raw_q.timestamp.tzinfo else raw_q.timestamp.replace(tzinfo=datetime.timezone.utc)
                    age_sec = (now - ts).total_seconds()
                    max_age = 20.0 if raw_q.is_realtime else 60.0

                    if age_sec > max_age:
                        freshness = QuoteFreshness.STALE
                    elif not raw_q.is_realtime:
                        freshness = QuoteFreshness.DELAYED
                    else:
                        freshness = QuoteFreshness.FRESH

                    prev_c = raw_q.prev_close or raw_q.close or raw_q.open or raw_q.last_price
                    chg = raw_q.change if raw_q.change is not None else (round(raw_q.last_price - prev_c, 2) if prev_c > 0 else 0.0)
                    chg_pct = raw_q.change_pct if raw_q.change_pct is not None else (round(((raw_q.last_price - prev_c) / prev_c) * 100.0, 2) if prev_c > 0 else 0.0)

                    q = Quote(
                        symbol=sym,
                        market=market,
                        price=raw_q.last_price,
                        provider=raw_q.source or provider.name,
                        exchange_ts=ts,
                        received_ts=now,
                        freshness=freshness,
                        realtime=raw_q.is_realtime,
                        day_volume=raw_q.day_volume,
                        open=raw_q.open,
                        high=raw_q.high,
                        low=raw_q.low,
                        close=raw_q.close or prev_c,
                        prev_close=prev_c,
                        change=chg,
                        change_pct=chg_pct,
                        bid=raw_q.bid,
                        ask=raw_q.ask,
                    )
                    quotes[sym] = q
                    clean_alias = sym.replace('BSE:', '').replace('NSE:', '').strip().upper()
                    quotes[clean_alias] = q
                    if clean_alias in ('SENSEX', 'BSESN'):
                        quotes['SENSEX'] = q
                        quotes['BSE:SENSEX'] = q
                        quotes['BSESN'] = q
                    elif clean_alias in ('NIFTY', 'NIFTY50'):
                        quotes['NIFTY'] = q
                        quotes['NSE:NIFTY'] = q
                        quotes['NIFTY50'] = q
                    elif clean_alias in ('BANKNIFTY',):
                        quotes['BANKNIFTY'] = q
                        quotes['NSE:BANKNIFTY'] = q
                    else:
                        quotes[f'BSE:{clean_alias}'] = q
                        quotes[f'NSE:{clean_alias}'] = q

                    for candidate in list(missing):
                        cand_clean = candidate.replace('BSE:', '').replace('NSE:', '').strip().upper()
                        if candidate in quotes or cand_clean == clean_alias:
                            missing.remove(candidate)
            except Exception as e:
                logger.warning(f"Provider {provider.name} quote failed: {e}")

            if not missing:
                break

        # 3. Multi-worker sync: persist newly fetched quotes to PostgreSQL
        if db is not None and quotes:
            self.save_latest_quotes_to_db(quotes, market, db)

        return quotes

    def get_decision_quotes(
        self,
        symbols: List[str],
        market: str = "IN",
        db: Optional[Session] = None,
    ) -> Dict[str, DecisionQuote]:
        """Decision Lane boundary: strictly filters out any non-FRESH or non-realtime quotes."""
        all_quotes = self.get_quotes(symbols, market=market, db=db)
        decision_quotes: Dict[str, DecisionQuote] = {}
        for sym, q in all_quotes.items():
            try:
                dq = q.to_decision_quote()
                decision_quotes[sym] = dq
            except IneligibleQuoteError as e:
                logger.debug(f"Quote for {sym} excluded from decision lane: {e}")
        return decision_quotes

    def check_health(self) -> Dict[str, ProviderHealth]:
        def _enrich(h: ProviderHealth) -> ProviderHealth:
            rl = request_layers.get(h.name)
            if rl:
                m = rl.get_metrics()
                h.success_rate = m["success_rate"]
                h.p50_latency_ms = m["p50_latency_ms"]
                h.p95_latency_ms = m["p95_latency_ms"]
                h.circuit_state = m["circuit_state"]
                h.cooldown_until = m["cooldown_until"]
                if m.get("last_error"):
                    h.last_error = m["last_error"]
            return h

        return {
            "angelone": _enrich(self.angelone.health()),
            "yfinance": _enrich(self.yfinance.health()),
            "alpaca": _enrich(self.alpaca.health()),
            "kite_personal": _enrich(
                ProviderHealth(
                    name="kite_personal",
                    status="HEALTHY" if self.kite.is_authenticated() else ("CONFIGURED_NOT_AUTH" if self.kite.is_configured() else "NOT_CONFIGURED"),
                    is_realtime=False,
                    message="Zerodha Kite Personal connected" if self.kite.is_authenticated() else "Daily login required via /portfolio/kite/login-url",
                )
            ),
        }


provider_manager = ProviderManager()

