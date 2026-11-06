import datetime
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.engine.costs import CostBreakdown, CostModel
from app.engine.gaprisk import calculate_effective_risk_per_share, compute_gap95
from app.engine.indicators import add_all_indicators
from app.engine.newsfilter import SymbolNewsCoverage, news_engine
from app.engine.regime import RegimeResult, evaluate_market_regime
from app.engine.screener import ChecklistItem, screener_engine
from app.engine.setups import SetupCandidate, setup_engine
from app.engine.sizing import PositionSizer, SizingResult
from app.engine.universe import universe_manager
from app.models import DecisionAudit, DecisionStageResult
from app.settings import settings

logger = logging.getLogger(__name__)


class StageCheck(BaseModel):
    name: str
    value: str
    threshold: str
    passed: bool
    note: str = ""


class StageResult(BaseModel):
    stage_name: str
    status: str  # PASS, BLOCK, WAIT
    checks: List[StageCheck]
    rejection_reasons: List[str]


class PipelineDecision(BaseModel):
    symbol: str
    market: str
    asof_date: datetime.date
    mode: str  # LIVE, PAPER, BACKTEST
    final_decision: str  # PASS, BLOCK, WAIT
    setup: Optional[str] = None
    trigger: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop: Optional[float] = None
    target1: Optional[float] = None
    qty: Optional[int] = None
    risk_amount: Optional[float] = None
    cost_in_r: Optional[float] = None
    stages: List[StageResult]
    all_rejection_reasons: List[str]
    config_hash: str
    code_version: str = "2.3"
    data_source: str = "ANGEL_ONE"


def compute_config_hash() -> str:
    cfg_str = json.dumps(settings.strategy_config, sort_keys=True)
    return hashlib.sha256(cfg_str.encode("utf-8")).hexdigest()[:16]


