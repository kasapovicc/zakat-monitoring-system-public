"""
Scheduler for automatic zakat analysis

Uses APScheduler to run analysis on the 1st of each Hijri month.
Includes missed-job recovery for when the app wasn't running.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
from typing import Optional, Callable

from hijri_converter import Gregorian

logger = logging.getLogger(__name__)


class ZakatScheduler:
    """Scheduler for automatic zakat analysis"""

    def __init__(
        self,
        on_analysis_trigger: Callable,
        data_dir: Optional[Path] = None
    ):
        """
        Initialize scheduler.

        Args:
            on_analysis_trigger: Callback function to run analysis
            data_dir: Directory to store scheduler state
        """
        self.on_analysis_trigger = on_analysis_trigger

        if data_dir is None:
            self.data_dir = Path.home() / "Library" / "Application Support" / "Zekat"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "scheduler_state.json"

        self.scheduler = BackgroundScheduler()
        self.last_run: Optional[datetime] = None

        self._load_state()

    def _load_state(self):
        """Load scheduler state from disk"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    if 'last_run' in state:
                        self.last_run = datetime.fromisoformat(state['last_run'])
            except Exception as e:
                logger.warning(f"Failed to load scheduler state: {e}")

    def _save_state(self):
        """Save scheduler state to disk"""
        try:
            state = {
                'last_run': self.last_run.isoformat() if self.last_run else None
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"Failed to save scheduler state: {e}")

    def _should_run_missed_job(self) -> bool:
        """
        Check if a monthly analysis was missed.

        Returns:
            True if analysis should run due to missed schedule
        """
        if not self.last_run:
            # Never run before, run now
            return True

        # Get current Hijri date by converting from Gregorian
        today = datetime.now()
        current_hijri = Gregorian(today.year, today.month, today.day).to_hijri()

        # Get last run Hijri date by converting from Gregorian
        last_hijri = Gregorian(
            self.last_run.year,
            self.last_run.month,
            self.last_run.day
        ).to_hijri()

        # Check if we're in a different Hijri month
        if current_hijri.month != last_hijri.month or current_hijri.year != last_hijri.year:
            # Different month, should run
            return True

        return False

    def _run_analysis(self):
        """Execute analysis and update last run time"""
        logger.info("Scheduler triggering analysis...")

        try:
            # Call the analysis callback
            self.on_analysis_trigger()

            # Update last run time
            self.last_run = datetime.now()
            self._save_state()

            logger.info("Scheduled analysis completed")

        except Exception as e:
            logger.error(f"Scheduled analysis failed: {e}")

    def start(self):
        """Start the scheduler"""
        # Check for missed job on startup
        if self._should_run_missed_job():
            logger.info("Missed monthly analysis detected, running now...")
            self._run_analysis()

        # Schedule monthly analysis on 1st of each month at 10:00 AM
        # Note: This uses Gregorian calendar. For exact Hijri dates,
        # a more complex implementation would be needed.
        self.scheduler.add_job(
            self._run_analysis,
            trigger=CronTrigger(day=1, hour=10, minute=0),
            id='monthly_analysis',
            name='Monthly Zakat Analysis',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def trigger_now(self):
        """Manually trigger analysis immediately"""
        self._run_analysis()

    def get_next_run_time(self) -> Optional[datetime]:
        """
        Get the next scheduled run time.

        Returns:
            Next run datetime or None if not scheduled
        """
        job = self.scheduler.get_job('monthly_analysis')
        if job:
            return job.next_run_time
        return None

    def is_running(self) -> bool:
        """Check if scheduler is running"""
        return self.scheduler.running
