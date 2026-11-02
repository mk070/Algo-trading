import asyncio
import datetime
import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
import pandas as pd
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import check_db_health, get_db
from app.engine.indicators import add_all_indicators
from app.engine.regime import evaluate_market_regime
from app.engine.screener import screener_engine
from app.engine.universe import universe_manager
from app.models import Alert, CustomPriceAlert, DailyBar, Instrument, JobRun, LatestQuote, Position, SettingKV, Signal
from app.notify.dispatcher import dispatcher
from app.notify.telegram import telegram_notifier
from app.providers.base import ProviderHealth, Quote, QuoteFreshness
from app.providers.manager import provider_manager
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def get_health(db: Session = Depends(get_db)):
    """Health check: provider status, last job runs, database connectivity."""
    providers = provider_manager.check_health()
    db_health = check_db_health()
    try:
        last_jobs = (
            db.query(JobRun)
            .order_by(JobRun.started_at.desc())
            .limit(10)
            .all()
        )
    except Exception as e:
        logger.warning(f"Failed to fetch job runs in health check: {e}")
        last_jobs = []
    job_summaries = [
        {
            "job": j.job,
            "status": j.status,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "detail": j.detail,
        }
        for j in last_jobs
    ]

    return {
        "status": "HEALTHY" if db_health.get("status") == "HEALTHY" else "DEGRADED",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "database": db_health,
        "providers": {k: v.model_dump() for k, v in providers.items()},
        "last_job_runs": job_summaries,
    }


@router.get("/health/db")
def get_database_health():
    """Detailed database health monitoring endpoint for Neon PostgreSQL."""
    return check_db_health()


@router.get("/neon/services")
def get_neon_services():
    """Returns end-to-end status of all wired Neon services: Postgres, Auth, and Realtime."""
    db_health = check_db_health()
    
    auth_status = {
        "configured": bool(settings.neon_auth_base_url),
        "base_url": settings.neon_auth_base_url,
        "jwks_url": settings.neon_auth_jwks_url,
    }
    if settings.neon_auth_jwks_url:
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                res = client.get(settings.neon_auth_jwks_url)
                if res.status_code == 200:
                    auth_status["status"] = "CONNECTED"
                    auth_status["keys_count"] = len(res.json().get("keys", []))
                else:
                    auth_status["status"] = f"HTTP_{res.status_code}"
        except Exception as e:
            auth_status["status"] = "UNREACHABLE"
            auth_status["error"] = str(e)
    else:
        auth_status["status"] = "NOT_CONFIGURED"

    rt_status = {
        "configured": bool(settings.neon_realtime_url),
        "url": settings.neon_realtime_url,
        "secret_set": bool(settings.neon_realtime_secret),
        "status": "ACTIVE" if (settings.neon_realtime_url and settings.neon_realtime_secret) else "NOT_CONFIGURED",
    }

    return {
        "branch": settings.neon_branch or "production",
        "postgres": db_health,
        "auth": auth_status,
        "realtime": rt_status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get("/regime")
def get_regime(market: str = Query("IN", pattern="^(IN|US)$"), db: Session = Depends(get_db)):
    """Returns current market regime status and index indicators."""
    mkt_cfg = settings.get_market_config(market)
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=400)
    bars = provider_manager.get_daily_bars([mkt_cfg.index_symbol], start_date, today, market=market, db=db)
    index_df = bars.get(mkt_cfg.index_symbol)
    res = evaluate_market_regime(index_df, market=market)
    return res.model_dump()


