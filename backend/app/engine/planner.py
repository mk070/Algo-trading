import datetime
import json
import logging
from typing import Any, Dict, List, Optional
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
from app.engine.fundamentals_engine import fundamentals_engine
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
    tier: str = "Small"
    is_higher_risk: bool = False
    setup_edge_status: str = "VALIDATED"
    setup_note: Optional[str] = None
    sources: List[str] = ["AUTO"]
    first_failing_check: Optional[str] = None
    blocked_reason: Optional[Dict[str, str]] = None
    reasons: List[str]
    checklist: List[ChecklistItem]
    decision_stages: List[StageResult] = []
    news_coverage: SymbolNewsCoverage
    fundamentals: Optional[Dict[str, Any]] = None
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
    pre_breakout_watchlist: List[PlannedSignal] = []
    funnel: List[Dict[str, Any]] = []
    coverage_summary: Optional[Dict[str, Any]] = None
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
        stocks = universe_manager.load_universe(market, db=db)
        symbols = [s.symbol for s in stocks]
        if not symbols:
            symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

        stock_tier_map = {s.symbol: getattr(s, "tier", "Small") for s in stocks}
        stock_risk_map = {s.symbol: getattr(s, "is_higher_risk", False) for s in stocks}
        snapshots_map = fundamentals_engine.get_all_latest_snapshots(market=market, db=db)

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
                    tag = "VALUE_RADAR" if it.source == "VALUE_RADAR" else f"WATCHLIST:{wl.name}"
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

        dist_pct = ((regime.last_close - regime.sma200) / regime.sma200 * 100.0) if regime.sma200 > 0 else 0.0
        dist_str = f", {dist_pct:+.2f}%" if dist_pct != 0 else ""
        index_name = "Nifty" if market == "IN" else "S&P 500"
        regime_weak_msg = f"Regime WEAK ({index_name} {regime.last_close:,.2f} below SMA200 {regime.sma200:,.2f}{dist_str})"

        if not regime.allows_entries:
            data_warnings.append(
                f"Market regime is WEAK ({regime_weak_msg}). All new entries blocked."
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

        # 4. Calculate Relative Strength Percentile Ranks across whole scanned liquid universe
        universe_syms = [s for s in symbols if s in enriched_data]
        universe_scores = [screener_engine.calculate_rs_score(enriched_data[s]) for s in universe_syms]
        rs_ranks = screener_engine.calculate_universe_rs_ranks({s: enriched_data[s] for s in universe_syms})

        for sym, df in enriched_data.items():
            if sym not in rs_ranks:
                rs_ranks[sym] = screener_engine.compute_out_of_universe_rs_rank(df, universe_scores)

        index_ret126 = 0.0
        if index_df is not None and len(index_df) >= 126:
            index_ret126 = float(index_df["close"].pct_change(126).iloc[-1] or 0.0)

        # 5. Execute Decision Pipeline & Monotonic Sequential Funnel Tracking
        primary_signals: List[PlannedSignal] = []
        shadow_signals: List[PlannedSignal] = []
        candidate_opportunities: List[PlannedSignal] = []
        pre_breakout_watchlist: List[PlannedSignal] = []
        passed_filters_count = 0

        funnel_counts = {
            "scanned": 0,
            "trend_ok": 0,
            "setup_ok": 0,
            "fundamentals_ok": 0,
            "news_ok": 0,
            "risk_ok": 0,
            "pass": 0,
        }

        for sym, df in enriched_data.items():
            stock_rs_rank = rs_ranks.get(sym, 0.5)
            tier = stock_tier_map.get(sym, "Small")
            is_higher_risk = stock_risk_map.get(sym, True if tier == "Small" else False)

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

            # Universe filter evaluation (Price floor, ADV, Volatility cap, Affordability)
            u_res = universe_manager.filter_stock(sym, df, market=market, capital=mkt_cfg.capital, tier=tier)
            if u_res.passed:
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

            # Fundamentals evaluation
            snap = snapshots_map.get(sym)
            fund_dict = None
            if snap and snap.lights_json:
                try:
                    fund_dict = json.loads(snap.lights_json)
                except Exception:
                    fund_dict = None
            if not fund_dict and snap:
                fund_dict = fundamentals_engine.evaluate_traffic_lights(sym, {
                    "revenue_yoy": snap.revenue_yoy,
                    "profit_yoy": snap.profit_yoy,
                    "op_margin": snap.op_margin,
                    "roce": snap.roce,
                    "roe": snap.roe,
                    "debt_equity": snap.debt_equity,
                    "interest_coverage": snap.interest_coverage,
                    "pe": snap.pe,
                    "sector_median_pe": snap.sector_median_pe,
                    "promoter_holding": snap.promoter_holding,
                    "pledge_pct": snap.pledge_pct,
                }, market=market)

            # Monotonic sequential funnel accumulation
            is_scanned = u_res.passed
            is_trend = is_scanned and tt_res.passed
            is_setup = is_trend and (cand is not None and getattr(cand, "setup", "") in ("VCP", "PULLBACK"))
            fund_has_red = (fund_dict.get("red_count", 0) > 0) if fund_dict else False
            is_fund = is_setup and not fund_has_red
            is_news = is_fund and (news_cov.status == "CLEAR")
            is_risk = is_news and regime.allows_entries and (decision.stages[-1].status == "PASS")
            is_pass = is_risk and (decision.final_decision == "ALLOW")

            if is_scanned: funnel_counts["scanned"] += 1
            if is_trend: funnel_counts["trend_ok"] += 1
            if is_setup: funnel_counts["setup_ok"] += 1
            if is_fund: funnel_counts["fundamentals_ok"] += 1
            if is_news: funnel_counts["news_ok"] += 1
            if is_risk: funnel_counts["risk_ok"] += 1
            if is_pass: funnel_counts["pass"] += 1

            if cand:
                trigger = decision.trigger or cand.pivot
                stop = decision.stop or cand.stop_loss
                target1 = decision.target1 or round(trigger + 2.0 * max(0.1, trigger - stop), 2)
                qty = decision.qty if ((decision.final_decision == "ALLOW" or state == "PRE_BREAKOUT_WATCHLIST") and decision.qty and decision.qty > 0) else 0
            else:
                trigger = 0.0
                stop = 0.0
                target1 = 0.0
                qty = 0

            is_already_held = sym in held_symbols
            first_failing = decision.all_rejection_reasons[0] if decision.all_rejection_reasons else None
            blocked_reason = None
            for stage in decision.stages:
                if stage.status != "BLOCK":
                    continue
                failed_check = next((check for check in stage.checks if not check.passed), None)
                if failed_check:
                    blocked_reason = {
                        "stage": stage.stage_name,
                        "check": failed_check.name,
                        "value": failed_check.value,
                        "threshold": failed_check.threshold,
                        "note": failed_check.note or "This check must pass before the setup can proceed.",
                    }
                elif stage.rejection_reasons:
                    blocked_reason = {"stage": stage.stage_name, "check": "Gate", "value": stage.rejection_reasons[0], "threshold": "Pass required", "note": "This gate blocked the setup."}
                if blocked_reason:
                    break

            # Categorize Opportunity State
            if is_already_held:
                state = "ALREADY_HELD"
            elif cand and cand.classification == "BROKE_OUT_TODAY":
                state = "BROKE_OUT_TODAY"
            elif (
                cand and cand.setup == "VCP" and last_price < cand.pivot
                and ((cand.pivot - last_price) / cand.pivot * 100.0) <= settings.get_vcp_config().pivot_proximity_pct
                and all(stage.status == "PASS" for stage in decision.stages if stage.stage_name in {"Setup Validator", "Entry Planner", "Exit Planner", "Position Sizer"})
            ):
                state = "PRE_BREAKOUT_WATCHLIST"
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

            # Setup edge validation attribution (Strategy Lab task-9156 caveat)
            setup_edge_status = "VALIDATED"
            setup_note = None
            if cand:
                if cand.setup == "PULLBACK":
                    setup_edge_status = "NO_VALIDATED_EDGE"
                    setup_note = "Strategy Lab (task-9156) found no validated edge for Setup P (EMA pullback). Research only."
                else:
                    setup_edge_status = "VALIDATED"
                    setup_note = "Minervini Stage 2 VCP consolidation structure"

            # If blocked by Market Regime, override blocked reason with exact distance
            if not regime.allows_entries and state == "BLOCKED":
                blocked_reason = {
                    "stage": "Scanner",
                    "check": "Market Regime",
                    "value": regime.status,
                    "threshold": "BULLISH or CAUTION",
                    "note": regime_weak_msg,
                }

            # Ranking Score Calculation
            score = 100.0 * stock_rs_rank
            if regime.is_bullish:
                score += 10.0
            if news_cov.status == "CLEAR":
                score += 5.0
            if decision.cost_in_r and decision.cost_in_r > 0:
                score -= decision.cost_in_r * 5.0

            valid_until = session_date + datetime.timedelta(days=2)
            raw_reasons = decision.all_rejection_reasons if decision.all_rejection_reasons else (cand.reasons if cand else ["No valid base consolidation or pullback pattern detected"])
            reasons = [
                r for r in raw_reasons
                if isinstance(r, str) and r.strip() and not ("price 0.00" in r and not cand)
            ]
            if not reasons:
                reasons = ["No valid base consolidation or pullback pattern detected"] if not cand else ["Setup pending breakout confirmation"]
            if not regime.allows_entries and state == "BLOCKED":
                reasons = [f"BLOCKED: {regime_weak_msg}"]

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
                tier=tier,
                is_higher_risk=is_higher_risk,
                setup_edge_status=setup_edge_status,
                setup_note=setup_note,
                sources=candidate_sources.get(sym, ["AUTO"]),
                first_failing_check=first_failing,
                blocked_reason=blocked_reason,
                reasons=reasons,
                checklist=tt_res.checklist,
                decision_stages=decision.stages,
                news_coverage=news_cov,
                fundamentals=fund_dict,
                valid_until=valid_until,
                is_experimental=cand.is_experimental if cand else False,
                shadow_mode=cand.shadow_mode if cand else False,
            )

            # Small / Illiquid Tier Gating: excluded from primary live BUY alerts unless enabled in Settings
            allow_small_caps = getattr(mkt_cfg, "allow_higher_risk_small_caps", False)
            if decision.final_decision == "ALLOW" and cand and not is_already_held and state not in {"BROKE_OUT_TODAY", "PRE_BREAKOUT_WATCHLIST"}:
                if (tier == "Small" or is_higher_risk) and not allow_small_caps:
                    sig.state = "BLOCKED"
                    sig.reasons.append("Higher risk Small-cap tier excluded from live BUY alerts (enable in Settings to allow)")
                    candidate_opportunities.append(sig)
                elif cand.shadow_mode or cand.is_experimental:
                    shadow_signals.append(sig)
                else:
                    primary_signals.append(sig)
            else:
                candidate_opportunities.append(sig)
                if state == "PRE_BREAKOUT_WATCHLIST":
                    pre_breakout_watchlist.append(sig)

        # Sort by score descending and take top N for primary signals
        top_n = int(self.screen_cfg.get("top_n_per_market", 6))
        primary_signals.sort(key=lambda s: s.score, reverse=True)
        primary_signals = primary_signals[:top_n]

        # Sort candidate opportunities by score descending
        candidate_opportunities.sort(key=lambda s: s.score, reverse=True)

        # Build monotonic sequential funnel
        funnel = [
            {
                "key": "ALL",
                "label": "Scanned",
                "count": funnel_counts["scanned"],
                "denominator": len(symbols),
                "tooltip": "Eligible instruments passing price floor, liquidity ADV, volatility cap and affordability filters",
            },
            {
                "key": "TREND",
                "label": "Trend OK",
                "count": funnel_counts["trend_ok"],
                "denominator": funnel_counts["scanned"] or 1,
                "tooltip": "Passing Minervini Stage 2 Trend Template rules (SMA50/150/200, 52w high/low, RS Rank >= 0.70)",
            },
            {
                "key": "SETUPS",
                "label": "Valid Setups" if regime.allows_entries else "Patterns (blocked by regime)",
                "count": funnel_counts["setup_ok"],
                "denominator": funnel_counts["trend_ok"] or 1,
                "tooltip": "Consolidation structure formed: tight VCP contraction or EMA pullback",
            },
            {
                "key": "FUNDAMENTALS",
                "label": "Fundamentals OK",
                "count": funnel_counts["fundamentals_ok"],
                "denominator": funnel_counts["setup_ok"] or 1,
                "tooltip": "Fundamental health check has 0 RED traffic lights (mode: warn)",
            },
            {
                "key": "NEWS",
                "label": "News Clear",
                "count": funnel_counts["news_ok"],
                "denominator": funnel_counts["fundamentals_ok"] or 1,
                "tooltip": "No high-risk corporate disclosures, earnings blackout, or adverse news events",
            },
            {
                "key": "RISK",
                "label": "Risk OK",
                "count": funnel_counts["risk_ok"],
                "denominator": funnel_counts["news_ok"] or 1,
                "tooltip": "Passes portfolio heat, sector limits, cost drag gate <= 0.25R, and regime allow_entries",
            },
            {
                "key": "PASS",
                "label": "PASS",
                "count": funnel_counts["pass"],
                "denominator": funnel_counts["risk_ok"] or 1,
                "tooltip": "Approved actionable order ready for execution upon 15m intraday trigger confirmation",
            },
        ]

        # 6. Persist Scan and Signals into Database
        if db is not None:
            previous_fundamentals = {}
            for old_signal in db.query(Signal).filter(Signal.market == market).order_by(Signal.created_at.desc()).all():
                if old_signal.symbol not in previous_fundamentals and old_signal.fundamentals_json:
                    previous_fundamentals[old_signal.symbol] = old_signal.fundamentals_json
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
                    fundamentals_json=json.dumps(s.fundamentals, default=str) if s.fundamentals else previous_fundamentals.get(s.symbol, json.dumps({
                        "symbol": s.symbol, "mode": settings.fundamentals_config.get("mode", "warn"),
                        "unknown_count": 8, "red_count": 0,
                        "lights": [{"metric": "Fundamental coverage", "status": "UNKNOWN", "value": "No snapshot stored", "period": "N/A", "source": "N/A", "why": "Refresh the Fundamentalist view for available data.", "threshold": "Missing data is never green"}],
                    })),
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
            pre_breakout_watchlist=pre_breakout_watchlist,
            funnel=funnel,
            universe_size=len(symbols),
            passed_filters=passed_filters_count,
            data_warnings=data_warnings,
            generated_at=datetime.datetime.utcnow(),
        )


planner = Planner()

