import datetime
import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backtest.montecarlo import run_monte_carlo
from app.backtest.simulator import BacktestSimulator
from app.db import get_db
from app.engine.universe import universe_manager
from app.models import BacktestRun, BacktestTrade
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class BacktestRequest(BaseModel):
    market: str = "IN"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    capital: Optional[float] = 17500.0
    setup_filter: str = "ALL"  # ALL, VCP, PULLBACK


@router.post("/backtests")
def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """Runs a historical simulation over universe stocks using conservative fill rules."""
    end_d = datetime.date.fromisoformat(req.end_date) if req.end_date else datetime.date.today()
    start_d = datetime.date.fromisoformat(req.start_date) if req.start_date else (end_d - datetime.timedelta(days=730))

    stocks = universe_manager.load_universe(req.market)
    symbols = [s.symbol for s in stocks][:30]  # run on top liquid constituents
    if not symbols:
        symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]

    bars_dict = provider_manager.get_daily_bars(
        symbols, start_d - datetime.timedelta(days=100), end_d, market=req.market, db=db
    )

    simulator = BacktestSimulator(market=req.market)
    sim_result = simulator.run(
        bars_data=bars_dict,
        start_date=start_d,
        end_date=end_d,
        capital=req.capital,
        setup_filter=req.setup_filter,
    )

    # Run Monte Carlo on the simulated trades
    mc_result = run_monte_carlo(sim_result["trades"], initial_capital=req.capital or 17500.0)

    # Persist run to DB
    run_record = BacktestRun(
        universe=f"{req.market}_TOP_{len(symbols)}",
        start_date=start_d,
        end_date=end_d,
        config_json=json.dumps(req.model_dump()),
        metrics_json=json.dumps(
            {
                "metrics": sim_result["metrics"],
                "monte_carlo": mc_result.model_dump(),
                "survivorship_bias_notice": sim_result["survivorship_bias_notice"],
            }
        ),
        status="COMPLETED",
    )
    db.add(run_record)
    db.flush()

    for t in sim_result["trades"]:
        bt_trade = BacktestTrade(
            run_id=run_record.id,
            symbol=t["symbol"],
            setup=t["setup"],
            entry_date=datetime.date.fromisoformat(str(t["entry_date"])),
            entry_price=t["entry_price"],
            exit_date=datetime.date.fromisoformat(str(t["exit_date"])),
            exit_price=t["exit_price"],
            exit_reason=t["exit_reason"],
            qty=t["qty"],
            pnl=t["pnl"],
            r_multiple=t["r_multiple"],
            costs=t["costs"],
        )
        db.add(bt_trade)

    db.commit()

    return {
        "id": run_record.id,
        "metrics": sim_result["metrics"],
        "monte_carlo": mc_result.model_dump(),
        "equity_curve": sim_result["equity_curve"],
        "trades_count": len(sim_result["trades"]),
        "trades": sim_result["trades"][:50],  # preview top 50
        "survivorship_bias_notice": sim_result["survivorship_bias_notice"],
    }


class ScenarioLabRequest(BaseModel):
    symbol: str
    market: str = "IN"
    trigger: float
    stop: float
    asof_date: Optional[str] = None
    n_simulations: Optional[int] = 10000
    seed: Optional[int] = 42


@router.post("/scenario-lab")
def run_scenario_lab(req: ScenarioLabRequest, db: Session = Depends(get_db)):
    """Runs Swing Replay & Scenario Lab (Spec 12.6).
    Produces separate Observed (historical analogues) and Simulated (block bootstrap)
    first-passage metrics across 5, 10, 20 session horizons with zero look-ahead.
    """
    from app.backtest.scenario_lab import scenario_lab
    asof_d = datetime.date.fromisoformat(req.asof_date) if req.asof_date else datetime.date.today()
    start_d = asof_d - datetime.timedelta(days=730)

    # Load symbol data and top universe data for analogue discovery
    universe_stocks = universe_manager.load_universe(req.market)
    analogue_symbols = [s.symbol for s in universe_stocks][:15]
    if req.symbol not in analogue_symbols:
        analogue_symbols.append(req.symbol)

    bars_dict = provider_manager.get_daily_bars(
        analogue_symbols, start_d, asof_d, market=req.market, db=db
    )
    df_sym = bars_dict.get(req.symbol)
    if df_sym is None or df_sym.empty:
        raise HTTPException(status_code=400, detail=f"No price data available for {req.symbol}")

    res = scenario_lab.evaluate(
        symbol=req.symbol,
        df=df_sym,
        trigger=req.trigger,
        stop=req.stop,
        asof=asof_d,
        all_historical_dfs=bars_dict,
        n_simulations=req.n_simulations or 10000,
        seed=req.seed or 42,
    )
    return res.model_dump()



@router.get("/backtests/{run_id}")
def get_backtest_run(run_id: int, db: Session = Depends(get_db)):
    run_record = db.query(BacktestRun).filter(BacktestRun.id == run_id).first()
    if not run_record:
        raise HTTPException(status_code=404, detail="Backtest run not found")

    trades = db.query(BacktestTrade).filter(BacktestTrade.run_id == run_id).all()
    metrics_data = json.loads(run_record.metrics_json) if run_record.metrics_json else {}

    return {
        "id": run_record.id,
        "universe": run_record.universe,
        "start_date": run_record.start_date.isoformat(),
        "end_date": run_record.end_date.isoformat(),
        "status": run_record.status,
        "metrics": metrics_data.get("metrics"),
        "monte_carlo": metrics_data.get("monte_carlo"),
        "survivorship_bias_notice": metrics_data.get("survivorship_bias_notice"),
        "trades": [
            {
                "symbol": t.symbol,
                "setup": t.setup,
                "entry_date": t.entry_date.isoformat(),
                "entry_price": t.entry_price,
                "exit_date": t.exit_date.isoformat(),
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "qty": t.qty,
                "pnl": t.pnl,
                "r_multiple": t.r_multiple,
                "costs": t.costs,
            }
            for t in trades
        ],
    }