@router.get("/quotes")
def get_quotes(symbols: str = Query(..., description="Comma-separated symbols"), market: str = "IN"):
    """Fetch live or cached quotes with freshness and staleness flags."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    quotes = provider_manager.get_quotes(sym_list, market=market)
    return {s: q.model_dump() for s, q in quotes.items()}


@router.get("/bars/{symbol}")
def get_bars(
    symbol: str,
    tf: str = "1d",
    n: int = 250,
    market: str = "IN",
    db: Session = Depends(get_db),
):
    """Returns OHLCV bars + indicators (EMA20, EMA50, SMA50, SMA150, SMA200, RSI, ATR),
    feed freshness metadata, and existing strategy overlays for TradingView interactive charts.
    """
    clean_sym = symbol.strip().upper()
    clean_mkt = market.strip().upper()
    today = datetime.date.today()
    is_15m = tf.lower() in ("15m", "fifteen_minute", "15min")

    daily_df = None
    candle_data = []

    if is_15m:
        bars_dict = provider_manager.get_intraday_bars([clean_sym], interval="FIFTEEN_MINUTE", days=7, market=clean_mkt)
        df_15m = bars_dict.get(clean_sym)
        if df_15m is not None and not df_15m.empty:
            df_15m = df_15m.copy()
            time_col = "timestamp" if "timestamp" in df_15m.columns else ("datetime" if "datetime" in df_15m.columns else df_15m.columns[0])
            df_15m["timestamp"] = pd.to_datetime(df_15m[time_col])
            df_15m = df_15m.sort_values("timestamp").reset_index(drop=True)
            df_15m = add_all_indicators(df_15m)
            recent_15m = df_15m.iloc[-min(len(df_15m), n):]
            for _, r in recent_15m.iterrows():
                ts_val = int(pd.to_datetime(r["timestamp"]).timestamp())
                candle_data.append({
                    "time": ts_val,
                    "open": round(float(r["open"]), 2),
                    "high": round(float(r["high"]), 2),
                    "low": round(float(r["low"]), 2),
                    "close": round(float(r["close"]), 2),
                    "volume": float(r["volume"]),
                    "ema20": round(float(r["ema20"]), 2) if pd.notna(r.get("ema20")) else None,
                    "ema50": round(float(r["ema50"]), 2) if pd.notna(r.get("ema50")) else None,
                    "sma50": round(float(r["sma50"]), 2) if pd.notna(r.get("sma50")) else None,
                    "sma150": round(float(r["sma150"]), 2) if pd.notna(r.get("sma150")) else None,
                    "sma200": round(float(r["sma200"]), 2) if pd.notna(r.get("sma200")) else None,
                    "rsi14": round(float(r["rsi14"]), 1) if pd.notna(r.get("rsi14")) else None,
                    "atr14": round(float(r["atr14"]), 2) if pd.notna(r.get("atr14")) else None,
                })

    if not is_15m or not candle_data:
        # Daily bars
        start_date = today - datetime.timedelta(days=max(n * 2, 365))
        bars = provider_manager.get_daily_bars([clean_sym], start_date, today, market=market, db=db)
        daily_df = bars.get(clean_sym)
        if daily_df is None or daily_df.empty:
            raise HTTPException(status_code=404, detail=f"No bars found for symbol {clean_sym}")

        daily_df = add_all_indicators(daily_df)
        recent_daily = daily_df.iloc[-min(len(daily_df), n):]

        candle_data = []
        for _, r in recent_daily.iterrows():
            d_val = r["date"]
            time_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
            candle_data.append({
                "time": time_str,
                "open": round(float(r["open"]), 2),
                "high": round(float(r["high"]), 2),
                "low": round(float(r["low"]), 2),
                "close": round(float(r["close"]), 2),
                "volume": float(r["volume"]),
                "ema20": round(float(r["ema20"]), 2) if pd.notna(r.get("ema20")) else None,
                "ema50": round(float(r["ema50"]), 2) if pd.notna(r.get("ema50")) else None,
                "sma50": round(float(r["sma50"]), 2) if pd.notna(r.get("sma50")) else None,
                "sma150": round(float(r["sma150"]), 2) if pd.notna(r.get("sma150")) else None,
                "sma200": round(float(r["sma200"]), 2) if pd.notna(r.get("sma200")) else None,
                "rsi14": round(float(r["rsi14"]), 1) if pd.notna(r.get("rsi14")) else None,
                "atr14": round(float(r["atr14"]), 2) if pd.notna(r.get("atr14")) else None,
            })

    # Live Quote & Feed Status evaluation
    feed_status = "DELAYED"
    provider_name = "angelone" if market == "IN" else "alpaca"
    last_quote_time = None
    lq = None
    try:
        live_quotes = provider_manager.get_quotes([clean_sym], market=market, db=db)
        lq = live_quotes.get(clean_sym)
        if lq:
            provider_name = lq.provider or provider_name
            if lq.exchange_ts:
                last_quote_time = lq.exchange_ts.isoformat()

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            q_time = lq.exchange_ts if lq.exchange_ts.tzinfo else lq.exchange_ts.replace(tzinfo=datetime.timezone.utc)
            age_sec = (now_utc - q_time).total_seconds()

            if lq.realtime and lq.freshness == QuoteFreshness.FRESH and age_sec <= 60.0:
                feed_status = "LIVE"
            elif lq.freshness == QuoteFreshness.STALE or age_sec > 300.0:
                feed_status = "STALE"
            elif lq.freshness == QuoteFreshness.DELAYED or not lq.realtime:
                feed_status = "DELAYED"
            else:
                feed_status = "LIVE" if lq.realtime else "DELAYED"

            # 0-Latency Live Quote Injection into the latest daily candle
            if lq.price > 0 and candle_data and not is_15m:
                today_str = today.isoformat()
                if candle_data[-1]["time"] == today_str:
                    candle_data[-1]["close"] = round(float(lq.price), 2)
                    candle_data[-1]["high"] = max(candle_data[-1]["high"], round(float(lq.price), 2))
                    candle_data[-1]["low"] = min(candle_data[-1]["low"], round(float(lq.price), 2))
                    if lq.day_volume > 0:
                        candle_data[-1]["volume"] = float(lq.day_volume)
                else:
                    prev_close = candle_data[-1]["close"]
                    candle_data.append({
                        "time": today_str,
                        "open": round(float(lq.open or prev_close), 2),
                        "high": round(float(max(lq.high or lq.price, lq.price)), 2),
                        "low": round(float(min(lq.low or lq.price, lq.price)), 2),
                        "close": round(float(lq.price), 2),
                        "volume": float(lq.day_volume or 0.0),
                        "ema20": candle_data[-1]["ema20"],
                        "ema50": candle_data[-1]["ema50"],
                        "sma50": candle_data[-1]["sma50"],
                        "sma150": candle_data[-1]["sma150"],
                        "sma200": candle_data[-1]["sma200"],
                        "rsi14": candle_data[-1]["rsi14"],
                        "atr14": candle_data[-1]["atr14"],
                    })
    except Exception as e:
        logger.warning(f"Could not inject live quote into chart for {clean_sym}: {e}")
        feed_status = "DISCONNECTED"

    current_price = (
        round(float(lq.price), 2)
        if (lq and lq.price and lq.price > 0)
        else (candle_data[-1]["close"] if candle_data else None)
    )

    # Strategy Output Overlay
    strategy_overlay = None
    try:
        sig = (
            db.query(Signal)
            .filter(Signal.symbol == clean_sym, Signal.market == clean_mkt)
            .order_by(Signal.id.desc())
            .first()
        )
        if sig:
            reasons = []
            if sig.reasons_json:
                try:
                    reasons = json.loads(sig.reasons_json)
                except Exception:
                    pass

            vcp_base = None
            if sig.setup == "VCP" and len(candle_data) >= 15:
                base_bars = 20
                for r_text in reasons:
                    if "consolidation of" in r_text:
                        import re
                        m = re.search(r"consolidation of (\d+) sessions", r_text)
                        if m:
                            base_bars = int(m.group(1))
                            break

                base_bars = min(base_bars, len(candle_data))
                base_slice = candle_data[-base_bars:]
                vcp_base = {
                    "base_bars": base_bars,
                    "start_time": base_slice[0]["time"],
                    "end_time": base_slice[-1]["time"],
                    "base_high": round(max(b["high"] for b in base_slice), 2),
                    "base_low": round(min(b["low"] for b in base_slice), 2),
                    "pivot": round(sig.trigger - 0.1 * (sig.atr or 1.0), 2),
                }

            trend_template = []
            try:
                tt_df = daily_df
                if tt_df is None or len(tt_df) < 50:
                    start_date_tt = today - datetime.timedelta(days=400)
                    tt_bars = provider_manager.get_daily_bars([clean_sym], start_date_tt, today, market=market, db=db)
                    if clean_sym in tt_bars and len(tt_bars[clean_sym]) >= 50:
                        tt_df = add_all_indicators(tt_bars[clean_sym])
                if tt_df is not None and len(tt_df) >= 50:
                    tt_res = screener_engine.evaluate_trend_template(clean_sym, tt_df)
                    trend_template = [
                        {
                            "rule": item.rule,
                            "passed": item.passed,
                            "actual": item.actual_value,
                            "expected": item.expected_value,
                        }
                        for item in tt_res.checklist
                    ]
            except Exception as tt_e:
                logger.debug(f"Trend template note for {clean_sym}: {tt_e}")

            strategy_overlay = {
                "signal_id": sig.id,
                "setup": sig.setup,
                "trigger": round(sig.trigger, 2),
                "entry_zone_high": round(sig.entry_zone_high, 2),
                "stop": round(sig.stop, 2),
                "target1": round(sig.target1, 2),
                "state": sig.state,
                "rs_rank": round(sig.rs_rank, 2) if sig.rs_rank else None,
                "atr": round(sig.atr, 2) if sig.atr else None,
                "reasons": reasons,
                "vcp_base": vcp_base,
                "trend_template": trend_template,
            }
    except Exception as sig_e:
        logger.warning(f"Error compiling strategy overlay for {clean_sym}: {sig_e}")

    return {
        "symbol": clean_sym,
        "market": market,
        "timeframe": "15m" if is_15m else "1d",
        "provider": provider_name,
        "feed_status": feed_status,
        "last_quote_time": last_quote_time,
        "current_price": current_price,
        "bars": candle_data,
        "strategy_overlay": strategy_overlay,
    }


@router.get("/alerts")
def get_alerts(limit: int = 50, db: Session = Depends(get_db)):
    """Returns alert history."""
    rows = (
        db.query(Alert)
        .order_by(Alert.ts.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "ts": a.ts.isoformat(),
            "type": a.type,
            "symbol": a.symbol,
            "market": a.market,
            "title": a.title,
            "body": a.body,
            "payload": json.loads(a.payload_json) if a.payload_json else {},
            "delivered_telegram": a.delivered_telegram,
            "acknowledged": a.acknowledged,
        }
        for a in rows
    ]


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    db.commit()
    return {"status": "ACKNOWLEDGED", "id": alert_id}


@router.get("/settings")
def get_app_settings(db: Session = Depends(get_db)):
    """Returns strategy, risk, cost, and provider configuration status without revealing secrets."""
    strategy_cfg = settings.strategy_config
    return {
        "markets": strategy_cfg.get("markets", {}),
        "risk": strategy_cfg.get("risk", {}),
        "vcp": strategy_cfg.get("vcp", {}),
        "pullback": strategy_cfg.get("pullback", {}),
        "exits": strategy_cfg.get("exits", {}),
        "costs": strategy_cfg.get("costs", {}),
        "providers_status": {
            "angelone_configured": settings.angelone_api_key is not None,
            "kite_configured": settings.kite_api_key is not None,
            "alpaca_configured": settings.alpaca_api_key is not None,
            "telegram_configured": settings.telegram_bot_token is not None,
        },
        "disclaimer": "Signals are rules-based, not advice. Past/backtested performance does not guarantee future results.",
    }


@router.put("/settings")
def update_app_settings(payload: Dict, db: Session = Depends(get_db)):
    """Persists dynamic runtime overrides into settings_kv table."""
    key = "strategy_override"
    existing = db.query(SettingKV).filter(SettingKV.key == key).first()
    if existing:
        existing.value_json = json.dumps(payload)
        existing.updated_at = datetime.datetime.utcnow()
    else:
        new_row = SettingKV(key=key, value_json=json.dumps(payload))
        db.add(new_row)
    db.commit()
    return {"status": "UPDATED"}


@router.get("/telegram/status")
def get_telegram_status():
    """Returns Telegram connection status, bot username, masked chat ID, and last check timestamp."""
    return telegram_notifier.get_status()


@router.post("/telegram/test")
def test_telegram_notification():
    """Validates bot using getMe, then sends exactly one test message to the configured chat.
    Returns success only if confirmed by Telegram API, otherwise raises 400 with actionable error.
    """
    success, detail = telegram_notifier.send_test_message()
    if not success:
        raise HTTPException(status_code=400, detail=detail)
    return {
        "success": True,
        "detail": detail,
        "status": telegram_notifier.get_status(),
    }


@router.get("/stream")
async def stream_events(request: Request):
    """Server-Sent Events (SSE) pushing real-time alerts and tick updates to connected frontend clients."""
    queue = asyncio.Queue()
    dispatcher.sse_subscribers.append(queue)

    async def event_generator():
        try:
            # Send initial keepalive
            yield f"data: {json.dumps({'type': 'CONNECTED', 'timestamp': datetime.datetime.utcnow().isoformat()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield f": heartbeat\n\n"
        finally:
            if queue in dispatcher.sse_subscribers:
                dispatcher.sse_subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class CustomPriceAlertCreate(BaseModel):
    symbol: str
    market: str = "IN"
    target_price: float
    condition: str  # ABOVE, BELOW
    notes: Optional[str] = None


@router.get("/alerts/custom")
def get_custom_alerts(
    market: Optional[str] = Query(None, pattern="^(IN|US)$"),
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    """Returns custom price alerts, optionally filtered by market and active state."""
    q = db.query(CustomPriceAlert)
    if market:
        q = q.filter(CustomPriceAlert.market == market.upper())
    if active_only:
        q = q.filter(CustomPriceAlert.active == True)
    alerts = q.order_by(CustomPriceAlert.created_at.desc()).all()
    return [
        {
            "id": a.id,
            "symbol": a.symbol,
            "market": a.market,
            "target_price": a.target_price,
            "condition": a.condition,
            "notes": a.notes,
            "triggered": a.triggered,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            "triggered_price": a.triggered_price,
            "active": a.active,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/alerts/custom")
def create_custom_alert(
    payload: CustomPriceAlertCreate,
    db: Session = Depends(get_db),
):
    """Creates a user-defined price target alert for the active monitoring loop."""
    cond = payload.condition.upper().strip()
    if cond not in ("ABOVE", "BELOW"):
        raise HTTPException(status_code=400, detail="Condition must be 'ABOVE' or 'BELOW'")
    if payload.target_price <= 0:
        raise HTTPException(status_code=400, detail="Target price must be strictly positive")

    alert = CustomPriceAlert(
        symbol=payload.symbol.strip().upper(),
        market=payload.market.strip().upper(),
        target_price=payload.target_price,
        condition=cond,
        notes=payload.notes.strip() if payload.notes else None,
        active=True,
        triggered=False,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return {
        "status": "CREATED",
        "id": alert.id,
        "symbol": alert.symbol,
        "market": alert.market,
        "target_price": alert.target_price,
        "condition": alert.condition,
    }


@router.delete("/alerts/custom/{alert_id}")
def delete_custom_alert(
    alert_id: int,
    db: Session = Depends(get_db),
):
    """Deletes a custom price alert."""
    alert = db.query(CustomPriceAlert).filter(CustomPriceAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Custom alert not found")
    db.delete(alert)
    db.commit()
    return {"status": "DELETED", "id": alert_id}


@router.get("/market/pulse")
def get_market_pulse(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Computes real-time/EOD Market Breadth and Sector Heatmap from local daily bars."""
    market = market.upper()
    mkt_cfg = settings.get_market_config(market)
    universe_stocks = universe_manager.load_universe(market)
    stock_map = {s.symbol: s for s in universe_stocks}
    symbols = list(stock_map.keys())

    # Get index regime
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=400)
    index_bars = provider_manager.get_daily_bars([mkt_cfg.index_symbol], start_date, today, market=market, db=db)
    index_df = index_bars.get(mkt_cfg.index_symbol)
    regime = evaluate_market_regime(index_df, market=market)

    if not symbols:
        return {
            "market": market,
            "regime": regime.model_dump(),
            "breadth": {
                "total_tracked": 0,
                "pct_above_50_sma": 0.0,
                "pct_above_200_sma": 0.0,
                "advancers": 0,
                "decliners": 0,
                "unchanged": 0,
                "new_52w_highs": 0,
                "new_52w_lows": 0,
            },
            "sectors": [],
        }

    # Fetch daily bars from DB for universe
    cutoff_date = today - datetime.timedelta(days=380)
    bars_rows = (
        db.query(DailyBar)
        .filter(DailyBar.symbol.in_(symbols), DailyBar.date >= cutoff_date)
        .order_by(DailyBar.symbol, DailyBar.date.asc())
        .all()
    )

    by_symbol: Dict[str, List[DailyBar]] = {}
    for b in bars_rows:
        by_symbol.setdefault(b.symbol, []).append(b)

    total_tracked = 0
    count_above_50 = 0
    count_above_200 = 0
    advancers = 0
    decliners = 0
    unchanged = 0
    highs_52w = 0
    lows_52w = 0

    sector_stats: Dict[str, Dict[str, Any]] = {}

    for sym, s_obj in stock_map.items():
        s_bars = by_symbol.get(sym, [])
        if len(s_bars) < 5:
            continue

        total_tracked += 1
        last_b = s_bars[-1]
        c0 = last_b.close

        # 1D Return
        c1 = s_bars[-2].close if len(s_bars) >= 2 else c0
        ret_1d = ((c0 - c1) / c1 * 100.0) if c1 > 0 else 0.0
        if ret_1d > 0.05:
            advancers += 1
        elif ret_1d < -0.05:
            decliners += 1
        else:
            unchanged += 1

        # 1W Return (approx 5 bars)
        c5 = s_bars[-5].close if len(s_bars) >= 5 else s_bars[0].close
        ret_1w = ((c0 - c5) / c5 * 100.0) if c5 > 0 else 0.0

        # 1M Return (approx 21 bars)
        c21 = s_bars[-21].close if len(s_bars) >= 21 else s_bars[0].close
        ret_1m = ((c0 - c21) / c21 * 100.0) if c21 > 0 else 0.0

        # SMA 50
        closes = [b.close for b in s_bars]
        above_50 = False
        if len(closes) >= 50:
            sma50 = sum(closes[-50:]) / 50.0
            if c0 > sma50:
                count_above_50 += 1
                above_50 = True
        elif closes:
            if c0 > (sum(closes) / len(closes)):
                count_above_50 += 1
                above_50 = True

        # SMA 200
        if len(closes) >= 200:
            sma200 = sum(closes[-200:]) / 200.0
            if c0 > sma200:
                count_above_200 += 1
        elif closes:
            if c0 > (sum(closes) / len(closes)):
                count_above_200 += 1

        # 52w High / Low (within 2%)
        max_c = max(closes)
        min_c = min(closes)
        if c0 >= (max_c * 0.98):
            highs_52w += 1
        if c0 <= (min_c * 1.02):
            lows_52w += 1

        # Sector grouping
        sec = s_obj.sector or "General"
        if sec not in sector_stats:
            sector_stats[sec] = {
                "sector": sec,
                "stocks": [],
                "returns_1d": [],
                "returns_1w": [],
                "returns_1m": [],
                "above_50_count": 0,
            }
        sec_d = sector_stats[sec]
        sec_d["stocks"].append({"symbol": sym, "return_1d": round(ret_1d, 2), "close": c0})
        sec_d["returns_1d"].append(ret_1d)
        sec_d["returns_1w"].append(ret_1w)
        sec_d["returns_1m"].append(ret_1m)
        if above_50:
            sec_d["above_50_count"] += 1

    sectors_list = []
    for sec, d in sector_stats.items():
        n = len(d["stocks"])
        avg_1d = sum(d["returns_1d"]) / n if n > 0 else 0.0
        avg_1w = sum(d["returns_1w"]) / n if n > 0 else 0.0
        avg_1m = sum(d["returns_1m"]) / n if n > 0 else 0.0
        pct_50 = (d["above_50_count"] / n * 100.0) if n > 0 else 0.0
        sorted_stocks = sorted(d["stocks"], key=lambda x: x["return_1d"], reverse=True)
        leader = sorted_stocks[0]["symbol"] if sorted_stocks else None

        sectors_list.append({
            "sector": sec,
            "stock_count": n,
            "return_1d": round(avg_1d, 2),
            "return_1w": round(avg_1w, 2),
            "return_1m": round(avg_1m, 2),
            "pct_above_50": round(pct_50, 1),
            "leader": leader,
        })

    sectors_list.sort(key=lambda s: s["return_1d"], reverse=True)

    pct_above_50 = round((count_above_50 / total_tracked * 100.0), 1) if total_tracked > 0 else 0.0
    pct_above_200 = round((count_above_200 / total_tracked * 100.0), 1) if total_tracked > 0 else 0.0

    return {
        "market": market,
        "regime": regime.model_dump(),
        "breadth": {
            "total_tracked": total_tracked,
            "pct_above_50_sma": pct_above_50,
            "pct_above_200_sma": pct_above_200,
            "advancers": advancers,
            "decliners": decliners,
            "unchanged": unchanged,
            "new_52w_highs": highs_52w,
            "new_52w_lows": lows_52w,
        },
        "sectors": sectors_list,
    }


