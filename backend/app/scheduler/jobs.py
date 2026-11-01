import datetime
import logging
import shutil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

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


def job_db_backup(db):
    """Nightly point-in-time snapshot backup of Neon PostgreSQL database."""
    from app.db_backup import create_database_backup
    res = create_database_backup(db=db)
    logger.info(f"Nightly database backup completed: {res.get('file')} ({res.get('total_rows')} rows)")


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            log_job_execution("eod_scan_IN", job_eod_scan_in),
            CronTrigger(hour=16, minute=30),
            id="eod_scan_IN",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("eod_scan_US", job_eod_scan_us),
            CronTrigger(hour=21, minute=45),
            id="eod_scan_US",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("live_monitor_IN", job_live_monitor_in),
            IntervalTrigger(seconds=30),
            id="live_monitor_IN",
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
            log_job_execution("kite_sync", job_kite_sync),
            IntervalTrigger(minutes=5),
            id="kite_sync",
            replace_existing=True,
        )
        scheduler.add_job(
            log_job_execution("db_backup", job_db_backup),
            CronTrigger(hour=23, minute=59),
            id="db_backup",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Background job scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background job scheduler stopped.")

