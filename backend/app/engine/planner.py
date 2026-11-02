import datetime
import json
import logging
from typing import Dict, List, Optional
import pandas as pd
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.engine.gaprisk import calculate_effective_risk_per_share, compute_gap95
from app.engine.indicators import add_all_indicators
from app.engine.newsfilter import SymbolNewsCoverage, news_engine
from app.engine.regime import RegimeResult, evaluate_market_regime
from app.engine.screener import ChecklistItem, screener_engine
from app.engine.setups import SetupCandidate, setup_engine
from app.engine.pipeline import StageResult, decision_pipeline
from app.engine.sizing import PositionSizer
from app.engine.universe import universe_manager
from app.models import DecisionAudit, Position, Scan, Signal, Watchlist, WatchlistItem
from app.providers.manager import provider_manager
from app.settings import settings

logger = logging.getLogger(__name__)


class PlannedSignal(BaseModel):
    id: Optional[int] = None
    audit_id: Optional[int] = None
    symbol: str
    market: str
    setup: str
    trigger: float
    entry_zone_high: float
    stop: float
    target1: float
    qty: int
    risk_amount: float
    cost_estimate: float
    cost_in_r: float
    rs_rank: float
    score: float
    atr: float
    gap95: float
    state: str
    sources: List[str] = ["AUTO"]
    first_failing_check: Optional[str] = None
    reasons: List[str]
    checklist: List[ChecklistItem]
    decision_stages: List[StageResult] = []
    news_coverage: SymbolNewsCoverage
    valid_until: datetime.date
    is_experimental: bool = False
    shadow_mode: bool = False


class TradePlan(BaseModel):
    market: str
    session_date: datetime.date
    regime: RegimeResult
    signals: List[PlannedSignal]
    shadow_signals: List[PlannedSignal] = []
    candidate_opportunities: List[PlannedSignal] = []
    universe_size: int
    passed_filters: int
    data_warnings: List[str]
    generated_at: datetime.datetime


