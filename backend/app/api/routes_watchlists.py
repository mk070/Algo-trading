import datetime
import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.symbol_normalizer import SymbolResolution, symbol_normalizer
from app.models import Position, Signal, Watchlist, WatchlistItem
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateWatchlistRequest(BaseModel):
    name: str
    market: str = "IN"
    source: Optional[str] = "APP_MANUAL"


class AddWatchlistItemRequest(BaseModel):
    symbol: str
    exchange: Optional[str] = "NSE"
    notes: Optional[str] = None
    source: Optional[str] = "APP_MANUAL"


class DiffWatchlistRequest(BaseModel):
    raw_text: str
    source_tag: Optional[str] = "ZERODHA_MANUAL_IMPORT"


class ReimportWatchlistRequest(BaseModel):
    raw_text: str
    mode: str = "merge"  # merge, replace
    source_tag: Optional[str] = "ZERODHA_MANUAL_IMPORT"


def _extract_tokens_from_text(raw_text: str) -> List[str]:
    """Splits raw text by comma, semicolon, space, or newline into clean tokens."""
    # Replace separators with newlines
    normalized = raw_text.replace(",", "\n").replace(";", "\n").replace("\t", "\n")
    tokens = []
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip CSV header lines
        lower_line = line.lower()
        if lower_line.startswith("symbol") or lower_line.startswith("tradingsymbol") or lower_line.startswith("ticker"):
            continue
        # Split by spaces if multiple symbols were space-separated
        parts = line.split()
        for p in parts:
            p_clean = p.strip()
            if p_clean:
                tokens.append(p_clean)
    return tokens[:500]  # Respect 500 symbol safety cap


@router.get("/watchlists")
def get_watchlists(
    market: str = Query("IN", pattern="^(IN|US)$"),
    db: Session = Depends(get_db),
):
    """Returns all active watchlists for the given market with provenance and staleness status."""
    market = market.upper()
    lists = (
        db.query(Watchlist)
        .filter(Watchlist.market == market, Watchlist.is_deleted == False)
        .order_by(Watchlist.is_default.desc(), Watchlist.created_at.asc())
        .all()
    )

    if not lists:
        default_wl = Watchlist(
            name="Default Focus",
            market=market,
            source="APP_MANUAL",
            is_default=True,
            imported_at=datetime.datetime.utcnow(),
            last_reimported_at=datetime.datetime.utcnow(),
        )
        db.add(default_wl)
        db.commit()
        db.refresh(default_wl)

        # Seed initial core universe stocks
        seed_syms = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"] if market == "IN" else ["AAPL", "NVDA", "MSFT", "AMZN"]
        for s in seed_syms:
            item = WatchlistItem(
                watchlist_id=default_wl.id,
                symbol=s,
                raw_input=s,
                status="RESOLVED",
                exchange="NSE" if market == "IN" else "NASDAQ",
                source="APP_MANUAL",
                notes="Top universe market leader",
            )
            db.add(item)
        db.commit()
        lists = [default_wl]

    now = datetime.datetime.now(datetime.timezone.utc)
    results = []
    for wl in lists:
        count = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.watchlist_id == wl.id, WatchlistItem.is_deleted == False)
            .count()
        )
        last_date = wl.last_reimported_at or wl.imported_at or wl.created_at
        if last_date:
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=datetime.timezone.utc)
            age_days = (now - last_date).days
        else:
            age_days = 0
        is_stale = age_days > 7

        results.append(
            {
                "id": wl.id,
                "name": wl.name,
                "market": wl.market,
                "source": wl.source or "APP_MANUAL",
                "is_default": wl.is_default,
                "items_count": count,
                "imported_at": wl.imported_at.isoformat() if wl.imported_at else None,
                "last_reimported_at": wl.last_reimported_at.isoformat() if wl.last_reimported_at else None,
                "age_days": age_days,
                "is_stale": is_stale,
                "provenance_label": "Manually imported Zerodha watchlist (not synchronised)"
                if wl.source == "ZERODHA_MANUAL_IMPORT"
                else "Manual App Watchlist",
            }
        )

    return results


