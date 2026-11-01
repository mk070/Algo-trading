import asyncio
import datetime
import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import check_db_health, get_db
from app.engine.indicators import add_all_indicators
from app.engine.regime import evaluate_market_regime
from app.models import Alert, DailyBar, JobRun, SettingKV
from app.notify.dispatcher import dispatcher
from app.providers.base import ProviderHealth, Quote
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
    """Returns OHLCV bars + indicators (EMA20, SMA50, SMA200, RSI, ATR) for interactive charts."""
    clean_sym = symbol.strip().upper()
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=max(n * 2, 365))

    bars = provider_manager.get_daily_bars([clean_sym], start_date, today, market=market, db=db)
    df = bars.get(clean_sym)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No bars found for symbol {clean_sym}")

    df = add_all_indicators(df)
    recent = df.iloc[-n:]

    candle_data = []
    for _, r in recent.iterrows():
        d_val = r["date"]
        time_str = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
        candle_data.append(
            {
                "time": time_str,
                "open": round(float(r["open"]), 2),
                "high": round(float(r["high"]), 2),
                "low": round(float(r["low"]), 2),
                "close": round(float(r["close"]), 2),
                "volume": float(r["volume"]),
                "ema20": round(float(r["ema20"]), 2) if pd.notna(r.get("ema20")) else None,
                "sma50": round(float(r["sma50"]), 2) if pd.notna(r.get("sma50")) else None,
                "sma200": round(float(r["sma200"]), 2) if pd.notna(r.get("sma200")) else None,
                "rsi14": round(float(r["rsi14"]), 1) if pd.notna(r.get("rsi14")) else None,
                "atr14": round(float(r["atr14"]), 2) if pd.notna(r.get("atr14")) else None,
            }
        )

    return {"symbol": clean_sym, "market": market, "bars": candle_data}


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