class Planner:
    """Master Orchestrator: executes the full end-of-day scan and generates ranked Trade Plans."""

    def __init__(self):
        self.screen_cfg = settings.strategy_config.get("screen", {})

    def run_scan(
        self,
        market: str = "IN",
        target_date: Optional[datetime.date] = None,
        db: Optional[Session] = None,
    ) -> TradePlan:
        session_date = target_date or datetime.date.today()
        mkt_cfg = settings.get_market_config(market)
        sizer = PositionSizer(market)
        data_warnings = []

        # 1. Load Universe Candidates
        stocks = universe_manager.load_universe(market)
        symbols = [s.symbol for s in stocks]
        if not symbols:
            symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

        # Tag candidate sources: 1 instrument = 1 candidate = 1 alert stream
        candidate_sources: Dict[str, List[str]] = {s: ["AUTO"] for s in symbols}

        # Query all active Watchlist items for this market
        if db is not None:
            active_wls = (
                db.query(Watchlist)
                .filter(Watchlist.market == market, Watchlist.is_deleted == False)
                .all()
            )
            for wl in active_wls:
                w_items = (
                    db.query(WatchlistItem)
                    .filter(WatchlistItem.watchlist_id == wl.id, WatchlistItem.is_deleted == False)
                    .all()
                )
                for it in w_items:
                    tag = f"WATCHLIST:{wl.name}"
                    if it.symbol not in candidate_sources:
                        candidate_sources[it.symbol] = [tag]
                    elif tag not in candidate_sources[it.symbol]:
                        candidate_sources[it.symbol].append(tag)

        all_symbols = list(candidate_sources.keys())

        # Check for open positions to suppress BUY alerts
        held_symbols = set()
        if db is not None:
            open_pos = (
                db.query(Position.symbol)
                .filter(Position.market == market, Position.status == "OPEN")
                .all()
            )
            held_symbols = set(p[0] for p in open_pos)

        # 2. Market Regime Check
        start_date = session_date - datetime.timedelta(days=400)
        index_bars = provider_manager.get_daily_bars(
            [mkt_cfg.index_symbol], start_date, session_date, market=market, db=db
        )
        index_df = index_bars.get(mkt_cfg.index_symbol)
        regime = evaluate_market_regime(index_df, market=market)

        if not regime.allows_entries:
            data_warnings.append(
                f"Market regime is WEAK ({regime.detail}). All new entries blocked."
            )

        # 3. Pull Historical Daily Bars for Universe + Watchlist Candidates
        bars_dict = provider_manager.get_daily_bars(
            all_symbols, start_date, session_date, market=market, db=db
        )

        # Compute indicators
        enriched_data: Dict[str, pd.DataFrame] = {}
        for sym, df in bars_dict.items():
            if df is not None and len(df) >= 20:
                enriched = add_all_indicators(df)
                enriched_data[sym] = enriched
            else:
                data_warnings.append(f"Insufficient historical bars for {sym}")

        # 4. Calculate Relative Strength Percentile Ranks
        # Out-of-universe Relative Strength evaluated against the systematic universe return distribution without distorting ranking population
        universe_syms = [s for s in symbols if s in enriched_data]
        universe_scores = [screener_engine.calculate_rs_score(enriched_data[s]) for s in universe_syms]
        rs_ranks = screener_engine.calculate_universe_rs_ranks({s: enriched_data[s] for s in universe_syms})

        for sym, df in enriched_data.items():
            if sym not in rs_ranks:
                rs_ranks[sym] = screener_engine.compute_out_of_universe_rs_rank(df, universe_scores)

        index_ret126 = 0.0
        if index_df is not None and len(index_df) >= 126:
            index_ret126 = float(index_df["close"].pct_change(126).iloc[-1] or 0.0)

        # 5. Execute Decision Pipeline across Universe & Watchlists
        primary_signals: List[PlannedSignal] = []
        shadow_signals: List[PlannedSignal] = []
        candidate_opportunities: List[PlannedSignal] = []
        passed_filters_count = 0

        for sym, df in enriched_data.items():
            stock_rs_rank = rs_ranks.get(sym, 0.5)

            # Evaluate through the unified 7-stage Trade Decision Pipeline
            decision = decision_pipeline.evaluate(
                symbol=sym,
                df=df,
                market=market,
                asof=session_date,
                mode="LIVE",
                index_df=index_df,
                all_universe_data=enriched_data,
                db=db,
            )

            # Scanner filter counting
            if decision.stages[0].status == "PASS":
                passed_filters_count += 1

            # Candidate setup information
            cand = setup_engine.evaluate_vcp_breakout(sym, df, tick=mkt_cfg.tick) or setup_engine.evaluate_pullback(sym, df, tick=mkt_cfg.tick)

            last_row = df.iloc[-1]
            last_price = float(last_row["close"])
            last_atr = float(last_row.get("atr14", 1.0))
            gap95 = compute_gap95(df)
            news_cov = news_engine.check_symbol_coverage(sym, market=market, db=db)
            tt_res = screener_engine.evaluate_trend_template(
                sym, df, rs_rank=stock_rs_rank, index_ret126=index_ret126
            )

            trigger = decision.trigger or (cand.pivot if cand else round(last_price * 1.02, 2))
            stop = decision.stop or (cand.stop_loss if cand else round(last_price * 0.95, 2))
            target1 = decision.target1 or round(trigger + 2.0 * max(0.1, trigger - stop), 2)
            qty = decision.qty if decision.qty and decision.qty > 0 else 1

            is_already_held = sym in held_symbols
            first_failing = decision.all_rejection_reasons[0] if decision.all_rejection_reasons else None

            # Categorize Opportunity State
            if is_already_held:
                state = "ALREADY_HELD"
            elif cand and decision.final_decision == "ALLOW":
                dist = ((trigger - last_price) / trigger * 100.0) if trigger > 0 else 999.0
                if 0 <= dist <= 1.5:
                    state = "APPROACHING"
                else:
                    state = "VALID_SETUP"
            elif cand and decision.final_decision == "BLOCK":
                state = "BLOCKED"
            elif not cand and decision.final_decision == "BLOCK":
                state = "NO_SETUP"
            else:
                state = "WATCHLIST"

            # Ranking Score Calculation
            score = 100.0 * stock_rs_rank
            if regime.is_bullish:
                score += 10.0
            if news_cov.status == "CLEAR":
                score += 5.0
            if decision.cost_in_r and decision.cost_in_r > 0:
                score -= decision.cost_in_r * 5.0

            valid_until = session_date + datetime.timedelta(days=2)
            reasons = decision.all_rejection_reasons if decision.all_rejection_reasons else (cand.reasons if cand else ["No valid base consolidation"])

            sig = PlannedSignal(
                symbol=sym,
                market=market,
                setup=cand.setup if cand else "MONITORING",
                trigger=round(trigger, 2),
                entry_zone_high=round(decision.entry_zone_high or trigger, 2),
                stop=round(stop, 2),
                target1=round(target1, 2),
                qty=qty,
                risk_amount=decision.risk_amount or 0.0,
                cost_estimate=(decision.cost_in_r or 0.1) * (decision.risk_amount or 100.0),
                cost_in_r=decision.cost_in_r or 0.0,
                rs_rank=stock_rs_rank,
                score=round(score, 1),
                atr=round(last_atr, 2),
                gap95=round(gap95, 3),
                state=state,
                sources=candidate_sources.get(sym, ["AUTO"]),
                first_failing_check=first_failing,
                reasons=reasons,
                checklist=tt_res.checklist,
                decision_stages=decision.stages,
                news_coverage=news_cov,
                valid_until=valid_until,
                is_experimental=cand.is_experimental if cand else False,
                shadow_mode=cand.shadow_mode if cand else False,
            )

            if decision.final_decision == "ALLOW" and cand and not is_already_held:
                if cand.shadow_mode or cand.is_experimental:
                    shadow_signals.append(sig)
                else:
                    primary_signals.append(sig)
            else:
                candidate_opportunities.append(sig)

        # Sort by score descending and take top N for primary signals
        top_n = int(self.screen_cfg.get("top_n_per_market", 6))
        primary_signals.sort(key=lambda s: s.score, reverse=True)
        primary_signals = primary_signals[:top_n]

        # Sort candidate opportunities by score descending
        candidate_opportunities.sort(key=lambda s: s.score, reverse=True)

        # 6. Persist Scan and Signals into Database
        if db is not None:
            scan_row = Scan(
                market=market,
                session_date=session_date,
                regime=regime.status,
                regime_detail_json=json.dumps(regime.model_dump()),
                universe_size=len(symbols),
                passed_filters=passed_filters_count,
                data_warnings_json=json.dumps(data_warnings),
            )
            db.add(scan_row)
            db.flush()

            # Clean previous non-closed signals for this market before inserting fresh scan signals
            db.query(Signal).filter(Signal.market == market, Signal.state.in_(["WATCHLIST", "BLOCKED", "NO_SETUP", "APPROACHING"])).delete(synchronize_session=False)

            all_to_persist = primary_signals + shadow_signals + candidate_opportunities
            for s in all_to_persist:
                sig_row = Signal(
                    scan_id=scan_row.id,
                    symbol=s.symbol,
                    market=s.market,
                    setup=s.setup,
                    trigger=s.trigger,
                    entry_zone_high=s.entry_zone_high,
                    stop=s.stop,
                    target1=s.target1,
                    qty=s.qty,
                    risk_amount=s.risk_amount,
                    cost_estimate=s.cost_estimate,
                    cost_in_r=s.cost_in_r,
                    rs_rank=s.rs_rank,
                    score=s.score,
                    atr=s.atr,
                    gap95=s.gap95,
                    reasons_json=json.dumps(s.reasons),
                    sources_json=json.dumps(s.sources),
                    news_flags_json=json.dumps(s.news_coverage.model_dump(), default=str),
                    state=s.state,
                    valid_until=s.valid_until,
                )
                db.add(sig_row)
                db.flush()
                s.id = sig_row.id

            db.commit()

        return TradePlan(
            market=market,
            session_date=session_date,
            regime=regime,
            signals=primary_signals,
            shadow_signals=shadow_signals,
            candidate_opportunities=candidate_opportunities,
            universe_size=len(symbols),
            passed_filters=passed_filters_count,
            data_warnings=data_warnings,
            generated_at=datetime.datetime.utcnow(),
        )


planner = Planner()

