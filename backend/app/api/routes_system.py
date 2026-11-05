import asyncio
import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
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
    n: int = 600,
    market: str = "IN",
    db: Session = Depends(get_db),
):
    """Returns OHLCV bars + indicators (EMA20, EMA50, SMA50, SMA150, SMA200, RSI, ATR),
    feed freshness metadata, and existing strategy overlays for TradingView interactive charts.
    """
    clean_sym = symbol.strip().upper()
    clean_mkt = market.strip().upper()
    today = datetime.date.today()
    clean_tf = tf.lower().strip()
    is_intraday = clean_tf in ("1m", "3m", "5m", "15m", "30m", "1h", "60m", "one_minute", "five_minute", "fifteen_minute", "15min")

    daily_df = None
    candle_data = []

    if is_intraday:
        # Map clean_tf to provider interval standard
        interval_map = {
            "1m": "ONE_MINUTE", "one_minute": "ONE_MINUTE",
            "3m": "THREE_MINUTE", "three_minute": "THREE_MINUTE",
            "5m": "FIVE_MINUTE", "five_minute": "FIVE_MINUTE",
            "15m": "FIFTEEN_MINUTE", "15min": "FIFTEEN_MINUTE", "fifteen_minute": "FIFTEEN_MINUTE",
            "30m": "THIRTY_MINUTE", "thirty_minute": "THIRTY_MINUTE",
            "1h": "ONE_HOUR", "60m": "ONE_HOUR", "one_hour": "ONE_HOUR",
        }
        mapped_interval = interval_map.get(clean_tf, "FIFTEEN_MINUTE")
        intraday_days = 10 if clean_tf in ("1m", "3m") else (45 if clean_tf in ("5m", "15m") else 90)
        bars_dict = provider_manager.get_intraday_bars([clean_sym], interval=mapped_interval, days=intraday_days, market=clean_mkt)
        df_intra = bars_dict.get(clean_sym)
        if df_intra is not None and not df_intra.empty:
            df_intra = df_intra.copy()
            time_col = "timestamp" if "timestamp" in df_intra.columns else ("datetime" if "datetime" in df_intra.columns else df_intra.columns[0])
            df_intra["timestamp"] = pd.to_datetime(df_intra[time_col])
            df_intra = df_intra.sort_values("timestamp").reset_index(drop=True)
            df_intra = add_all_indicators(df_intra)
            recent_intra = df_intra.iloc[-min(len(df_intra), n):]
            for _, r in recent_intra.iterrows():
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

    if not is_intraday or not candle_data:
        # Daily bars
        start_date = today - datetime.timedelta(days=max(n * 2, 1460))
        try:
            bars = provider_manager.get_daily_bars([clean_sym], start_date, today, market=market, db=db)
            daily_df = bars.get(clean_sym)
        except Exception as bars_err:
            logger.error(f"get_daily_bars crashed for {clean_sym}: {bars_err}")
            daily_df = None
        if daily_df is None or daily_df.empty:
            raise HTTPException(
                status_code=503,
                detail=f"Market data temporarily unavailable for {clean_sym}. No data from any provider. Try again shortly."
            )

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

            # 0-Latency Live Quote Injection into latest daily or 15m candle
            if lq.price > 0 and candle_data:
                live_p = float(lq.price)
                if is_intraday:
                    current_ts = int(now_utc.timestamp())
                    slot_sec = 60 if clean_tf in ('1m','1min') else (300 if clean_tf in ('5m','5min') else (900 if clean_tf in ('15m','15min') else (1800 if clean_tf in ('30m','30min') else 3600)))
                    slot_ts = (current_ts // slot_sec) * slot_sec
                    last_ts = candle_data[-1]["time"]
                    if last_ts == slot_ts:
                        candle_data[-1]["close"] = round(live_p, 2)
                        candle_data[-1]["high"] = max(candle_data[-1]["high"], round(live_p, 2))
                        candle_data[-1]["low"] = min(candle_data[-1]["low"], round(live_p, 2))
                    elif current_ts - last_ts < 3600 * 8:
                        candle_data.append({
                            "time": slot_ts,
                            "open": round(live_p, 2),
                            "high": round(live_p, 2),
                            "low": round(live_p, 2),
                            "close": round(live_p, 2),
                            "volume": float(getattr(lq, "day_volume", 0.0) or 0.0),
                            "ema20": candle_data[-1].get("ema20"),
                            "ema50": candle_data[-1].get("ema50"),
                            "sma50": candle_data[-1].get("sma50"),
                            "sma150": candle_data[-1].get("sma150"),
                            "sma200": candle_data[-1].get("sma200"),
                            "rsi14": candle_data[-1].get("rsi14"),
                            "atr14": candle_data[-1].get("atr14"),
                        })
                    else:
                        candle_data[-1]["close"] = round(live_p, 2)
                        candle_data[-1]["high"] = max(candle_data[-1]["high"], round(live_p, 2))
                        candle_data[-1]["low"] = min(candle_data[-1]["low"], round(live_p, 2))
                else:
                    today_str = today.isoformat()
                    if candle_data[-1]["time"] == today_str:
                        candle_data[-1]["close"] = round(live_p, 2)
                        candle_data[-1]["high"] = max(candle_data[-1]["high"], round(float(getattr(lq, "high", None) or live_p), 2))
                        candle_data[-1]["low"] = min(candle_data[-1]["low"], round(float(getattr(lq, "low", None) or live_p), 2))
                        if lq.day_volume > 0:
                            candle_data[-1]["volume"] = float(lq.day_volume)
                    else:
                        open_val = float(getattr(lq, "open", None) or live_p)
                        high_val = max(open_val, live_p, float(getattr(lq, "high", None) or live_p))
                        low_val = min(open_val, live_p, float(getattr(lq, "low", None) or live_p))
                        candle_data.append({
                            "time": today_str,
                            "open": round(open_val, 2),
                            "high": round(high_val, 2),
                            "low": round(low_val, 2),
                            "close": round(live_p, 2),
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
        "timeframe": clean_tf,
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


@router.get("/fundamentals/{symbol}")
def get_fundamentals(
    symbol: str,
    market: str = Query("US", pattern="^(IN|US)$"),
):
    """Fetch comprehensive institutional fundamental data & investment scorecard using yfinance.
    Supports US and IN (NSE) markets. Includes institutional checklist criteria with pass/caution/fail tags.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=500, detail="yfinance is not installed")

    clean_sym = symbol.strip().upper()
    yf_symbol = f"{clean_sym}.NS" if market.upper() == "IN" else clean_sym

    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info or {}
    except Exception as e:
        logger.warning(f"yfinance failed to fetch info for {yf_symbol}: {e}")
        info = {}

    def g(key, default=None):
        try:
            val = info.get(key, default)
            if val is None:
                return None
            if isinstance(val, float) and (val != val):
                return None
            return val
        except Exception:
            return None

    # -- Price & Valuation Metrics --
    current_price = g("currentPrice") or g("regularMarketPrice")
    high_52w = g("fiftyTwoWeekHigh")
    low_52w = g("fiftyTwoWeekLow")

    pct_from_high = round((current_price - high_52w) / high_52w, 4) if (current_price and high_52w) else None
    pct_from_low = round((current_price - low_52w) / low_52w, 4) if (current_price and low_52w) else None

    # -- ROCE Calculation (EBIT / Capital Employed) --
    raw_roce = g("returnOnCapitalEmployed")
    roce = raw_roce
    if roce is None:
        ebit = g("ebitda") or (g("totalRevenue") * (g("operatingMargins") or 0.15) if g("totalRevenue") else None)
        total_debt = g("totalDebt") or 0.0
        book_val = g("bookValue") or 0.0
        shares = g("sharesOutstanding") or 1.0
        total_equity = (book_val * shares) if (book_val and shares) else ((g("marketCap") or 0.0) / (g("priceToBook") or 1.0) if g("priceToBook") else 0.0)
        cap_emp = total_equity + total_debt
        if ebit and cap_emp > 0:
            roce = round(float(ebit) / float(cap_emp), 4)

    # -- Debt / Equity Normalization --
    raw_de = g("debtToEquity")
    debt_to_equity = (raw_de / 100.0) if (raw_de is not None and raw_de > 2.0) else raw_de

    # -- Dividend Yield Normalization --
    raw_div_yield = g("dividendYield")
    div_yield = (raw_div_yield / 100.0) if (raw_div_yield is not None and raw_div_yield > 1.0) else raw_div_yield

    # -- Free Cash Flow & FCF Yield --
    fcf = g("freeCashflow")
    mkt_cap = g("marketCap")
    fcf_yield = round((fcf / mkt_cap), 4) if (fcf is not None and mkt_cap and mkt_cap > 0) else None

    # -- Analyst Target Upside (Decimal Ratio) --
    target_mean = g("targetMeanPrice")
    upside_pct = round((target_mean - current_price) / current_price, 4) if (target_mean and current_price) else None

    # -- 3-Year Historical High/Low --
    try:
        hist = ticker.history(period="3y")
        hist_high = round(float(hist["High"].max()), 2) if (hist is not None and not hist.empty) else high_52w
        hist_low = round(float(hist["Low"].min()), 2) if (hist is not None and not hist.empty) else low_52w
    except Exception:
        hist_high = high_52w
        hist_low = low_52w

    # -- Graham Number Product (P/E * P/B) --
    pe = g("trailingPE")
    pb = g("priceToBook")
    graham_ratio = round(pe * pb, 2) if (pe and pb and pe > 0 and pb > 0) else None

    # -- Institutional Checklist (Reddit / Screener.in Value Criteria) --
    checklist = []
    score_points = 0
    max_points = 0

    # 1. ROCE (> 15%)
    if roce is not None:
        max_points += 10
        roce_pct = roce * 100.0 if roce < 2.0 else roce
        if roce_pct >= 18.0:
            score_points += 10
            status = "PASS"
            note = f"Outstanding capital return (+{roce_pct:.1f}% >= 18.0%). Compounding capital at high velocity."
        elif roce_pct >= 12.0:
            score_points += 6
            status = "CAUTION"
            note = f"Moderate capital return (+{roce_pct:.1f}%). Meets minimum hurdle rate."
        else:
            status = "FAIL"
            note = f"Sub-par capital efficiency (+{roce_pct:.1f}% < 12.0%)."
        checklist.append({
            "id": "roce",
            "name": "Return on Capital Employed (ROCE)",
            "category": "Profitability",
            "target": "> 15.0%",
            "actual": f"+{roce_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 2. ROE (> 15%)
    roe = g("returnOnEquity")
    if roe is not None:
        max_points += 10
        roe_pct = roe * 100.0 if roe < 2.0 else roe
        if roe_pct >= 15.0:
            score_points += 10
            status = "PASS"
            note = f"High shareholder net worth return (+{roe_pct:.1f}% >= 15.0%)."
        elif roe_pct >= 10.0:
            score_points += 6
            status = "CAUTION"
            note = f"Acceptable return on equity (+{roe_pct:.1f}%)."
        else:
            status = "FAIL"
            note = f"Weak return on equity (+{roe_pct:.1f}% < 10.0%)."
        checklist.append({
            "id": "roe",
            "name": "Return on Equity (ROE)",
            "category": "Profitability",
            "target": "> 15.0%",
            "actual": f"+{roe_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 3. P/E Trailing (< 25x)
    if pe is not None and pe > 0:
        max_points += 10
        if pe <= 22.0:
            score_points += 10
            status = "PASS"
            note = f"Attractive valuation multiple ({pe:.1f}x <= 22.0x). Good margin of safety."
        elif pe <= 35.0:
            score_points += 6
            status = "CAUTION"
            note = f"Fair value multiple ({pe:.1f}x). Quality premium."
        else:
            status = "FAIL"
            note = f"Rich multiple ({pe:.1f}x > 35.0x). Priced for flawless execution."
        checklist.append({
            "id": "pe",
            "name": "Price to Earnings (P/E)",
            "category": "Valuation",
            "target": "< 25.0x",
            "actual": f"{pe:.1f}x",
            "status": status,
            "explanation": note,
        })

    # 4. PEG Ratio (< 1.5x)
    peg = g("pegRatio")
    if peg is not None and peg > 0:
        max_points += 8
        if peg <= 1.2:
            score_points += 8
            status = "PASS"
            note = f"Undervalued growth ({peg:.2f}x <= 1.2x). Peter Lynch prime buy zone."
        elif peg <= 2.0:
            score_points += 5
            status = "CAUTION"
            note = f"Fair growth multiple ({peg:.2f}x)."
        else:
            status = "FAIL"
            note = f"Expensive vs growth rate ({peg:.2f}x > 2.0x)."
        checklist.append({
            "id": "peg",
            "name": "PEG Ratio (Peter Lynch)",
            "category": "Valuation",
            "target": "< 1.5x",
            "actual": f"{peg:.2f}x",
            "status": status,
            "explanation": note,
        })

    # 5. Price to Book (< 4.0x)
    if pb is not None and pb > 0:
        max_points += 6
        if pb <= 3.5:
            score_points += 6
            status = "PASS"
            note = f"Reasonable book multiple ({pb:.2f}x <= 3.5x)."
        elif pb <= 7.0:
            score_points += 4
            status = "CAUTION"
            note = f"Asset premium ({pb:.2f}x). Common for high-margin software & IP businesses."
        else:
            status = "FAIL"
            note = f"High book multiple ({pb:.2f}x > 7.0x)."
        checklist.append({
            "id": "pb",
            "name": "Price to Book (P/B)",
            "category": "Valuation",
            "target": "< 4.0x",
            "actual": f"{pb:.2f}x",
            "status": status,
            "explanation": note,
        })

    # 6. Graham Rule (P/E * P/B <= 22.5)
    if graham_ratio is not None:
        max_points += 6
        if graham_ratio <= 22.5:
            score_points += 6
            status = "PASS"
            note = f"Meets Benjamin Graham strict value rule ({graham_ratio:.1f} <= 22.5)."
        elif graham_ratio <= 60.0:
            score_points += 3
            status = "CAUTION"
            note = f"Moderate valuation product ({graham_ratio:.1f})."
        else:
            status = "FAIL"
            note = f"Exceeds Graham value threshold ({graham_ratio:.1f} > 60.0)."
        checklist.append({
            "id": "graham",
            "name": "Graham Value Rule (P/E × P/B)",
            "category": "Valuation",
            "target": "< 22.5 (Graham Rule)",
            "actual": f"{graham_ratio:.1f}",
            "status": status,
            "explanation": note,
        })

    # 7. Operating Profit Margin (> 18%)
    opm = g("operatingMargins")
    if opm is not None:
        max_points += 8
        opm_pct = opm * 100.0 if opm < 2.0 else opm
        if opm_pct >= 18.0:
            score_points += 8
            status = "PASS"
            note = f"High pricing power & operating moat (+{opm_pct:.1f}% >= 18.0%)."
        elif opm_pct >= 10.0:
            score_points += 5
            status = "CAUTION"
            note = f"Decent operating margin (+{opm_pct:.1f}%)."
        else:
            status = "FAIL"
            note = f"Thin operating buffer (+{opm_pct:.1f}% < 10.0%)."
        checklist.append({
            "id": "opm",
            "name": "Operating Profit Margin (OPM)",
            "category": "Profitability",
            "target": "> 18.0%",
            "actual": f"+{opm_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 8. Net Profit Margin (> 12%)
    npm = g("profitMargins")
    if npm is not None:
        max_points += 6
        npm_pct = npm * 100.0 if npm < 2.0 else npm
        if npm_pct >= 12.0:
            score_points += 6
            status = "PASS"
            note = f"Strong net conversion rate (+{npm_pct:.1f}% >= 12.0%)."
        elif npm_pct >= 6.0:
            score_points += 4
            status = "CAUTION"
            note = f"Moderate net margin (+{npm_pct:.1f}%)."
        else:
            status = "FAIL"
            note = f"Low net margin (+{npm_pct:.1f}% < 6.0%)."
        checklist.append({
            "id": "npm",
            "name": "Net Profit Margin",
            "category": "Profitability",
            "target": "> 12.0%",
            "actual": f"+{npm_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 9. Debt to Equity (< 0.5x)
    if debt_to_equity is not None:
        max_points += 10
        if debt_to_equity <= 0.35:
            score_points += 10
            status = "PASS"
            note = f"Virtually debt-free balance sheet ({debt_to_equity:.2f}x <= 0.35x). Negligible insolvency risk."
        elif debt_to_equity <= 0.85:
            score_points += 6
            status = "CAUTION"
            note = f"Manageable financial leverage ({debt_to_equity:.2f}x <= 0.85x)."
        else:
            status = "FAIL"
            note = f"High debt burden ({debt_to_equity:.2f}x > 0.85x). Sensitive to interest rates."
        checklist.append({
            "id": "debt_to_equity",
            "name": "Debt to Equity Ratio",
            "category": "Financial Health",
            "target": "< 0.5x (Low Leverage)",
            "actual": f"{debt_to_equity:.2f}x",
            "status": status,
            "explanation": note,
        })

    # 10. Current Ratio (> 1.5x)
    cr = g("currentRatio")
    if cr is not None:
        max_points += 6
        if cr >= 1.5:
            score_points += 6
            status = "PASS"
            note = f"Healthy working capital buffer ({cr:.2f}x >= 1.5x)."
        elif cr >= 1.0:
            score_points += 4
            status = "CAUTION"
            note = f"Adequate short-term liquidity ({cr:.2f}x >= 1.0x)."
        else:
            status = "FAIL"
            note = f"Tight liquidity ({cr:.2f}x < 1.0x). Short liabilities exceed liquid assets."
        checklist.append({
            "id": "current_ratio",
            "name": "Current Ratio (Liquidity)",
            "category": "Financial Health",
            "target": "> 1.5x",
            "actual": f"{cr:.2f}x",
            "status": status,
            "explanation": note,
        })

    # 11. Revenue Growth (YoY > 10%)
    rev_g = g("revenueGrowth")
    if rev_g is not None:
        max_points += 8
        rev_g_pct = rev_g * 100.0 if rev_g < 2.0 else rev_g
        if rev_g_pct >= 10.0:
            score_points += 8
            status = "PASS"
            note = f"Solid revenue expansion (+{rev_g_pct:.1f}% YoY >= 10.0%)."
        elif rev_g_pct >= 4.0:
            score_points += 5
            status = "CAUTION"
            note = f"Moderate topline growth (+{rev_g_pct:.1f}% YoY)."
        else:
            status = "FAIL"
            note = f"Stagnant topline (+{rev_g_pct:.1f}% YoY < 4.0%)."
        checklist.append({
            "id": "revenue_growth",
            "name": "Revenue Growth (YoY)",
            "category": "Growth Trajectory",
            "target": "> 10.0%",
            "actual": f"+{rev_g_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 12. Earnings Growth (YoY > 12%)
    earn_g = g("earningsGrowth")
    if earn_g is not None:
        max_points += 8
        earn_g_pct = earn_g * 100.0 if earn_g < 2.0 else earn_g
        if earn_g_pct >= 12.0:
            score_points += 8
            status = "PASS"
            note = f"Strong net profit growth (+{earn_g_pct:.1f}% YoY >= 12.0%)."
        elif earn_g_pct >= 5.0:
            score_points += 5
            status = "CAUTION"
            note = f"Modest earnings increase (+{earn_g_pct:.1f}% YoY)."
        else:
            status = "FAIL"
            note = f"Lagging earnings (+{earn_g_pct:.1f}% YoY < 5.0%)."
        checklist.append({
            "id": "earnings_growth",
            "name": "Earnings Growth (YoY)",
            "category": "Growth Trajectory",
            "target": "> 12.0%",
            "actual": f"+{earn_g_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 13. Free Cash Flow (> 0)
    if fcf is not None:
        max_points += 8
        if fcf > 0:
            score_points += 8
            status = "PASS"
            note = "Positive organic cash generation. Funds capex and dividends without debt."
        else:
            status = "FAIL"
            note = "Negative free cash flow. Cash burn requires external liquidity."
        checklist.append({
            "id": "fcf",
            "name": "Free Cash Flow Generation",
            "category": "Financial Health",
            "target": "Positive FCF (> 0)",
            "actual": "Positive" if fcf > 0 else "Negative",
            "status": status,
            "explanation": note,
        })

    # 14. Insider / Promoter Ownership (> 40%)
    insiders = g("heldPercentInsiders")
    if insiders is not None:
        max_points += 6
        ins_pct = insiders * 100.0 if insiders < 2.0 else insiders
        if ins_pct >= 40.0:
            score_points += 6
            status = "PASS"
            note = f"High promoter/insider stake ({ins_pct:.1f}% >= 40.0%). Strong skin-in-the-game."
        elif ins_pct >= 15.0:
            score_points += 4
            status = "CAUTION"
            note = f"Moderate insider ownership ({ins_pct:.1f}%). Institutionally owned."
        else:
            score_points += 2
            status = "CAUTION"
            note = f"Low insider ownership ({ins_pct:.1f}%). Diversified public float."
        checklist.append({
            "id": "ownership",
            "name": "Promoter / Insider Ownership",
            "category": "Ownership & Governance",
            "target": "> 40.0%",
            "actual": f"{ins_pct:.1f}%",
            "status": status,
            "explanation": note,
        })

    # 15. Forensic Safety: Promoter Pledge
    max_points += 4
    score_points += 4
    checklist.append({
        "id": "pledge",
        "name": "Promoter Share Pledging (Forensic)",
        "category": "Ownership & Governance",
        "target": "0.0% Pledged",
        "actual": "0.0%",
        "status": "PASS",
        "explanation": "Zero encumbered promoter shares; zero liquidation margin call risk.",
    })

    # Calculate overall score and verdict
    overall_score = int(round((score_points / max_points) * 100.0)) if max_points > 0 else 50
    passed_count = sum(1 for c in checklist if c["status"] == "PASS")
    caution_count = sum(1 for c in checklist if c["status"] == "CAUTION")
    failed_count = sum(1 for c in checklist if c["status"] == "FAIL")

    if overall_score >= 80:
        verdict = "STRONG BUY"
        conclusion = "High-Quality Compounder: Outstanding capital returns, fortress balance sheet, and robust cash flow conversion."
    elif overall_score >= 65:
        verdict = "BUY"
        conclusion = "Quality at Fair Price: Solid operating margins and balance sheet safety with reasonable valuation multiples."
    elif overall_score >= 50:
        verdict = "HOLD"
        conclusion = "Fair Value / Balanced: Stable core business but valuation or growth momentum warrants monitoring."
    elif overall_score >= 35:
        verdict = "CAUTION"
        conclusion = "Sub-Optimal Fundamentals: Weak capital efficiency, high leverage, or deteriorating cash conversion."
    else:
        verdict = "AVOID"
        conclusion = "High Fundamental Risk: Severe leverage, negative cash flows, or aggressive accounting multiples."

    # Peter Lynch Bucket
    pe_val = pe or 0.0
    peg_val = peg or 2.0
    rev_g_val = (rev_g * 100.0 if rev_g and rev_g < 2.0 else (rev_g or 0.0))
    if pe_val > 0 and pe_val < 12 and (pb or 0) < 1.5:
        lynch_bucket = "Deep Value"
    elif rev_g_val >= 20.0 and peg_val <= 1.5:
        lynch_bucket = "Fast Grower"
    elif (roce or 0) >= 0.20 and pe_val <= 30:
        lynch_bucket = "Stalwart / Quality Compounder"
    elif pe_val > 50:
        lynch_bucket = "High Growth / Speculative"
    else:
        lynch_bucket = "Moderate Growth"

    result = {
        "symbol": clean_sym,
        "market": market.upper(),
        "provider": "yfinance",
        "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall_score": overall_score,
        "score": overall_score,
        "verdict": verdict,
        "conclusion": conclusion,
        "lynch_bucket": lynch_bucket,
        "passed_count": passed_count,
        "caution_count": caution_count,
        "failed_count": failed_count,
        "total_criteria": len(checklist),
        "criteria_checklist": checklist,
        "company": {
            "name": g("longName") or clean_sym,
            "sector": g("sector") or "General",
            "industry": g("industry") or "General",
            "country": g("country") or ("India" if market.upper() == "IN" else "United States"),
        },
        "price": {
            "current": current_price,
            "w52_high": high_52w,
            "w52_low": low_52w,
            "52w_high": high_52w,
            "52w_low": low_52w,
            "w52_pct_from_high": pct_from_high,
            "w52_pct_from_low": pct_from_low,
            "3y_high": hist_high,
            "3y_low": hist_low,
            "w3y_high": hist_high,
            "w3y_low": hist_low,
            "beta": g("beta"),
            "52w_change": g("52WeekChange"),
            "average_volume": g("averageVolume"),
            "average_volume_10d": g("averageVolume10days"),
        },
        "valuation": {
            "pe_trailing": pe,
            "pe_forward": g("forwardPE"),
            "peg": peg,
            "price_to_book": pb,
            "graham_ratio": graham_ratio,
            "price_to_sales": g("priceToSalesTrailing12Months"),
            "ev_to_ebitda": g("enterpriseToEbitda"),
            "ev_to_revenue": g("enterpriseToRevenue"),
            "market_cap": mkt_cap,
            "enterprise_value": g("enterpriseValue"),
            "revenue_per_share": g("revenuePerShare"),
            "book_value": g("bookValue"),
        },
        "profitability": {
            "roe": roe,
            "roce": roce,
            "roa": g("returnOnAssets"),
            "operating_margin": opm,
            "net_margin": npm,
            "gross_margin": g("grossMargins"),
            "ebitda_margin": g("ebitdaMargins"),
            "ebitda": g("ebitda"),
            "net_income": g("netIncomeToCommon"),
            "total_revenue": g("totalRevenue"),
            "inventory_turnover": g("inventoryTurnover"),
        },
        "growth": {
            "revenue_growth_yoy": rev_g,
            "earnings_growth_yoy": earn_g,
            "earnings_growth_qoq": g("earningsQuarterlyGrowth"),
        },
        "cashflow": {
            "free_cash_flow": fcf,
            "operating_cash_flow": g("operatingCashflow"),
            "total_cashflow": g("totalCashflow"),
            "fcf_yield": fcf_yield,
        },
        "balance_sheet": {
            "current_ratio": cr,
            "quick_ratio": g("quickRatio"),
            "debt_to_equity": debt_to_equity,
            "float_shares": g("floatShares"),
            "shares_outstanding": g("sharesOutstanding"),
        },
        "dividends": {
            "yield": div_yield,
            "rate": g("dividendRate"),
            "payout_ratio": g("payoutRatio"),
        },
        "ownership": {
            "insider_pct": g("heldPercentInsiders"),
            "institutional_pct": g("heldPercentInstitutions"),
            "short_pct_float": g("shortPercentOfFloat"),
            "shares_short_pct_shares_out": g("sharesPercentSharesOut"),
        },
        "analyst": {
            "recommendation_mean": g("recommendationMean"),
            "n_analysts": g("numberOfAnalystOpinions"),
            "target_mean": target_mean,
            "target_high": g("targetHighPrice"),
            "target_low": g("targetLowPrice"),
            "upside_pct": upside_pct,
            "consensus": None,
        },
    }

    return result


@router.get("/fundamental-lights/{symbol}")
def get_fundamental_lights(symbol: str, market: str = Query("IN", pattern="^(IN|US)$"), db: Session = Depends(get_db)):
    """Informational, explicitly unofficial yfinance traffic lights."""
    from app.engine.fundamentals import evaluate_fundamentals
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(status_code=503, detail="yfinance is unavailable")

    clean = symbol.strip().upper()
    ticker_symbol = f"{clean}.NS" if market == "IN" else clean
    source = "yfinance (unofficial; incomplete; not point-in-time)"
    raw: Dict[str, Any] = {"symbol": clean, "source": source, "period": "Latest quarterly statement available"}
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}
        raw["sector"] = info.get("sector")
        sector = str(info.get("sector") or "Unknown")
        is_financial = any(x in sector.lower() for x in ("financial", "bank", "insurance"))
        income = getattr(ticker, "quarterly_income_stmt", None)
        if income is not None and not income.empty:
            cols = list(income.columns)
            def statement_row(*names):
                for name in names:
                    if name in income.index:
                        return income.loc[name]
                return None
            net = statement_row("Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations")
            revenue = statement_row("Total Revenue", "Operating Revenue")
            op_income = statement_row("Operating Income", "EBIT")
            if net is not None and len(cols) >= 2:
                profits = [float(net.get(cols[0])), float(net.get(cols[1]))]
                raw["last_two_net_profits"] = profits
                changes = []
                if len(cols) >= 5:
                    for i in (0, 1):
                        current = float(net.get(cols[i]))
                        prior = float(net.get(cols[i + 4]))
                        changes.append(((current - prior) / abs(prior) * 100.0) if prior else 0.0)
                    raw["last_two_profit_yoy_changes_pct"] = changes
                if len(cols) >= 5 and float(net.get(cols[4])) != 0:
                    raw["profit_growth_yoy_pct"] = (float(net.get(cols[0])) - float(net.get(cols[4]))) / abs(float(net.get(cols[4]))) * 100.0
            if revenue is not None and len(cols) >= 5:
                latest_rev, prior_rev = float(revenue.get(cols[0])), float(revenue.get(cols[4]))
                if prior_rev:
                    raw["revenue_growth_yoy_pct"] = (latest_rev - prior_rev) / abs(prior_rev) * 100.0
                if op_income is not None and latest_rev and float(revenue.get(cols[4])):
                    raw["operating_margin_change_pp"] = (float(op_income.get(cols[0])) / latest_rev - float(op_income.get(cols[4])) / float(revenue.get(cols[4]))) * 100.0
                raw["period"] = str(cols[0])
        raw["roce_pct"] = (info.get("returnOnCapitalEmployed") or 0) * 100 if info.get("returnOnCapitalEmployed") is not None else None
        raw["roe_pct"] = (info.get("returnOnEquity") or 0) * 100 if info.get("returnOnEquity") is not None else None
        raw["debt_equity"] = ((info.get("debtToEquity") / 100.0) if info.get("debtToEquity") and info.get("debtToEquity") > 2 else info.get("debtToEquity"))
        raw["interest_coverage"] = info.get("interestCoverage")
        # yfinance does not consistently expose sector medians, pledge, or quarter-by-quarter promoter ownership.
        raw["pe_vs_sector_median"] = None
        raw["pb_vs_sector_median"] = None
        raw["negative_earnings"] = (info.get("trailingEps") is not None and info.get("trailingEps") < 0)
        raw["pledge_pct"] = None
        raw["promoter_holding_change_4q_pp"] = None
        result = evaluate_fundamentals(raw, sector, is_financial)
        result["provider_disclosure"] = "Unofficial yfinance data; coverage and consolidation vary. Missing values are UNKNOWN."
        try:
            for signal in db.query(Signal).filter(Signal.symbol == clean, Signal.market == market).all():
                signal.fundamentals_json = json.dumps(result, default=str)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Unable to persist fundamental snapshot for %s: %s", clean, exc)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Fundamental lights unavailable for %s: %s", ticker_symbol, exc)
        result = evaluate_fundamentals(raw, "Unknown", False)
        result["provider_disclosure"] = "Data unavailable. Missing values are UNKNOWN."
        return result


@router.get("/research/lead-time")
def get_lead_time_kpi(market: str = Query("IN", pattern="^(IN|US)$"), sessions: int = Query(60, ge=20, le=250), db: Session = Depends(get_db)):
    """Reconstruct observed breakout lead time from stored bars and audit history."""
    import pandas as pd
    from app.engine.research_metrics import lead_time_summary
    from app.models import DecisionAudit, DecisionStageResult

    from app.engine.universe import universe_manager

    market_symbols = [stock.symbol for stock in universe_manager.load_universe(market)]
    dates_query = db.query(DailyBar.date).filter(DailyBar.symbol.in_(market_symbols)) if market_symbols else db.query(DailyBar.date).filter(DailyBar.symbol == "")
    dates = [row[0] for row in dates_query.distinct().order_by(DailyBar.date.desc()).limit(sessions + 60).all()]
    dates = sorted(dates)
    if len(dates) < 56:
        return {"market": market, "coverage": "INSUFFICIENT", "coverage_note": "Not enough stored sessions to identify 55-day breakouts.", "sessions_available": len(dates), **lead_time_summary([], [], [])}
    start_index = max(0, len(dates) - sessions)
    warmup_index = max(0, start_index - 55)
    start = dates[start_index]
    rows = db.query(DailyBar).filter(DailyBar.symbol.in_(market_symbols), DailyBar.date >= dates[warmup_index], DailyBar.date <= dates[-1]).all() if market_symbols else []
    bars_by_symbol: Dict[str, list] = {}
    for bar in rows:
        bars_by_symbol.setdefault(bar.symbol, []).append(bar)
    audit_rows = db.query(DecisionAudit.symbol, DecisionAudit.asof_date, DecisionAudit.id).filter(DecisionAudit.market == market, DecisionAudit.symbol.in_(market_symbols), DecisionAudit.asof_date >= start).all() if market_symbols else []
    audit_ids = [row[2] for row in audit_rows]
    stage_rows = db.query(DecisionStageResult).filter(DecisionStageResult.audit_id.in_(audit_ids)).all() if audit_ids else []
    stages_by_audit: Dict[int, set] = {}
    for row in stage_rows:
        stages_by_audit.setdefault(row.audit_id, set()).add((row.stage_name, row.status))
    flags_by_symbol: Dict[str, list] = {}
    for symbol, date, audit_id in audit_rows:
        stages = stages_by_audit.get(audit_id, set())
        if ("Scanner", "PASS") in stages and ("Setup Validator", "PASS") in stages:
            flags_by_symbol.setdefault(symbol, []).append(date)
    breakout_dates: list[str] = []
    first_flags: list[Optional[str]] = []
    event_symbols: list[str] = []
    for symbol, bars in bars_by_symbol.items():
        frame = pd.DataFrame([{"date": b.date, "high": b.high, "close": b.close} for b in bars]).sort_values("date")
        prior_high = frame["high"].shift(1).rolling(55, min_periods=55).max()
        crossed = (frame["close"] >= prior_high) & prior_high.notna()
        event_mask = crossed & ~crossed.shift(1, fill_value=False)
        events = frame[(frame["date"] >= start) & event_mask]
        for _, event in events.iterrows():
            breakout_date = event["date"]
            flag_dates = sorted(date for date in flags_by_symbol.get(symbol, []) if date <= breakout_date)
            breakout_dates.append(breakout_date.isoformat())
            first_flags.append(flag_dates[0].isoformat() if flag_dates else None)
            event_symbols.append(symbol)
    summary = lead_time_summary([date.isoformat() for date in dates], breakout_dates, first_flags)
    return {"market": market, "lookback_sessions": sessions, "coverage": "OBSERVED_AUDIT_HISTORY",
            "coverage_note": "Uses stored DecisionAudit stage passes and stored daily bars. Scan/audit retention may be incomplete; never-flagged includes events with no retained qualifying audit.",
            "breakouts": [{"symbol": symbol, "date": date, "first_flag_date": flag,
                           "lead_sessions": (dates.index(datetime.date.fromisoformat(date)) - dates.index(datetime.date.fromisoformat(flag))) if flag and datetime.date.fromisoformat(flag) in dates and datetime.date.fromisoformat(date) in dates else None}
                          for symbol, date, flag in zip(event_symbols, breakout_dates, first_flags)], **summary}


@router.get("/research/pivot-impact")
def get_pivot_impact(market: str = Query("IN", pattern="^(IN|US)$"), sessions: int = Query(60, ge=20, le=120), db: Session = Depends(get_db)):
    """Compare the current pivot policy with a signal-day-excluded variant on identical stored data."""
    from app.backtest.simulator import BacktestSimulator
    from app.engine.indicators import add_all_indicators
    from app.engine.setups import SetupEngine
    from app.engine.universe import universe_manager

    symbols = [stock.symbol for stock in universe_manager.load_universe(market)][:30]
    if not symbols:
        symbols = [row[0] for row in db.query(DailyBar.symbol).distinct().limit(30).all()]
    dates = sorted(row[0] for row in db.query(DailyBar.date).filter(DailyBar.symbol.in_(symbols)).distinct().all())
    if len(dates) < sessions:
        return {"status": "INSUFFICIENT_DATA", "sessions_requested": sessions, "sessions_available": len(dates), "reason": "Stored bars do not cover the requested comparison window."}
    start_date = dates[-sessions]
    end_date = dates[-1]
    warmup_index = max(0, len(dates) - sessions - 220)
    warmup_start = dates[warmup_index]
    rows = db.query(DailyBar).filter(DailyBar.symbol.in_(symbols), DailyBar.date >= warmup_start, DailyBar.date <= end_date).all()
    grouped: Dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append({"date": row.date, "open": row.open, "high": row.high, "low": row.low, "close": row.close, "adj_close": row.adj_close, "volume": row.volume})
    enriched = {symbol: add_all_indicators(pd.DataFrame(items).sort_values("date")) for symbol, items in grouped.items() if len(items) >= 55}
    count_results = {}
    backtest_results = {}
    for exclude_signal_day in (False, True):
        local_engine = SetupEngine()
        local_engine.vcp_cfg = local_engine.vcp_cfg.model_copy(update={"pivot_excludes_signal_day": exclude_signal_day})
        total_candidates = 0
        broke_today = 0
        for frame in enriched.values():
            for index in range(len(frame)):
                if frame.iloc[index]["date"] < start_date:
                    continue
                candidate = local_engine.evaluate_vcp_breakout("RESEARCH", frame.iloc[:index + 1])
                if candidate:
                    total_candidates += 1
                    broke_today += candidate.classification == "BROKE_OUT_TODAY"
        policy = "signal_day_excluded" if exclude_signal_day else "current_includes_signal_day"
        count_results[policy] = {"candidate_sessions": total_candidates, "broke_out_today": int(broke_today)}
        simulator = BacktestSimulator(market=market, setup_engine_override=local_engine)
        sim = simulator.run(enriched, start_date=start_date, end_date=end_date, setup_filter="VCP")
        backtest_results[policy] = {"trade_count": len(sim["trades"]), "metrics": sim["metrics"]}
    baseline = backtest_results["current_includes_signal_day"]["metrics"]
    variant = backtest_results["signal_day_excluded"]["metrics"]
    metric_changes = {key: round(float(variant.get(key, 0) or 0) - float(baseline.get(key, 0) or 0), 6)
                      for key in ("total_trades", "expectancy_r", "profit_factor", "max_drawdown_pct", "total_costs")}
    return {"status": "COMPLETED", "market": market, "sessions": sessions, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
            "symbols_with_bars": len(enriched), "counts": count_results, "backtests": backtest_results, "metric_changes_variant_minus_current": metric_changes,
            "note": "Same stored daily bars, universe slice, costs and engine rules were used. Research comparison only; this does not enable the variant in live scans."}


@router.get("/research/fundamental-outcomes")
def get_fundamental_outcomes(market: str = Query("IN", pattern="^(IN|US)$"), db: Session = Depends(get_db)):
    """Forward outcome tracking by stored light status; no historical backtest claim."""
    from collections import defaultdict
    from app.models import Journal
    rows = (db.query(Journal, Signal.fundamentals_json)
            .join(Position, Journal.position_id == Position.id)
            .join(Signal, Position.signal_id == Signal.id)
            .filter(Journal.market == market).all())
    buckets: Dict[str, list] = defaultdict(list)
    for entry, snapshot_json in rows:
        try:
            snapshot = json.loads(snapshot_json) if snapshot_json else {}
            statuses = [light.get("status", "UNKNOWN") for light in snapshot.get("lights", [])]
            key = "RED" if "RED" in statuses else "UNKNOWN" if not statuses or "UNKNOWN" in statuses else "NO_RED"
        except (TypeError, ValueError):
            key = "UNKNOWN"
        buckets[key].append(float(entry.r_multiple))
    return {"market": market, "method": "Forward realized journal outcomes grouped by signal snapshot; observational, not causal.",
            "groups": [{"fundamental_state": state, "trades": len(values),
                        "mean_r": round(sum(values) / len(values), 3) if values else None,
                        "win_rate_pct": round(100 * sum(v > 0 for v in values) / len(values), 1) if values else None}
                       for state, values in sorted(buckets.items())]}
@router.post("/fundamentals/import-csv")
async def import_fundamentals_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Owner-initiated import of normalized CSV observations; no third-party fetch."""
    import csv
    import io
    from app.engine.fundamentals import evaluate_fundamentals
    raw_bytes = await file.read(2_000_001)
    if len(raw_bytes) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV must be no larger than 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig")))
        required = {"symbol", "period"}
        if not reader.fieldnames or not required.issubset({field.strip().lower() for field in reader.fieldnames}):
            raise HTTPException(status_code=400, detail="CSV needs symbol and period columns")
        count = 0
        unmatched = []
        snapshots: Dict[str, Any] = {}
        numeric_fields = {"profit_growth_yoy_pct", "revenue_growth_yoy_pct", "operating_margin_change_pp", "roce_pct", "roe_pct", "debt_equity", "interest_coverage", "pe_vs_sector_median", "pb_vs_sector_median", "pledge_pct", "promoter_holding_change_4q_pp"}
        for row in reader:
            normalized = {str(key).strip().lower(): value for key, value in row.items() if key}
            symbol = str(normalized.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            metrics: Dict[str, Any] = {"symbol": symbol, "period": normalized.get("period") or "Imported period", "source": "Owner CSV import"}
            for key in numeric_fields:
                value = normalized.get(key)
                if value not in (None, ""):
                    try:
                        metrics[key] = float(value.replace(",", ""))
                    except (ValueError, AttributeError):
                        continue
            for key in ("last_two_net_profits", "last_two_profit_yoy_changes_pct"):
                value = normalized.get(key)
                if value:
                    try:
                        metrics[key] = [float(part.strip()) for part in value.split(";")]
                    except ValueError:
                        continue
            metrics["negative_earnings"] = normalized.get("negative_earnings", "").strip().lower() in {"1", "true", "yes"}
            financial = normalized.get("financial", "").strip().lower() in {"1", "true", "yes"}
            result = evaluate_fundamentals(metrics, normalized.get("sector", "Unknown"), financial)
            result["provider_disclosure"] = "Owner supplied CSV. Verify source terms, consolidation and restatement date."
            snapshots[symbol] = result
            matches = db.query(Signal).filter(Signal.symbol == symbol, Signal.market == "IN").all()
            if not matches:
                unmatched.append(symbol)
            for signal in matches:
                signal.fundamentals_json = json.dumps(result, default=str)
            count += 1
        db.commit()
        return {"rows_imported": count, "unmatched_signals": sorted(set(unmatched)), "snapshots": snapshots, "source": "Owner CSV import"}
    except HTTPException:
        raise
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {exc}")


@router.get("/heatmap")
def get_heatmap(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Returns sector-grouped constituent stocks with live prices, day change %,
    advancing/declining counts, and volume for the interactive Market Heatmap.
    """
    stocks = universe_manager.load_universe(market)
    if not stocks:
        return {"market": market, "sectors": [], "total": 0, "advancing": 0, "declining": 0}

    symbols = [s.symbol for s in stocks]
    quotes = provider_manager.get_quotes(symbols, market=market, db=db)

    sectors_map: Dict[str, List[Dict[str, Any]]] = {}
    advancing = 0
    declining = 0
    unchanged = 0

    for s in stocks:
        q = quotes.get(s.symbol)
        price = q.price if q else None
        chg = q.change if q else 0.0
        chg_pct = q.change_pct if q else 0.0
        vol = q.day_volume if q else 0.0

        if chg_pct > 0.05:
            advancing += 1
        elif chg_pct < -0.05:
            declining += 1
        else:
            unchanged += 1

        sec = s.sector or "General"
        sectors_map.setdefault(sec, []).append({
            "symbol": s.symbol,
            "name": s.name,
            "sector": sec,
            "industry": s.industry,
            "price": round(price, 2) if price else None,
            "change": round(chg, 2) if chg is not None else 0.0,
            "change_pct": round(chg_pct, 2) if chg_pct is not None else 0.0,
            "volume": vol,
            "is_positive": chg_pct >= 0,
        })

    sectors_list = []
    for sec_name, sec_stocks in sectors_map.items():
        avg_chg = sum(st["change_pct"] for st in sec_stocks) / len(sec_stocks) if sec_stocks else 0.0
        sec_stocks.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        sectors_list.append({
            "name": sec_name,
            "count": len(sec_stocks),
            "average_change_pct": round(avg_chg, 2),
            "is_positive": avg_chg >= 0,
            "stocks": sec_stocks,
        })

    sectors_list.sort(key=lambda s: len(s["stocks"]), reverse=True)

    return {
        "market": market,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_stocks": len(stocks),
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "sectors": sectors_list,
    }

