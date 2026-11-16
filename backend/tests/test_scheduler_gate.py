"""
Unit tests for Phase 5 Forward Paper-Trading Scheduler Gate.
Verifies that:
1. forward_paper_trading_enabled defaults to False in settings.
2. job_daily_paper_trading is fail-closed and returns immediately when gate is False.
3. job_weekly_paper_reporting is fail-closed and returns immediately when gate is False.
4. start_scheduler() does not register daily_paper_trading or weekly_paper_reporting when gate is False.
"""

from unittest.mock import patch, MagicMock
from app.settings import settings
from app.scheduler import jobs


def test_forward_paper_trading_gate_defaults_to_false():
    """Verify that settings.forward_paper_trading_enabled defaults to False."""
    assert hasattr(settings, "forward_paper_trading_enabled")
    assert settings.forward_paper_trading_enabled is False


def test_job_daily_paper_trading_skipped_when_disabled():
    """Verify job_daily_paper_trading immediately exits when gate is False."""
    with patch("app.settings.settings.forward_paper_trading_enabled", False):
        with patch("app.engine.cycle4_paper.Cycle4PaperEngine") as mock_engine:
            jobs.job_daily_paper_trading(db=None)
            mock_engine.assert_not_called()


def test_job_weekly_paper_reporting_skipped_when_disabled():
    """Verify job_weekly_paper_reporting immediately exits when gate is False."""
    with patch("app.settings.settings.forward_paper_trading_enabled", False):
        with patch("research.cycle4.weekly_reporter.generate_weekly_report", create=True) as mock_report:
            jobs.job_weekly_paper_reporting(db=None)
            mock_report.assert_not_called()


def test_scheduler_does_not_register_paper_trading_jobs_when_disabled():
    """Verify start_scheduler() excludes paper-trading jobs when gate is False."""
    # Temporarily stop scheduler if running
    was_running = jobs.scheduler.running
    if was_running:
        jobs.scheduler.shutdown(wait=False)

    try:
        # Clear any existing jobs
        jobs.scheduler.remove_all_jobs()

        with patch("app.settings.settings.forward_paper_trading_enabled", False):
            # Run start_scheduler logic
            jobs.start_scheduler()

            registered_ids = [job.id for job in jobs.scheduler.get_jobs()]
            assert "daily_paper_trading" not in registered_ids
            assert "weekly_paper_reporting" not in registered_ids

            # Ensure unrelated core jobs are still registered
            assert "eod_scan_IN" in registered_ids
    finally:
        # Clean up
        if jobs.scheduler.running:
            jobs.scheduler.shutdown(wait=False)
