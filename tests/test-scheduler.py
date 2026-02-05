"""Tests for ZakatScheduler"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from app.scheduler import ZakatScheduler


class TestSchedulerInit:
    """Tests for scheduler initialization"""

    def test_init_creates_data_dir(self, tmp_path):
        """Should create data directory on init"""
        callback = MagicMock()
        data_dir = tmp_path / "test-data"

        scheduler = ZakatScheduler(
            on_analysis_trigger=callback,
            data_dir=data_dir
        )

        try:
            assert data_dir.exists()
            assert scheduler.data_dir == data_dir
        finally:
            if scheduler.is_running():
                scheduler.stop()

    def test_init_with_existing_dir(self, tmp_path):
        """Should work with existing data directory"""
        callback = MagicMock()
        data_dir = tmp_path / "existing"
        data_dir.mkdir()

        scheduler = ZakatScheduler(
            on_analysis_trigger=callback,
            data_dir=data_dir
        )

        try:
            assert data_dir.exists()
            assert scheduler.data_dir == data_dir
        finally:
            if scheduler.is_running():
                scheduler.stop()


class TestMissedJobDetection:
    """Tests for missed job detection"""

    def test_should_run_missed_job_never_run(self, tmp_path):
        """Should return True if never run before"""
        callback = MagicMock()
        scheduler = ZakatScheduler(
            on_analysis_trigger=callback,
            data_dir=tmp_path
        )

        try:
            assert scheduler._should_run_missed_job() is True
        finally:
            if scheduler.is_running():
                scheduler.stop()

    def test_should_run_missed_job_recent_run(self, tmp_path):
        """Should return False if run recently"""
        callback = MagicMock()
        scheduler = ZakatScheduler(
            on_analysis_trigger=callback,
            data_dir=tmp_path
        )

        try:
            # Record a run
            scheduler._record_run()

            # Should not need to run again immediately
            assert scheduler._should_run_missed_job() is False
        finally:
            if scheduler.is_running():
                scheduler.stop()


class TestSchedulerLifecycle:
    """Tests for scheduler start/stop"""

    def test_start_and_stop(self, tmp_path):
        """Should start and stop cleanly"""
        callback = MagicMock()
        scheduler = ZakatScheduler(
            on_analysis_trigger=callback,
            data_dir=tmp_path
        )

        # Start scheduler
        scheduler.start()
        assert scheduler.is_running() is True

        # Stop scheduler
        scheduler.stop()
        assert scheduler.is_running() is False

    def test_stop_when_not_running(self, tmp_path):
        """Should handle stop when not running"""
        callback = MagicMock()
        scheduler = ZakatScheduler(
            on_analysis_trigger=callback,
            data_dir=tmp_path
        )

        # Stop without starting (should not raise)
        scheduler.stop()
        assert scheduler.is_running() is False