@router.post("/watchlists")
def create_watchlist(
    req: CreateWatchlistRequest,
    db: Session = Depends(get_db),
):
    """Creates a new named watchlist."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Watchlist name cannot be empty")

    wl = Watchlist(
        name=name,
        market=req.market.upper(),
        source=req.source or "APP_MANUAL",
        is_default=False,
        imported_at=datetime.datetime.utcnow(),
        last_reimported_at=datetime.datetime.utcnow(),
    )
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return {
        "status": "SUCCESS",
        "watchlist": {
            "id": wl.id,
            "name": wl.name,
            "market": wl.market,
            "source": wl.source,
            "is_default": wl.is_default,
        },
    }


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int,
    db: Session = Depends(get_db),
):
    """Soft deletes a watchlist and its items, keeping history and signals intact."""
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    if wl.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default watchlist")

    now = datetime.datetime.utcnow()
    wl.is_deleted = True
    db.query(WatchlistItem).filter(WatchlistItem.watchlist_id == watchlist_id).update(
        {"is_deleted": True, "removed_at": now}
    )
    db.commit()
    return {"status": "DELETED", "id": watchlist_id}


@router.get("/watchlists/{watchlist_id}/items")
def get_watchlist_items(
    watchlist_id: int,
    db: Session = Depends(get_db),
):
    """Returns watchlist items with live prices, % day change, opportunity states,
    and the first failing check for stocks with no setup.
    """
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.is_deleted == False).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.is_deleted == False)
        .order_by(WatchlistItem.added_at.desc())
        .all()
    )

    symbols = [it.symbol for it in items]
    quotes = provider_manager.get_quotes(symbols, market=wl.market)

    # Check for active signals in DB to associate trigger, stop, and failure reasons
    active_signals = (
        db.query(Signal)
        .filter(Signal.symbol.in_(symbols), Signal.market == wl.market)
        .order_by(Signal.created_at.desc())
        .all()
    )
    sig_map = {s.symbol: s for s in active_signals}

    # Check for open positions to show "Already Held"
    open_positions = (
        db.query(Position.symbol)
        .filter(Position.market == wl.market, Position.status == "OPEN")
        .all()
    )
    held_symbols = set(row[0] for row in open_positions)

    now = datetime.datetime.now(datetime.timezone.utc)
    last_date = wl.last_reimported_at or wl.imported_at or wl.created_at
    if last_date:
        if last_date.tzinfo is None:
            last_date = last_date.replace(tzinfo=datetime.timezone.utc)
        age_days = (now - last_date).days
    else:
        age_days = 0

    results = []
    for it in items:
        sym = it.symbol
        q = quotes.get(sym) or quotes.get(f"BSE:{sym}") or quotes.get(f"NSE:{sym}") or quotes.get(sym.replace("BSE:", "").replace("NSE:", ""))
        sig = sig_map.get(sym)

        last_price = (q.price or q.last_price) if q else (sig.trigger if sig else None)
        day_change = 0.0
        if q:
            if q.change_pct is not None:
                day_change = float(q.change_pct)
            elif hasattr(q, "pct_change"):
                day_change = float(q.pct_change)
            elif getattr(q, "prev_close", None) and float(q.prev_close) > 0 and q.price:
                day_change = round(((q.price - q.prev_close) / q.prev_close) * 100.0, 2)

        setup = sig.setup if sig else "MONITORING"
        state = sig.state if sig else "WATCHLIST"
        rs_rank = sig.rs_rank if sig else 0.50

        # Only valid setups have an actionable trigger and stop loss
        has_valid_setup = sig is not None and sig.state not in ("NO_SETUP", "MONITORING", "WATCHLIST") and sig.setup in ("VCP", "BREAKOUT", "PULLBACK") and (sig.trigger or 0) > 0
        trigger = sig.trigger if (has_valid_setup and sig) else None
        stop = sig.stop if (has_valid_setup and sig) else None

        # Check if already held
        is_held = sym in held_symbols
        if is_held:
            state = "ALREADY_HELD"

        # Extract first failing check if no setup
        failing_check = None
        if sig and sig.reasons_json:
            try:
                reasons = json.loads(sig.reasons_json)
                if reasons and isinstance(reasons, list):
                    clean_reasons = [r for r in reasons if isinstance(r, str) and r.strip() and "price 0.00" not in r]
                    failing_check = clean_reasons[0] if clean_reasons else None
            except Exception:
                pass

        dist_trigger = (
            ((trigger - last_price) / trigger * 100.0)
            if (has_valid_setup and trigger and trigger > 0 and last_price and last_price > 0)
            else None
        )
        dist_stop = (
            ((last_price - stop) / last_price * 100.0)
            if (has_valid_setup and stop and stop > 0 and last_price and last_price > 0)
            else None
        )

        # Categorize opportunity filter state
        # Filter States: ALL | NEAR_BREAKOUT | VALID_SETUP | WAITING_CONFIRMATION | BLOCKED | NO_SETUP | ALREADY_HELD
        filter_category = "NO_SETUP"
        if is_held:
            filter_category = "ALREADY_HELD"
        elif state in ("TRIGGERED_PROVISIONAL", "TRIGGERED_CONFIRMED", "BUY_CONFIRMED"):
            filter_category = "WAITING_CONFIRMATION"
        elif state == "APPROACHING" or (dist_trigger is not None and 0 <= dist_trigger <= 2.5):
            filter_category = "NEAR_BREAKOUT"
        elif sig and sig.setup in ("VCP", "PULLBACK"):
            filter_category = "VALID_SETUP"
        elif state in ("INVALIDATED", "EXTENDED", "BLOCKED"):
            filter_category = "BLOCKED"

        results.append(
            {
                "id": it.id,
                "symbol": sym,
                "exchange": it.exchange,
                "notes": it.notes,
                "source": it.source,
                "last_price": round(last_price, 2) if last_price else None,
                "day_change_pct": round(day_change, 2) if day_change is not None else 0.0,
                "day_volume": q.day_volume if q else 0,
                "freshness": q.freshness if q else "UNAVAILABLE",
                "is_realtime": q.is_realtime if q else False,
                "setup": setup,
                "state": state,
                "filter_category": filter_category,
                "rs_rank": round(rs_rank, 2),
                "trigger": round(trigger, 2) if trigger else None,
                "stop": round(stop, 2) if stop else None,
                "dist_trigger_pct": round(dist_trigger, 2) if dist_trigger is not None else None,
                "dist_stop_pct": round(dist_stop, 2) if dist_stop is not None else None,
                "is_already_held": is_held,
                "first_failing_check": failing_check,
                "added_at": it.added_at.isoformat() if it.added_at else None,
            }
        )

    return {
        "watchlist": {
            "id": wl.id,
            "name": wl.name,
            "market": wl.market,
            "source": wl.source or "APP_MANUAL",
            "is_default": wl.is_default,
            "age_days": age_days,
            "is_stale": age_days > 7,
            "provenance_label": "Manually imported Zerodha watchlist (not synchronised)"
            if wl.source == "ZERODHA_MANUAL_IMPORT"
            else "Manual App Watchlist",
            "last_reimported_at": wl.last_reimported_at.isoformat() if wl.last_reimported_at else None,
        },
        "items": results,
    }


@router.post("/watchlists/{watchlist_id}/items")
def add_watchlist_item(
    watchlist_id: int,
    req: AddWatchlistItemRequest,
    db: Session = Depends(get_db),
):
    """Adds a single symbol using typeahead validation against the instrument master."""
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.is_deleted == False).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    existing_symbols = set(
        row[0]
        for row in db.query(WatchlistItem.symbol)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.is_deleted == False)
        .all()
    )

    resolution = symbol_normalizer.classify_symbol(req.symbol, market=wl.market, existing_symbols=existing_symbols)

    if resolution.status == "UNSUPPORTED":
        raise HTTPException(status_code=400, detail=resolution.reason)
    if resolution.status == "UNRESOLVED":
        raise HTTPException(status_code=400, detail=resolution.reason)
    if resolution.status == "DUPLICATE":
        return {"status": "ALREADY_EXISTS", "symbol": resolution.symbol}

    item = WatchlistItem(
        watchlist_id=watchlist_id,
        symbol=resolution.symbol,
        raw_input=req.symbol,
        status="RESOLVED",
        exchange=resolution.exchange,
        notes=req.notes,
        source=req.source or "APP_MANUAL",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "status": "ADDED",
        "item_id": item.id,
        "symbol": resolution.symbol,
        "exchange": resolution.exchange,
        "notes": item.notes,
    }


@router.delete("/watchlists/{watchlist_id}/items/{item_id}")
def remove_watchlist_item(
    watchlist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
):
    """Soft removes a symbol from the watchlist, preserving signals and trade journal history."""
    it = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.id == item_id, WatchlistItem.watchlist_id == watchlist_id)
        .first()
    )
    if not it:
        raise HTTPException(status_code=404, detail="Item not found")

    it.is_deleted = True
    it.removed_at = datetime.datetime.utcnow()
    db.commit()
    return {"status": "REMOVED", "item_id": item_id}


@router.post("/watchlists/{watchlist_id}/diff")
def preview_watchlist_diff(
    watchlist_id: int,
    req: DiffWatchlistRequest,
    db: Session = Depends(get_db),
):
    """Calculates diff preview (added, removed, unchanged) without executing changes."""
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.is_deleted == False).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    existing_items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.is_deleted == False)
        .all()
    )
    existing_symbols = {it.symbol for it in existing_items}

    raw_tokens = _extract_tokens_from_text(req.raw_text)
    classifications = symbol_normalizer.classify_batch(raw_tokens, market=wl.market)

    incoming_resolved = set()
    added_list: List[Dict] = []
    invalid_list: List[Dict] = []

    for c in classifications:
        if c.status == "RESOLVED":
            incoming_resolved.add(c.symbol)
            if c.symbol not in existing_symbols:
                added_list.append({"symbol": c.symbol, "raw": c.raw_input, "reason": c.reason})
        else:
            invalid_list.append({"raw": c.raw_input, "status": c.status, "reason": c.reason})

    unchanged_symbols = list(existing_symbols.intersection(incoming_resolved))
    removed_symbols = list(existing_symbols - incoming_resolved)

    return {
        "watchlist_id": watchlist_id,
        "watchlist_name": wl.name,
        "total_incoming": len(raw_tokens),
        "diff": {
            "added": added_list,
            "added_count": len(added_list),
            "removed": removed_symbols,
            "removed_count": len(removed_symbols),
            "unchanged": unchanged_symbols,
            "unchanged_count": len(unchanged_symbols),
            "rejected": invalid_list,
            "rejected_count": len(invalid_list),
        },
    }


@router.post("/watchlists/{watchlist_id}/import")
@router.post("/watchlists/{watchlist_id}/reimport")
def execute_watchlist_reimport(
    watchlist_id: int,
    req: ReimportWatchlistRequest,
    db: Session = Depends(get_db),
):
    """Executes watchlist re-import with confirmation.
    Modes:
      - 'merge': adds new resolved symbols, leaves existing items intact.
      - 'replace': adds new resolved symbols, soft-deletes omitted symbols.
    """
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id, Watchlist.is_deleted == False).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    now = datetime.datetime.utcnow()
    existing_items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.is_deleted == False)
        .all()
    )
    existing_map = {it.symbol: it for it in existing_items}

    raw_tokens = _extract_tokens_from_text(req.raw_text)
    classifications = symbol_normalizer.classify_batch(raw_tokens, market=wl.market)

    incoming_resolved: Set[str] = set()
    added_count = 0
    removed_count = 0

    for c in classifications:
        if c.status == "RESOLVED":
            incoming_resolved.add(c.symbol)
            if c.symbol not in existing_map:
                new_item = WatchlistItem(
                    watchlist_id=watchlist_id,
                    symbol=c.symbol,
                    raw_input=c.raw_input,
                    status="RESOLVED",
                    exchange=c.exchange,
                    source=req.source_tag or "ZERODHA_MANUAL_IMPORT",
                    notes="Manually imported from Zerodha",
                    added_at=now,
                )
                db.add(new_item)
                added_count += 1

    # In replace mode, soft delete items missing from incoming list
    if req.mode.lower() == "replace":
        for sym, item in existing_map.items():
            if sym not in incoming_resolved:
                item.is_deleted = True
                item.removed_at = now
                removed_count += 1

    # Update watchlist provenance metadata
    wl.source = req.source_tag or "ZERODHA_MANUAL_IMPORT"
    wl.last_reimported_at = now
    if not wl.imported_at:
        wl.imported_at = now

    db.commit()

    return {
        "status": "COMPLETED",
        "mode": req.mode.lower(),
        "watchlist_id": watchlist_id,
        "added_count": added_count,
        "removed_count": removed_count,
        "total_active_items": len(existing_map) + added_count - removed_count,
        "report": [r.model_dump() for r in classifications],
        "reimported_at": now.isoformat(),
    }