class DecisionPipeline:
    """Unified Trade Decision Pipeline (Spec 3.11, 4.5).
    Evaluates:
      Stage 1: Scanner (Regime, Price Floor, Liquidity ADV, Volatility Cap, Affordability)
      Stage 2: Setup Validator (Minervini Trend Template & Setup V VCP / Setup P Pullback)
      Stage 3: News / Event Analyst (Disclosures, Red/Amber flags, Earnings Blackout)
      Stage 4: Entry Planner (Pivot, Trigger, Entry Zone, Max Chase Limit)
      Stage 5: Exit Planner (Structural Stop, 2R Target 1, Chandelier Trail, Trend Break, Time Stop)
      Stage 6: Position Sizer (Gap95 Risk, Risk Amount, Position Cap, Whole Share Qty)
      Stage 7: Risk Validator (Heat, Max Positions, Correlation Cluster, Cost Gate <= 0.25R, Circuit Breakers)
    Final Decision: PASS | BLOCK | WAIT
    """

    def __init__(self):
        self.code_version = "2.3"

    def evaluate(
        self,
        symbol: str,
        df: pd.DataFrame,
        market: str = "IN",
        asof: Optional[datetime.date] = None,
        mode: str = "LIVE",
        index_df: Optional[pd.DataFrame] = None,
        capital_override: Optional[float] = None,
        current_open_positions: int = 0,
        current_open_heat: float = 0.0,
        open_symbols: Optional[List[str]] = None,
        all_universe_data: Optional[Dict[str, pd.DataFrame]] = None,
        earnings_date: Optional[datetime.date] = None,
        db: Optional[Session] = None,
    ) -> PipelineDecision:
        asof_date = asof or datetime.date.today()
        mkt_cfg = settings.get_market_config(market)
        capital = capital_override or mkt_cfg.capital
        config_hash = compute_config_hash()

        stages: List[StageResult] = []
        all_rejections: List[str] = []

        # Ensure dataframe is properly sliced up to asof (NO LOOK-AHEAD)
        if df is not None and not df.empty:
            df = df[df["date"] <= asof_date].copy()
            if len(df) >= 20 and "sma50" not in df.columns:
                df = add_all_indicators(df)

        # ------------------------------------------------------------------
        # STAGE 1: SCANNER
        # ------------------------------------------------------------------
        s1_checks: List[StageCheck] = []
        s1_rejections: List[str] = []

        # Market Regime Check
        regime = evaluate_market_regime(index_df, market=market)
        dist_pct = ((regime.last_close - regime.sma200) / regime.sma200 * 100.0) if regime.sma200 > 0 else 0.0
        dist_str = f", {dist_pct:+.2f}%" if dist_pct != 0 else ""
        index_name = "Nifty" if market == "IN" else "S&P 500"
        if not regime.allows_entries:
            regime_detail = f"Regime WEAK ({index_name} {regime.last_close:,.2f} below SMA200 {regime.sma200:,.2f}{dist_str})"
        else:
            regime_detail = regime.detail

        s1_checks.append(
            StageCheck(
                name="Market Regime",
                value=regime.status,
                threshold="BULLISH or CAUTION",
                passed=regime.allows_entries,
                note=regime_detail,
            )
        )
        if not regime.allows_entries:
            s1_rejections.append(f"Regime {regime.status} blocks new entries ({regime_detail})")

        # Universe Filters (Price floor, Liquidity ADV, Volatility Cap, Affordability)
        u_res = universe_manager.filter_stock(symbol, df, market=market, capital=capital)
        s1_checks.append(
            StageCheck(
                name="Price Floor",
                value=f"{u_res.last_price:.2f}",
                threshold=f">= {mkt_cfg.min_price:.2f}",
                passed=u_res.last_price >= mkt_cfg.min_price,
                note="Minimum price filter",
            )
        )
        s1_checks.append(
            StageCheck(
                name="Liquidity (20d Turnover)",
                value=f"{u_res.avg_turnover:,.0f}",
                threshold=f">= {mkt_cfg.min_avg_traded_value:,.0f}",
                passed=u_res.avg_turnover >= mkt_cfg.min_avg_traded_value,
                note="Average daily traded value",
            )
        )
        s1_checks.append(
            StageCheck(
                name="Volatility Cap (ATR%)",
                value=f"{u_res.atr_pct:.2f}%",
                threshold=f"<= {settings.get_risk_config().max_atr_pct}%",
                passed=u_res.atr_pct <= settings.get_risk_config().max_atr_pct,
                note="Maximum volatility boundary",
            )
        )
        s1_checks.append(
            StageCheck(
                name="Affordability",
                value=f"{u_res.last_price:.2f}",
                threshold=f"<= {capital * (settings.get_risk_config().max_share_price_pct_of_capital / 100.0):.2f}",
                passed=u_res.is_affordable,
                note="1 share cost <= 25% of capital",
            )
        )

        for rej in u_res.rejection_reasons:
            s1_rejections.append(rej)

        s1_status = "PASS" if not s1_rejections else "BLOCK"
        stages.append(
            StageResult(
                stage_name="Scanner",
                status=s1_status,
                checks=s1_checks,
                rejection_reasons=s1_rejections,
            )
        )
        all_rejections.extend(s1_rejections)

        # ------------------------------------------------------------------
        # STAGE 2: SETUP VALIDATOR (Minervini Trend Template & Setups)
        # ------------------------------------------------------------------
        s2_checks: List[StageCheck] = []
        s2_rejections: List[str] = []

        rs_rank = 0.75
        index_ret126 = 0.0
        if all_universe_data:
            ranks = screener_engine.calculate_universe_rs_ranks(all_universe_data)
            rs_rank = ranks.get(symbol, 0.75)
        if index_df is not None and len(index_df) >= 126:
            index_ret126 = float(index_df["close"].pct_change(126).iloc[-1] or 0.0)

        tt_res = screener_engine.evaluate_trend_template(
            symbol, df, rs_rank=rs_rank, index_ret126=index_ret126
        )

        for item in tt_res.checklist:
            s2_checks.append(
                StageCheck(
                    name=item.rule,
                    value=item.actual_value,
                    threshold=item.expected_value,
                    passed=item.passed,
                    note="Trend Template requirement",
                )
            )
            if not item.passed:
                s2_rejections.append(f"Trend Template: {item.rule} failed ({item.actual_value})")

        # Setup detection
        vcp_cand = setup_engine.evaluate_vcp_breakout(symbol, df, tick=mkt_cfg.tick)
        pullback_cand = setup_engine.evaluate_pullback(symbol, df, tick=mkt_cfg.tick)
        chosen_cand: Optional[SetupCandidate] = vcp_cand or pullback_cand

        s2_checks.append(
            StageCheck(
                name="Setup Pattern Detection",
                value=chosen_cand.setup if chosen_cand else "None",
                threshold="Valid VCP or Pullback pattern",
                passed=chosen_cand is not None,
                note="Objective pattern criteria",
            )
        )
        if not chosen_cand:
            s2_rejections.append("No valid base consolidation or pullback pattern detected")

        s2_status = "PASS" if not s2_rejections else "BLOCK"
        stages.append(
            StageResult(
                stage_name="Setup Validator",
                status=s2_status,
                checks=s2_checks,
                rejection_reasons=s2_rejections,
            )
        )
        all_rejections.extend(s2_rejections)

        # ------------------------------------------------------------------
        # STAGE 3: NEWS / EVENT ANALYST (Disclosures & Earnings Blackout)
        # ------------------------------------------------------------------
        s3_checks: List[StageCheck] = []
        s3_rejections: List[str] = []

        news_cov = news_engine.check_symbol_coverage(
            symbol, market=market, earnings_date=earnings_date, asof_date=asof_date, db=db
        )

        s3_checks.append(
            StageCheck(
                name="Earnings Blackout Window",
                value="Blackout Triggered" if news_cov.has_earnings_blackout else "Clear",
                threshold=f"No earnings within {settings.get_news_config().earnings_block_days} days",
                passed=not news_cov.has_earnings_blackout,
                note=f"Earnings date: {news_cov.earnings_date or 'None scheduled'}",
            )
        )
        if news_cov.has_earnings_blackout:
            s3_rejections.append(
                f"Earnings blackout: financial results scheduled on {news_cov.earnings_date} (within {settings.get_news_config().earnings_block_days} days)"
            )

        s3_checks.append(
            StageCheck(
                name="Critical RED Announcements",
                value=f"{news_cov.red_events_count} Red Events",
                threshold="0 Red Events",
                passed=news_cov.red_events_count == 0,
                note="Fraud, forensic audit, auditor resignation, default",
            )
        )
        if news_cov.red_events_count > 0:
            s3_rejections.append(f"Blocked by {news_cov.red_events_count} critical RED corporate disclosures")

        s3_checks.append(
            StageCheck(
                name="AMBER Review Items",
                value=f"{news_cov.amber_events_count} Amber Events",
                threshold="Review required if present",
                passed=True,  # AMBER flags do not block, they flag
                note="Fund-raise, board meetings, litigation",
            )
        )

        s3_status = "BLOCK" if s3_rejections else ("WAIT" if news_cov.status == "REVIEW" else "PASS")
        stages.append(
            StageResult(
                stage_name="News/Event Analyst",
                status=s3_status,
                checks=s3_checks,
                rejection_reasons=s3_rejections,
            )
        )
        all_rejections.extend(s3_rejections)

        # Fundamental lights are an informational layer by default. They come
        # from an explicitly initiated refresh and are carried forward with the
        # symbol's signals; UNKNOWN data never becomes a pass/green light.
        fundamentals_cfg = settings.fundamentals_config
        fundamental_snapshot = None
        if db is not None:
            from app.models import Signal
            previous = (db.query(Signal).filter(Signal.symbol == symbol, Signal.market == market)
                        .order_by(Signal.created_at.desc()).first())
            if previous and previous.fundamentals_json:
                try:
                    fundamental_snapshot = json.loads(previous.fundamentals_json)
                except (TypeError, ValueError):
                    fundamental_snapshot = None
        red_metrics = [light for light in (fundamental_snapshot or {}).get("lights", []) if light.get("status") == "RED"]
        fundamental_mode = fundamentals_cfg.get("mode", "warn")
        fundamental_blocks = bool(red_metrics) and fundamental_mode == "block_on_red"
        fundamental_reason = ("Fundamental review: " + ", ".join(light.get("metric", "metric") for light in red_metrics)) if red_metrics else None
        stages.append(StageResult(
            stage_name="Fundamentalist",
            status="BLOCK" if fundamental_blocks else "PASS",
            checks=[StageCheck(
                name="Fundamental traffic lights",
                value=(f"{len(red_metrics)} RED / {(fundamental_snapshot or {}).get('unknown_count', 8)} UNKNOWN" if fundamental_snapshot else "UNKNOWN (not refreshed)"),
                threshold=("No RED lights" if fundamental_mode == "block_on_red" else "Review RED lights; do not change the technical plan"),
                passed=not red_metrics,
                note="; ".join(light.get("metric", "") + ": " + str(light.get("value", "")) for light in red_metrics) or "Missing data remains UNKNOWN.",
            )],
            rejection_reasons=[fundamental_reason] if fundamental_reason and fundamental_mode in {"warn", "block_on_red"} else [],
        ))
        if fundamental_reason and fundamental_mode in {"warn", "block_on_red"}:
            all_rejections.append(fundamental_reason)

        # ------------------------------------------------------------------
        # STAGES 4-7: ENTRY, EXIT, SIZING, AND RISK VALIDATION
        # Only evaluate execution mechanics if a valid setup candidate exists!
        # If no setup exists, mark these stages as WAIT with clean informational notes.
        # ------------------------------------------------------------------
        if not chosen_cand:
            sizing = None
            stages.append(
                StageResult(
                    stage_name="Entry Planner",
                    status="NOT EVALUATED",
                    checks=[
                        StageCheck(
                            name="Trigger Level",
                            value="None",
                            threshold="Calculated pivot + 0.1*ATR",
                            passed=False,
                            note="NOT EVALUATED - awaiting valid chart base / breakout setup",
                        )
                    ],
                    rejection_reasons=[],
                )
            )
            stages.append(
                StageResult(
                    stage_name="Exit Planner",
                    status="NOT EVALUATED",
                    checks=[
                        StageCheck(
                            name="Structural Stop Loss",
                            value="None",
                            threshold="Lowest low 10 bars - 0.2*ATR",
                            passed=False,
                            note="NOT EVALUATED - defined once trigger level confirmed",
                        )
                    ],
                    rejection_reasons=[],
                )
            )
            stages.append(
                StageResult(
                    stage_name="Position Sizer",
                    status="NOT EVALUATED",
                    checks=[
                        StageCheck(
                            name="Planned Sizing",
                            value="0 shares",
                            threshold=">= 1 share",
                            passed=False,
                            note="NOT EVALUATED - position sizing deferred until setup verified",
                        )
                    ],
                    rejection_reasons=[],
                )
            )
            stages.append(
                StageResult(
                    stage_name="Risk Validator",
                    status="NOT EVALUATED",
                    checks=[
                        StageCheck(
                            name="Risk & Cost Gate",
                            value="Pending",
                            threshold="Cost <= 0.25R",
                            passed=False,
                            note="NOT EVALUATED - validation executed on actionable entries",
                        )
                    ],
                    rejection_reasons=[],
                )
            )
        else:
            # ------------------------------------------------------------------
            # STAGE 4: ENTRY PLANNER
            # ------------------------------------------------------------------
            s4_checks: List[StageCheck] = []
            s4_rejections: List[str] = []

            trigger = chosen_cand.trigger
            zone_high = chosen_cand.entry_zone_high
            pivot = chosen_cand.pivot

            s4_checks.append(
                StageCheck(
                    name="Trigger Level",
                    value=f"{trigger:.2f}",
                    threshold="Calculated pivot + 0.1*ATR",
                    passed=trigger > 0,
                    note=f"Pivot: {pivot:.2f}",
                )
            )
            s4_checks.append(
                StageCheck(
                    name="Entry Zone Boundary",
                    value=f"{trigger:.2f} to {zone_high:.2f}",
                    threshold=f"Max {((zone_high - trigger)/trigger * 100.0) if trigger > 0 else 0.0:.1f}% above trigger",
                    passed=zone_high >= trigger and trigger > 0,
                    note="Maximum acceptable chase range",
                )
            )

            s4_status = "PASS" if trigger > 0 else "BLOCK"
            stages.append(
                StageResult(
                    stage_name="Entry Planner",
                    status=s4_status,
                    checks=s4_checks,
                    rejection_reasons=s4_rejections,
                )
            )

            # ------------------------------------------------------------------
            # STAGE 5: EXIT PLANNER
            # ------------------------------------------------------------------
            s5_checks: List[StageCheck] = []
            s5_rejections: List[str] = []

            stop = chosen_cand.stop
            target1 = chosen_cand.target1
            risk_per_share = (trigger - stop) if trigger > stop else 0.0

            s5_checks.append(
                StageCheck(
                    name="Structural Stop Loss",
                    value=f"{stop:.2f}",
                    threshold="Lowest low 10 bars - 0.2*ATR",
                    passed=stop > 0 and stop < trigger,
                    note=f"Risk/share: {risk_per_share:.2f}",
                )
            )
            s5_checks.append(
                StageCheck(
                    name="Target 1 (2R)",
                    value=f"{target1:.2f}",
                    threshold=f">= trigger + 2R ({trigger + 2*risk_per_share:.2f})",
                    passed=target1 >= trigger + 1.9 * risk_per_share,
                    note="Minimum reward/risk ratio 2.0",
                )
            )
            s5_checks.append(
                StageCheck(
                    name="Trailing Exit Strategy",
                    value="Chandelier trail (3*ATR from high) after +1R",
                    threshold="Configured",
                    passed=True,
                    note="Breakeven moved at +1R",
                )
            )

            s5_status = "PASS" if stop > 0 and stop < trigger else "BLOCK"
            stages.append(
                StageResult(
                    stage_name="Exit Planner",
                    status=s5_status,
                    checks=s5_checks,
                    rejection_reasons=s5_rejections,
                )
            )

            # ------------------------------------------------------------------
            # STAGE 6: POSITION SIZER
            # ------------------------------------------------------------------
            s6_checks: List[StageCheck] = []
            s6_rejections: List[str] = []

            gap95 = compute_gap95(df) if df is not None else 0.02
            eff_risk = calculate_effective_risk_per_share(trigger, stop, gap95) if trigger > stop else 1.0

            sizer = PositionSizer(market=market)
            sizing = sizer.calculate_size(
                symbol=symbol,
                entry=trigger,
                stop=stop,
                effective_risk_per_share=eff_risk,
                capital_override=capital,
                current_open_positions=current_open_positions,
                current_open_heat=current_open_heat,
            )

            s6_checks.append(
                StageCheck(
                    name="Effective Risk per Share (with Gap95)",
                    value=f"{eff_risk:.2f} (gap95: {gap95*100:.1f}%)",
                    threshold=f">= nominal risk {trigger - stop:.2f}",
                    passed=eff_risk >= (trigger - stop),
                    note="Adjusts sizing downward for gappy stocks",
                )
            )
            s6_checks.append(
                StageCheck(
                    name="Calculated Whole Share Quantity",
                    value=f"{sizing.qty} shares",
                    threshold=">= 1 share",
                    passed=sizing.qty >= 1,
                    note=f"Position value: {sizing.position_value:.2f}",
                )
            )

            if sizing.qty < 1:
                s6_rejections.append(f"Position size is 0: {sizing.rejection_reason}")

            s6_status = "PASS" if sizing.qty >= 1 else "BLOCK"
            stages.append(
                StageResult(
                    stage_name="Position Sizer",
                    status=s6_status,
                    checks=s6_checks,
                    rejection_reasons=s6_rejections,
                )
            )
            all_rejections.extend(s6_rejections)

            # ------------------------------------------------------------------
            # STAGE 7: RISK VALIDATOR (Cost Gate, Heat, Correlation, Circuit Breakers)
            # ------------------------------------------------------------------
            from app.engine.risk_validator import RiskValidator
            validator = RiskValidator(market=market)
            risk_res = validator.validate(
                symbol=symbol,
                entry_price=trigger,
                stop_loss=stop,
                qty=sizing.qty,
                risk_amount=sizing.risk_amount,
                cost_breakdown=sizing.cost_breakdown,
                capital=capital,
                current_open_positions=current_open_positions,
                current_open_heat=current_open_heat,
                open_symbols=open_symbols,
                all_universe_data=all_universe_data,
            )

            stages.append(
                StageResult(
                    stage_name="Risk Validator",
                    status=risk_res.status,
                    checks=risk_res.checks,
                    rejection_reasons=risk_res.rejection_reasons,
                )
            )
            all_rejections.extend(risk_res.rejection_reasons)

        # Persist/display audit stages in the same order as the Research Desk flow.
        # Sorting changes presentation only; final PASS/BLOCK/WAIT calculation is unchanged.
        stage_order = {
            "Scanner": 0,
            "Setup Validator": 1,
            "Fundamentalist": 2,
            "News/Event Analyst": 3,
            "Entry Planner": 4,
            "Exit Planner": 5,
            "Position Sizer": 6,
            "Risk Validator": 7,
        }
        stages.sort(key=lambda stage: stage_order.get(stage.stage_name, 99))

        # ------------------------------------------------------------------
        # FINAL DECISION: PASS | BLOCK | WAIT
        # ------------------------------------------------------------------
        has_blocks = any(s.status == "BLOCK" for s in stages)
        has_waits = any(s.status == "WAIT" for s in stages)

        if has_blocks:
            final_decision = "BLOCK"
        elif has_waits:
            final_decision = "WAIT"
        else:
            final_decision = "PASS"

        decision = PipelineDecision(
            symbol=symbol,
            market=market,
            asof_date=asof_date,
            mode=mode,
            final_decision=final_decision,
            setup=chosen_cand.setup if chosen_cand else None,
            trigger=trigger if chosen_cand else None,
            entry_zone_high=zone_high if chosen_cand else None,
            stop=stop if chosen_cand else None,
            target1=target1 if chosen_cand else None,
            qty=sizing.qty if (chosen_cand and sizing and sizing.passed) else 0,
            risk_amount=sizing.risk_amount if (chosen_cand and sizing and sizing.passed) else 0.0,
            cost_in_r=sizing.cost_breakdown.cost_in_r if (chosen_cand and sizing and sizing.cost_breakdown) else 0.0,
            stages=stages,
            all_rejection_reasons=[r.strip() for r in all_rejections if isinstance(r, str) and r.strip()],
            config_hash=config_hash,
            code_version=self.code_version,
            data_source="ANGEL_ONE" if market == "IN" else "ALPACA",
        )

        # Persist Audit Trail to DB if session provided
        if db is not None:
            try:
                audit = DecisionAudit(
                    symbol=symbol,
                    market=market,
                    asof_date=asof_date,
                    mode=mode,
                    final_decision=final_decision,
                    setup=decision.setup,
                    trigger=decision.trigger,
                    stop=decision.stop,
                    target1=decision.target1,
                    qty=decision.qty,
                    risk_amount=decision.risk_amount,
                    cost_in_r=decision.cost_in_r,
                    config_hash=config_hash,
                    code_version=self.code_version,
                    data_source=decision.data_source,
                )
                db.add(audit)
                db.flush()

                for stage in stages:
                    st_row = DecisionStageResult(
                        audit_id=audit.id,
                        stage_name=stage.stage_name,
                        status=stage.status,
                        checks_json=json.dumps([c.model_dump() for c in stage.checks]),
                        rejection_reasons_json=json.dumps(stage.rejection_reasons),
                    )
                    db.add(st_row)

                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error persisting decision audit for {symbol}: {e}")

        return decision


decision_pipeline = DecisionPipeline()
