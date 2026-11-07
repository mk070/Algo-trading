import datetime
import logging
import shutil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd

from app.db import SessionLocal
from app.engine.newsfilter import news_engine
from app.engine.planner import planner
from app.models import JobRun, NewsSourceState
from app.notify.dispatcher import dispatcher
from app.providers.manager import provider_manager
from app.scheduler.monitor import live_monitor
from app.settings import DATA_DIR

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def log_job_execution(job_name: str, func):
    def wrapper(*args, **kwargs):
        db = SessionLocal()
        job_run = JobRun(job=job_name, started_at=datetime.datetime.utcnow(), status="RUNNING")
        db.add(job_run)
        db.commit()
        try:
            func(db, *args, **kwargs)
            job_run.status = "SUCCESS"
            job_run.finished_at = datetime.datetime.utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            job_run.status = "FAILED"
            job_run.finished_at = datetime.datetime.utcnow()
            job_run.detail = str(e)
            db.commit()
            logger.error(f"Job {job_name} failed: {e}")
        finally:
            db.close()

    return wrapper


def job_eod_scan_in(db):
    logger.info("Executing EOD scan for Indian Market (IN)...")
    plan = planner.run_scan(market="IN", db=db)
    # Notify EOD plan summary to Telegram
    summary = (
        f"📋 <b>EOD TRADE PLAN (IN) - {plan.session_date}</b>\n\n"
        f"• Market Regime: <b>{plan.regime.status}</b> ({plan.regime.detail})\n"
        f"• Universe Screened: {plan.universe_size} stocks ({plan.passed_filters} passed)\n"
        f"• Setups Shortlisted: <b>{len(plan.signals)}</b>\n\n"
    )
    if plan.signals:
        for s in plan.signals:
            summary += f"▶ <b>{s.symbol}</b> ({s.setup}) | Buy > {s.trigger:.2f} | SL {s.stop:.2f} | Qty {s.qty}\n"
    else:
        summary += "<i>No qualifying setups today: doing nothing is a valid trade.</i>"

    dispatcher.dispatch(
        alert_type="SYSTEM",
        title="Indian EOD Trade Plan Ready",
        body=summary,
        market="IN",
        db=db,
    )


def job_eod_scan_us(db):
    logger.info("Executing EOD scan for US Market (US)...")
    planner.run_scan(market="US", db=db)


def job_live_monitor_in(db):
    live_monitor.tick_market(market="IN", db=db)


def job_live_monitor_us(db):
    live_monitor.tick_market(market="US", db=db)


def job_kite_sync(db):
    if provider_manager.kite.is_authenticated():
        logger.info("Syncing Kite Personal holdings and positions...")
        provider_manager.kite.holdings()
        provider_manager.kite.positions()


def job_poll_news_p0(db):
    """Priority 0 news polling (every 15 min): NSE Corporate Announcements & Results."""
    logger.info("Executing P0 news poll (NSE Announcements & Financial Results)...")
    for feed_key in ("Corporate_announcements", "Financial_Results"):
        res = news_engine.nse_collector.fetch_feed(feed_key)
        news_engine.update_source_health(
            source="nse_rss",
            success=res.success,
            latency_sec=res.latency_sec,
            error=res.error,
            items_count=len(res.items),
            etag=res.etag,
            last_modified=res.last_modified,
            db=db,
        )
        if res.success:
            for item in res.items:
                news_engine.ingest_raw_item(item, db=db)


def job_poll_news_p1(db):
    """Priority 1 news polling (every 30 min): Board Meetings & Corporate Actions."""
    logger.info("Executing P1 news poll (NSE Board Meetings & Actions)...")
    for feed_key in ("Board_Meetings", "Corp_action"):
        res = news_engine.nse_collector.fetch_feed(feed_key)
        if res.success:
            for item in res.items:
                news_engine.ingest_raw_item(item, db=db)


def job_poll_macro_calendar(db):
    """Macro event poll (every 6 hours): Central Bank policy releases."""
    logger.info("Executing macro news poll (RBI and Fed Press Releases)...")
    rbi_res = news_engine.central_bank_collector.fetch_rbi_news()
    news_engine.update_source_health(
        source="rbi_rss",
        success=rbi_res.success,
        latency_sec=rbi_res.latency_sec,
        error=rbi_res.error,
        items_count=len(rbi_res.items),
        etag=rbi_res.etag,
        last_modified=rbi_res.last_modified,
        db=db,
    )
    if rbi_res.success:
        for item in rbi_res.items:
            news_engine.ingest_raw_item(item, db=db)

    fed_res = news_engine.central_bank_collector.fetch_fed_news()
    news_engine.update_source_health(
        source="fed_rss",
        success=fed_res.success,
        latency_sec=fed_res.latency_sec,
        error=fed_res.error,
        items_count=len(fed_res.items),
        etag=fed_res.etag,
        last_modified=fed_res.last_modified,
        db=db,
    )
    if fed_res.success:
        for item in fed_res.items:
            news_engine.ingest_raw_item(item, db=db)


def job_poll_media_news(db):
    """Periodic poll of live financial press (Yahoo Finance, Moneycontrol, Reuters)
    for top universe and watchlist symbols.
    """
    logger.info("Polling real-time financial media news (Yahoo Finance, Reuters, Moneycontrol)...")
    from app.engine.universe import universe_manager
    in_stocks = [s.symbol for s in universe_manager.load_universe("IN")][:5]
    us_stocks = [s.symbol for s in universe_manager.load_universe("US")][:5]
    news_engine.poll_financial_news(in_stocks, market="IN", db=db)
    news_engine.poll_financial_news(us_stocks, market="US", db=db)


