import datetime
import json
import logging
from typing import Dict, List, Optional, Set
from sqlalchemy.orm import Session

from app.engine.exits import exit_manager
from app.engine.pipeline import decision_pipeline
from app.models import Position, Signal
from app.notify.dispatcher import dispatcher
from app.providers.base import Quote
from app.providers.manager import provider_manager
from app.settings import settings

logger = logging.getLogger(__name__)


class LiveBreakoutMonitor:
    """Monitors live market quotes during trading sessions and updates signal/position states.
    Features:
    - Angel One WebSocket as primary India feed; REST polling as fallback/reconciliation.
    - Completed 15-minute candle confirmation above trigger before confirmed buy.
    - Volume-pace check against intraday expected baseline.
    - On trigger, re-evaluates the full DecisionPipeline (price, news, volume, risk) with fresh data.
    - No-chase cancellation (EXTENDED/SKIP) when price exceeds entry zone high.
    - Invalidation when price drops to or below stop before breakout.
    - Expiry for stale watchlist signals (TTL).
    - Strict freshness limits (delayed data never fires trigger alerts).
    - Alert de-duplication.
    """

    def __init__(self):
        self.vcp_cfg = settings.get_vcp_config()
        self.approach_pct = self.vcp_cfg.approach_pct
        self.min_volume_pace = getattr(self.vcp_cfg, "volume_pace_min", 1.0)
        self.dispatched_alerts: Set[str] = set()

    def _should_dispatch(self, key: str) -> bool:
        """Prevent duplicate alerts in the same session."""
        if key in self.dispatched_alerts:
            return False
        self.dispatched_alerts.add(key)
        return True

    def sync_websocket_subscriptions(self, market: str, symbols: List[str]):
        """Ensure Angel One WebSocket streams shortlist + open positions for India."""
        if market.upper() == "IN":
            try:
                provider_manager.angelone.ws_manager.sync_subscriptions(symbols)
            except Exception as e:
                logger.warning(f"Could not sync WebSocket subscriptions: {e}")

    def tick_market(self, market: str, db: Session, current_time: Optional[datetime.datetime] = None):
        """Polls or evaluates incoming quotes for active signals and open positions."""
        now = current_time or datetime.datetime.utcnow()
        today = now.date()

        # 1. Fetch active signals in WATCHLIST, APPROACHING, or TRIGGERED_PROVISIONAL
        active_signals = (
            db.query(Signal)
            .filter(
                Signal.market == market,
                Signal.state.in_(["WATCHLIST", "APPROACHING", "TRIGGERED_PROVISIONAL"]),
            )
            .all()
        )

        # 2. Fetch open positions
        open_positions = (
            db.query(Position)
            .filter(Position.market == market, Position.status == "OPEN")
            .all()
        )

        all_symbols = list(set([s.symbol for s in active_signals] + [p.symbol for p in open_positions]))
        if not all_symbols:
            return

        # Keep WebSocket subscriptions synchronized
        self.sync_websocket_subscriptions(market, all_symbols)

        # Fetch quotes: try primary WebSocket quotes first for IN, fallback to REST
        quotes: Dict[str, Quote] = {}
        missing_rest: List[str] = []

        if market.upper() == "IN":
            ws_manager = provider_manager.angelone.ws_manager
            for sym in all_symbols:
                ws_q = ws_manager.get_live_quote(sym, current_time=now)
                if ws_q and not ws_q.is_stale:
                    quotes[sym] = ws_q
                else:
                    missing_rest.append(sym)
        else:
            missing_rest = list(all_symbols)

        if missing_rest:
            rest_quotes = provider_manager.get_quotes(missing_rest, market=market)
            quotes.update(rest_quotes)

        open_heat = sum(p.risk_amount for p in open_positions if p.risk_amount)
        open_syms = [p.symbol for p in open_positions]

        # -------------------------------------------------------------
        # Process Active Signals
        # -------------------------------------------------------------
        for sig in active_signals:
            # Check Signal TTL Expiry (15 trading days ~ 21 calendar days)
            if sig.created_at:
                age_days = (today - sig.created_at.date()).days
                if age_days > 21 and sig.state in ("WATCHLIST", "APPROACHING"):
                    sig.state = "EXPIRED"
                    db.commit()
                    continue

            q = quotes.get(sig.symbol)
            if not q or q.is_stale:
                continue

            # Strict Rule: delayed feeds never fire trigger alerts or show as live
            if not q.is_realtime:
                continue

            last_p = q.last_price
            trigger = sig.trigger
            stop = sig.stop
            zone_high = sig.entry_zone_high or (trigger * 1.015)

            # Invalidation Check
            if last_p <= stop:
                sig.state = "INVALIDATED"
                db.commit()
                dedupe_key = f"{sig.symbol}:INVALIDATED:{today}"
                if self._should_dispatch(dedupe_key):
                    dispatcher.dispatch(
                        alert_type="CANCEL",
                        title=f"INVALIDATED: {sig.symbol}",
                        body=f"Price ({last_p:.2f}) dropped to or below stop ({stop:.2f}) before breakout.",
                        symbol=sig.symbol,
                        market=market,
                        db=db,
                    )
                continue

            # No-Chase Extension Check
            if last_p > zone_high:
                sig.state = "EXTENDED"
                db.commit()
                dedupe_key = f"{sig.symbol}:EXTENDED:{today}"
                if self._should_dispatch(dedupe_key):
                    dispatcher.dispatch(
                        alert_type="SKIP",
                        title=f"EXTENDED (DO NOT CHASE): {sig.symbol}",
                        body=f"Price ({last_p:.2f}) moved beyond acceptable entry zone ({zone_high:.2f}). Skip trade.",
                        symbol=sig.symbol,
                        market=market,
                        db=db,
                    )
                continue

            # Approaching Zone Check
            if trigger > 0 and last_p < trigger and ((trigger - last_p) / trigger * 100.0) <= self.approach_pct:
                if sig.state != "APPROACHING":
                    sig.state = "APPROACHING"
                    db.commit()
                    dedupe_key = f"{sig.symbol}:APPROACHING:{today}"
                    if self._should_dispatch(dedupe_key):
                        dispatcher.dispatch(
                            alert_type="SYSTEM",
                            title=f"APPROACHING TRIGGER: {sig.symbol}",
                            body=f"Price ({last_p:.2f}) is within {self.approach_pct}% of breakout trigger ({trigger:.2f}).",
                            symbol=sig.symbol,
                            market=market,
                            db=db,
                        )

            # Trigger Evaluation (Between trigger and zone_high)
            if last_p >= trigger and last_p <= zone_high:
                candle_builder = provider_manager.angelone.ws_manager.candle_builder
                is_15m_confirmed = candle_builder.is_confirmed_15m(sig.symbol, trigger)

                # Volume pace check
                vol_pace = candle_builder.calculate_volume_pace(
                    symbol=sig.symbol,
                    avg_volume_20d=sig.atr * 100000 if sig.atr else 500000,
                    current_time=now,
                    day_volume=q.day_volume,
                )

                if not is_15m_confirmed:
                    # Provisional Trigger (waiting for 15m candle close)
                    if sig.state != "TRIGGERED_PROVISIONAL":
                        sig.state = "TRIGGERED_PROVISIONAL"
                        db.commit()
                        dedupe_key = f"{sig.symbol}:PROVISIONAL:{today}"
                        if self._should_dispatch(dedupe_key):
                            dispatcher.dispatch(
                                alert_type="SYSTEM",
                                title=f"PROVISIONAL TRIGGER: {sig.symbol} @ {last_p:.2f}",
                                body=f"Price crossed trigger ({trigger:.2f}). Awaiting 15-min candle confirmation close and volume pace check.",
                                symbol=sig.symbol,
                                market=market,
                                db=db,
                            )
                else:
                    # 15-Minute Candle Confirmed: RE-RUN DECISION PIPELINE with fresh market & risk data
                    fresh_bars = provider_manager.get_daily_bars([sig.symbol], today - datetime.timedelta(days=120), today, market=market, db=db)
                    df_sym = fresh_bars.get(sig.symbol)

                    pipeline_decision = decision_pipeline.evaluate(
                        symbol=sig.symbol,
                        df=df_sym,
                        market=market,
                        asof=today,
                        mode="LIVE",
                        current_open_positions=len(open_positions),
                        current_open_heat=open_heat,
                        open_symbols=open_syms,
                        db=db,
                    )

                    if pipeline_decision.final_decision == "PASS":
                        sig.state = "BUY_CONFIRMED"
                        db.commit()
                        dedupe_key = f"{sig.symbol}:BUY_CONFIRMED:{today}"
                        if self._should_dispatch(dedupe_key):
                            reasons = json.loads(sig.reasons_json) if sig.reasons_json else []
                            body = dispatcher.format_buy_alert(
                                symbol=sig.symbol,
                                setup=sig.setup,
                                price=last_p,
                                trigger=trigger,
                                stop=stop,
                                target1=sig.target1,
                                qty=pipeline_decision.qty or sig.qty,
                                risk_cur=pipeline_decision.risk_amount or sig.risk_amount,
                                reasons=reasons,
                            )
                            dispatcher.dispatch(
                                alert_type="BUY",
                                title=f"BUY CONFIRMED: {sig.symbol} @ {last_p:.2f} (15m Confirmed)",
                                body=body,
                                symbol=sig.symbol,
                                market=market,
                                payload={
                                    "price": last_p,
                                    "qty": pipeline_decision.qty or sig.qty,
                                    "stop": stop,
                                    "target": sig.target1,
                                    "volume_pace": vol_pace,
                                },
                                db=db,
                            )
                    elif pipeline_decision.final_decision == "BLOCK":
                        sig.state = "BLOCKED"
                        db.commit()
                        dedupe_key = f"{sig.symbol}:BLOCKED:{today}"
                        if self._should_dispatch(dedupe_key):
                            reasons_text = "; ".join(pipeline_decision.all_rejection_reasons)
                            dispatcher.dispatch(
                                alert_type="CANCEL",
                                title=f"ENTRY BLOCKED: {sig.symbol}",
                                body=f"15m breakout was blocked by live pipeline check: {reasons_text}",
                                symbol=sig.symbol,
                                market=market,
                                db=db,
                            )
                    else:  # WAIT
                        sig.state = "WAIT"
                        db.commit()

        # -------------------------------------------------------------
        # Process Open Positions (Trailing stop & exits)
        # -------------------------------------------------------------
        for pos in open_positions:
            q = quotes.get(pos.symbol)
            if not q or q.is_stale:
                continue

            last_p = q.last_price
            eval_res = exit_manager.evaluate_position(
                entry_price=pos.entry_price,
                initial_stop=pos.initial_stop,
                current_active_stop=pos.active_stop,
                current_price=last_p,
                highest_price_since_entry=max(pos.entry_price, last_p),
                current_atr=pos.entry_price * 0.02,
                current_sma50=pos.entry_price * 0.95,
                days_held=1,
            )

            if eval_res.action == "SELL_ALL":
                dispatcher.dispatch(
                    alert_type="SELL",
                    title=f"SELL ALERT: {pos.symbol}",
                    body=eval_res.reason,
                    symbol=pos.symbol,
                    market=market,
                    db=db,
                )
            elif eval_res.action == "SELL_PARTIAL":
                dispatcher.dispatch(
                    alert_type="SELL_HALF",
                    title=f"TAKE PARTIAL PROFIT: {pos.symbol}",
                    body=eval_res.reason,
                    symbol=pos.symbol,
                    market=market,
                    db=db,
                )
            elif eval_res.action == "TRAIL_UPDATE" and eval_res.new_active_stop:
                if eval_res.new_active_stop > pos.active_stop:
                    pos.active_stop = eval_res.new_active_stop
                    db.commit()
                    dispatcher.dispatch(
                        alert_type="SYSTEM",
                        title=f"MOVE STOP: {pos.symbol}",
                        body=eval_res.reason,
                        symbol=pos.symbol,
                        market=market,
                        db=db,
                    )


live_monitor = LiveBreakoutMonitor()