@router.get("/search")
def search_symbols(
    q: str = Query(..., min_length=1),
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Fast keyboard symbol search scoped to the active market with cached quotes."""
    query_str = q.strip().upper()
    market = market.upper()

    universe_stocks = universe_manager.load_universe(market)
    matches = []
    seen = set()

    # Search in universe definitions first
    for s in universe_stocks:
        if query_str in s.symbol.upper() or query_str in s.name.upper():
            matches.append({
                "symbol": s.symbol,
                "name": s.name,
                "sector": s.sector,
                "market": market,
            })
            seen.add(s.symbol)
            if len(matches) >= 15:
                break

    # Also search Instrument database rows
    if len(matches) < 15:
        db_instrs = (
            db.query(Instrument)
            .filter(
                Instrument.market == market,
                (Instrument.symbol.ilike(f"%{query_str}%") | Instrument.name.ilike(f"%{query_str}%"))
            )
            .limit(15)
            .all()
        )
        for di in db_instrs:
            if di.symbol not in seen:
                matches.append({
                    "symbol": di.symbol,
                    "name": di.name or di.symbol,
                    "sector": di.sector or "General",
                    "market": market,
                })
                seen.add(di.symbol)

    # Attach latest quote price if available in LatestQuote table
    if matches:
        match_syms = [m["symbol"] for m in matches]
        lq_rows = (
            db.query(LatestQuote)
            .filter(LatestQuote.symbol.in_(match_syms), LatestQuote.market == market)
            .all()
        )
        lq_map = {r.symbol: r for r in lq_rows}
        for m in matches:
            lq = lq_map.get(m["symbol"])
            if lq:
                m["price"] = lq.price
                m["freshness"] = lq.freshness
                m["realtime"] = lq.realtime
                m["source"] = lq.provider
            else:
                m["price"] = None
                m["freshness"] = "UNAVAILABLE"
                m["realtime"] = False
                m["source"] = None

    return matches[:10]

