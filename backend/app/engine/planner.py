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
from app.models import DecisionAudit, Scan, Signal
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
    shadow_signals: List[PlannedSignal]
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

        # 1. Load Universe
        stocks = universe_manager.load_universe(market)
        symbols = [s.symbol for s in stocks]
        if not symbols:
            symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

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

        # 3. Pull Historical Daily Bars for Universe
        bars_dict = provider_manager.get_daily_bars(
            symbols, start_date, session_date, market=market, db=db
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
        rs_ranks = screener_engine.calculate_universe_rs_ranks(enriched_data)
        index_ret126 = 0.0
        if index_df is not None and len(index_df) >= 126:
            index_ret126 = float(index_df["close"].pct_change(126).iloc[-1] or 0.0)

        # 5. Execute Decision Pipeline across Universe
        primary_signals: List[PlannedSignal] = []
        shadow_signals: List[PlannedSignal] = []
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

            # Scanner & setup filter counting
            if decision.stages[0].status == "PASS":
                passed_filters_count += 1

            if decision.final_decision == "BLOCK":
                for rej in decision.all_rejection_reasons:
                    data_warnings.append(f"{sym}: {rej}")
                continue

            # Candidate setup information
            cand = setup_engine.evaluate_vcp_breakout(sym, df, tick=mkt_cfg.tick) or setup_engine.evaluate_pullback(sym, df, tick=mkt_cfg.tick)
            if not cand or not decision.trigger or not decision.stop:
                continue

            last_row = df.iloc[-1]
            last_atr = float(last_row.get("atr14", 1.0))
            gap95 = compute_gap95(df)
            news_cov = news_engine.check_symbol_coverage(sym, market=market, db=db)
            tt_res = screener_engine.evaluate_trend_template(
                sym, df, rs_rank=stock_rs_rank, index_ret126=index_ret126
            )

            # Ranking Score Calculation
            score = 100.0 * stock_rs_rank
            if regime.is_bullish:
                score += 10.0
            if news_cov.status == "CLEAR":
                score += 5.0
            if decision.cost_in_r and decision.cost_in_r > 0:
                score -= decision.cost_in_r * 5.0

            valid_until = session_date + datetime.timedelta(days=2)

            sig = PlannedSignal(
                symbol=sym,
                market=market,
                setup=cand.setup,
                trigger=decision.trigger,
                entry_zone_high=decision.entry_zone_high or decision.trigger,
                stop=decision.stop,
                target1=decision.target1 or (decision.trigger + 2.0 * (decision.trigger - decision.stop)),
                qty=decision.qty or 1,
                risk_amount=decision.risk_amount or 0.0,
                cost_estimate=(decision.cost_in_r or 0.1) * (decision.risk_amount or 100.0),
                cost_in_r=decision.cost_in_r or 0.0,
                rs_rank=stock_rs_rank,
                score=round(score, 1),
                atr=round(last_atr, 2),
                gap95=round(gap95, 3),
                state="WATCHLIST",
                reasons=cand.reasons,
                checklist=tt_res.checklist,
                decision_stages=decision.stages,
                news_coverage=news_cov,
                valid_until=valid_until,
                is_experimental=cand.is_experimental,
                shadow_mode=cand.shadow_mode,
            )

            if cand.shadow_mode or cand.is_experimental:
                shadow_signals.append(sig)
            else:
                primary_signals.append(sig)

        # Sort by score descending and take top N
        top_n = int(self.screen_cfg.get("top_n_per_market", 6))
        primary_signals.sort(key=lambda s: s.score, reverse=True)
        primary_signals = primary_signals[:top_n]

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

            for s in primary_signals + shadow_signals:
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
            universe_size=len(symbols),
            passed_filters=passed_filters_count,
            data_warnings=data_warnings,
            generated_at=datetime.datetime.utcnow(),
        )


planner = Planner()