def job_db_backup(db):
    """Nightly point-in-time snapshot backup of Neon PostgreSQL database."""
    from app.db_backup import create_database_backup
    res = create_database_backup(db=db)
    logger.info(f"Nightly database backup completed: {res.get('file')} ({res.get('total_rows')} rows)")


def job_universe_master_sync(db):
    """Weekly sync of Angel One instrument master and universe coverage."""
    from app.engine.universe import universe_manager
    logger.info("Executing scheduled weekly Angel One instrument master sync...")
    res = universe_manager.refresh_instrument_master(market="IN", db=db)
    logger.info(f"Instrument master sync completed: {res}")


def job_refresh_fundamentals_weekly(db):
    """Weekly fundamentals refresh for top liquid universe equities."""
    from app.engine.universe import universe_manager
    from app.engine.fundamentals_engine import fundamentals_engine
    logger.info("Executing scheduled weekly fundamental snapshots refresh...")
    universe = universe_manager.load_universe("IN")
    liquid_symbols = [s.symbol for s in universe if s.tier in ("Large", "Mid")][:100]
    for sym in liquid_symbols:
        try:
            fundamentals_engine.fetch_and_store_yfinance(sym, market="IN", db=db)
        except Exception as e:
            logger.debug(f"Weekly fundamentals skip {sym}: {e}")
    logger.info(f"Weekly fundamental snapshots refresh completed for {len(liquid_symbols)} symbols.")




def job_daily_paper_trading(db):
    """Executes daily paper-trading step at 16:00 IST post-market close."""
    from app.engine.cycle4_paper import Cycle4PaperEngine, run_cycle4_daily_step
    from app.engine.calendars import is_exchange_holiday
    import sys
    proj_root = Path(__file__).resolve().parent.parent.parent.parent
    if str(proj_root) not in sys.path:
        sys.path.insert(0, str(proj_root))
    from research.cycle4.daily_paper_runner import load_market_data

    today = datetime.date.today()
    if is_exchange_holiday("IN", today):
        logger.info(f"Daily paper trading skipped: {today} is an official exchange holiday or weekend.")
        return

    try:
        snap_df, bench_df = load_market_data(today)
    except Exception as e:
        logger.error(f"Paper trading market data loading failed: {e}")
        return

    engine = Cycle4PaperEngine(
        universe_path="data/universe/research_universe_v1.csv",
        state_dir="research/cycle4/state",
        initial_capital=17500.0,
    )

    past_dates = [r["date"] for r in engine.candidate_state.daily_history]
    if str(today) in past_dates:
        logger.info(f"Session {today} already marked to market. Skipping duplicate execution.")
        return

    res = run_cycle4_daily_step(
        engine=engine,
        session_date=today,
        historical_bars=snap_df,
        benchmark_df=bench_df,
        force_rebalance=False,
    )
    logger.info(f"Daily paper trading completed: {res.get('status')}")


def job_weekly_paper_reporting(db):
    """Executes Friday weekly paper-trading audit and report generation at 17:00 IST."""
    import sys
    proj_root = Path(__file__).resolve().parent.parent.parent.parent
    if str(proj_root) not in sys.path:
        sys.path.insert(0, str(proj_root))
    from research.cycle4.weekly_reporter import generate_weekly_report
    state_dir = Path("research/cycle4/state")
    output_dir = Path("research/cycle4/weekly_reviews")
    report_file = generate_weekly_report(state_dir=state_dir, output_dir=output_dir)
    logger.info(f"Weekly paper-trading review generated: {report_file}")


def start_scheduler():
    if not scheduler.running:
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        scheduler.add_job(
            log_job_execution("daily_paper_trading", job_daily_paper_trading),
            CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=kolkata_tz),
            id="daily_paper_trading",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("weekly_paper_reporting", job_weekly_paper_reporting),
            CronTrigger(day_of_week="fri", hour=17, minute=0, timezone=kolkata_tz),
            id="weekly_paper_reporting",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("eod_scan_IN", job_eod_scan_in),
            CronTrigger(hour=16, minute=30, timezone=ZoneInfo("Asia/Kolkata")),
            id="eod_scan_IN",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("eod_scan_US", job_eod_scan_us),
            CronTrigger(hour=21, minute=45, timezone=ZoneInfo("Asia/Kolkata")),
            id="eod_scan_US",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("live_monitor_IN", job_live_monitor_in),
            IntervalTrigger(seconds=60),
            id="live_monitor_IN",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("live_monitor_US", job_live_monitor_us),
            IntervalTrigger(seconds=60),
            id="live_monitor_US",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("news_poll_P0", job_poll_news_p0),
            IntervalTrigger(minutes=15),
            id="news_poll_P0",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("news_poll_P1", job_poll_news_p1),
            IntervalTrigger(minutes=30),
            id="news_poll_P1",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("macro_poll", job_poll_macro_calendar),
            IntervalTrigger(hours=6),
            id="macro_poll",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("news_media_poll", job_poll_media_news),
            IntervalTrigger(minutes=5),
            id="news_media_poll",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("kite_sync", job_kite_sync),
            IntervalTrigger(minutes=5),
            id="kite_sync",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("db_backup", job_db_backup),
            CronTrigger(hour=23, minute=59, timezone=ZoneInfo("Asia/Kolkata")),
            id="db_backup",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("universe_master_sync", job_universe_master_sync),
            CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=ZoneInfo("Asia/Kolkata")),
            id="universe_master_sync",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("fundamentals_weekly", job_refresh_fundamentals_weekly),
            CronTrigger(day_of_week="sun", hour=4, minute=0, timezone=ZoneInfo("Asia/Kolkata")),
            id="fundamentals_weekly",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Background job scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background job scheduler stopped.")

