"""
Adapter layer for ZakatMonitor

Wraps the ZakatMonitor class to allow config injection from local encrypted storage
instead of relying solely on environment variables.
Supports both old single-source and new multi-source config formats.
"""

import os
import sys
from typing import Dict, Optional, Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from zakat_monitor import ZakatMonitor, AnalysisResult


class ZakatMonitorAdapter:
    """
    Adapter that wraps ZakatMonitor and allows config injection.

    Supports two config formats:
    - Old format: single 'email' + 'accounts' objects
    - New format: 'email_sources' array + 'report_delivery' object
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._original_env: Dict[str, Optional[str]] = {}
        self.monitor: Optional[ZakatMonitor] = None

    def _is_new_config_format(self) -> bool:
        """Check if config uses the new multi-source format"""
        return 'email_sources' in self.config

    def _set_env_from_config(self):
        """Temporarily override environment variables with config values."""
        if self._is_new_config_format():
            self._set_env_from_new_config()
        else:
            self._set_env_from_old_config()

    def _set_env_from_new_config(self):
        """Set env vars from new multi-source config format."""
        sources = self.config.get('email_sources', [])
        report = self.config.get('report_delivery', {})

        env_mappings = {}

        # First source -> primary env vars
        if len(sources) >= 1:
            src = sources[0]
            pairs = src.get('account_pairs', [])
            env_mappings['IMAP_SERVER'] = src.get('imap_server', 'imap.gmail.com')
            env_mappings['IMAP_PORT'] = str(src.get('imap_port', 993))
            env_mappings['EMAIL_USERNAME'] = src.get('email')
            env_mappings['EMAIL_PASSWORD'] = src.get('password')
            if pairs:
                env_mappings['BAM_ACCOUNT'] = pairs[0].get('bam_account')
                env_mappings['EUR_ACCOUNT'] = pairs[0].get('eur_account')

        # Second source -> company env vars
        if len(sources) >= 2:
            src = sources[1]
            pairs = src.get('account_pairs', [])
            env_mappings['COMPANY_EMAIL_USERNAME'] = src.get('email')
            env_mappings['COMPANY_EMAIL_PASSWORD'] = src.get('password')
            if pairs:
                env_mappings['COMPANY_BAM_ACCOUNT'] = pairs[0].get('bam_account')
                env_mappings['COMPANY_EUR_ACCOUNT'] = pairs[0].get('eur_account')

        # Report delivery -> SMTP env vars
        env_mappings['SMTP_SERVER'] = report.get('smtp_server', 'smtp.gmail.com')
        env_mappings['SMTP_PORT'] = str(report.get('smtp_port', 587))
        env_mappings['SENDER_EMAIL'] = report.get('sender_email')
        env_mappings['RECIPIENT_EMAIL'] = report.get('recipient_email')

        # Other config
        env_mappings['ZAKAT_ENCRYPTION_KEY'] = self.config.get('encryption_key')
        env_mappings['ADDITIONAL_ASSETS'] = str(self.config.get('additional_assets', 0))
        env_mappings['NISAB_FALLBACK_BAM'] = str(self.config.get('nisab_fallback_bam', 24624.0))

        self._apply_env_mappings(env_mappings)

    def _set_env_from_old_config(self):
        """Set env vars from old single-source config format."""
        env_mappings = {
            'IMAP_SERVER': self.config.get('email', {}).get('imap_server'),
            'IMAP_PORT': str(self.config.get('email', {}).get('imap_port', 993)),
            'SMTP_SERVER': self.config.get('email', {}).get('smtp_server'),
            'SMTP_PORT': str(self.config.get('email', {}).get('smtp_port', 587)),
            'EMAIL_USERNAME': self.config.get('email', {}).get('username'),
            'EMAIL_PASSWORD': self.config.get('email', {}).get('password'),
            'SENDER_EMAIL': self.config.get('email', {}).get('sender_email'),
            'RECIPIENT_EMAIL': self.config.get('email', {}).get('recipient_email'),
            'BAM_ACCOUNT': self.config.get('accounts', {}).get('bam_account'),
            'EUR_ACCOUNT': self.config.get('accounts', {}).get('eur_account'),
            'COMPANY_EMAIL_USERNAME': self.config.get('company', {}).get('email_username'),
            'COMPANY_EMAIL_PASSWORD': self.config.get('company', {}).get('email_password'),
            'COMPANY_BAM_ACCOUNT': self.config.get('company', {}).get('bam_account'),
            'COMPANY_EUR_ACCOUNT': self.config.get('company', {}).get('eur_account'),
            'ZAKAT_ENCRYPTION_KEY': self.config.get('encryption_key'),
            'ADDITIONAL_ASSETS': str(self.config.get('additional_assets', 0)),
            'NISAB_FALLBACK_BAM': str(self.config.get('nisab_fallback_bam', 24624.0)),
        }
        self._apply_env_mappings(env_mappings)

    @staticmethod
    def _sanitize_value(value: str) -> str:
        """Remove non-breaking spaces and other invisible Unicode whitespace from config values.

        These commonly appear from copy-pasting on macOS (Option+Space = \\xa0).
        """
        return value.replace('\xa0', ' ').strip()

    def _apply_env_mappings(self, env_mappings: Dict[str, Optional[str]]):
        """Apply env var mappings, saving originals for restoration."""
        for key, value in env_mappings.items():
            self._original_env[key] = os.environ.get(key)
            if value is not None:
                os.environ[key] = self._sanitize_value(value)
            elif key in os.environ:
                del os.environ[key]

    def _restore_env(self):
        """Restore original environment variables."""
        for key, original_value in self._original_env.items():
            if original_value is not None:
                os.environ[key] = original_value
            elif key in os.environ:
                del os.environ[key]
        self._original_env.clear()

    # Stable data directory for balance history (matches ConfigStorage)
    _DATA_DIR = Path.home() / "Library" / "Application Support" / "Zekat"

    def initialize(self):
        """Initialize the ZakatMonitor with config-injected environment."""
        try:
            self._set_env_from_config()
            self.monitor = ZakatMonitor()
            # Override relative history path with absolute path in the app data dir
            # so the file persists across launches regardless of working directory.
            self._DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.monitor.history_file = str(self._DATA_DIR / "zakat_history_encrypted.json")
            # Reload history from the correct location
            self.monitor.balance_history = self.monitor._load_balance_history()
        finally:
            self._restore_env()

    def run_analysis(self) -> AnalysisResult:
        if not self.monitor:
            self.initialize()
        try:
            self._set_env_from_config()
            # Pass year progress override from config to monitor
            override = self.config.get('year_progress_override')
            if override and override.get('enabled'):
                self.monitor.year_progress_override = override
            else:
                self.monitor.year_progress_override = None
            return self.monitor.run_analysis()
        finally:
            self._restore_env()

    def get_balance_history(self) -> list:
        if not self.monitor:
            self.initialize()
        return self.monitor.balance_history

    def record_zakat_payment(self, amount: float, hijri_date: str) -> bool:
        if not self.monitor:
            self.initialize()
        try:
            self._set_env_from_config()
            self.monitor.record_zakat_payment(amount, hijri_date)
            return True
        except Exception as e:
            print(f"Error recording zakat payment: {e}")
            return False
        finally:
            self._restore_env()

    def get_current_nisab(self) -> float:
        if not self.monitor:
            self.initialize()
        try:
            self._set_env_from_config()
            return self.monitor.get_current_nisab()
        finally:
            self._restore_env()
