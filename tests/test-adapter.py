"""Tests for ZakatMonitorAdapter with multi-source config"""
import pytest
import os
from unittest.mock import patch, MagicMock
from app.adapter import ZakatMonitorAdapter


class TestAdapterInitialization:
    """Tests for adapter initialization"""

    def test_init_with_config(self):
        """Should initialize with provided config"""
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'test@example.com',
                    'password': 'pass',
                    'account_pairs': [{'bam_account': '123', 'eur_account': '456'}]
                }
            ],
            'encryption_key': 'test-key',
        }
        adapter = ZakatMonitorAdapter(config)
        assert adapter.config == config
        assert adapter.monitor is None

    def test_init_without_config(self):
        """Should initialize with empty config"""
        adapter = ZakatMonitorAdapter()
        assert adapter.config == {}
        assert adapter.monitor is None


class TestMultiSourceConfigDetection:
    """Tests for detecting old vs new config format"""

    def test_detects_new_format(self):
        """Config with email_sources key is new format"""
        config = {'email_sources': []}
        adapter = ZakatMonitorAdapter(config)
        assert adapter._is_new_config_format() is True

    def test_detects_old_format(self):
        """Config with email key (not email_sources) is old format"""
        config = {'email': {'username': 'test@gmail.com'}}
        adapter = ZakatMonitorAdapter(config)
        assert adapter._is_new_config_format() is False

    def test_empty_config_is_old_format(self):
        """Empty config treated as old format"""
        adapter = ZakatMonitorAdapter({})
        assert adapter._is_new_config_format() is False


class TestMultiSourceEnvInjection:
    """Tests for environment injection with multiple email sources"""

    def test_first_source_sets_primary_env(self):
        """First email source should map to primary env vars"""
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'first@gmail.com',
                    'password': 'pass1',
                    'imap_server': 'imap.gmail.com',
                    'imap_port': 993,
                    'account_pairs': [
                        {'bam_account': '111', 'eur_account': '222'}
                    ]
                }
            ],
            'report_delivery': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'sender@gmail.com',
                'password': 'smtppass',
                'sender_email': 'sender@gmail.com',
                'recipient_email': 'recipient@gmail.com'
            },
            'encryption_key': 'test-key',
            'nisab_fallback_bam': 24624.0,
        }
        adapter = ZakatMonitorAdapter(config)
        adapter._set_env_from_config()

        assert os.environ.get('EMAIL_USERNAME') == 'first@gmail.com'
        assert os.environ.get('BAM_ACCOUNT') == '111'
        assert os.environ.get('EUR_ACCOUNT') == '222'
        assert os.environ.get('SENDER_EMAIL') == 'sender@gmail.com'
        assert os.environ.get('RECIPIENT_EMAIL') == 'recipient@gmail.com'

        adapter._restore_env()

    def test_second_source_sets_company_env(self):
        """Second email source should map to company env vars"""
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'first@gmail.com',
                    'password': 'pass1',
                    'imap_server': 'imap.gmail.com',
                    'imap_port': 993,
                    'account_pairs': [
                        {'bam_account': '111', 'eur_account': '222'}
                    ]
                },
                {
                    'id': 'src-2',
                    'email': 'second@gmail.com',
                    'password': 'pass2',
                    'imap_server': 'imap.gmail.com',
                    'imap_port': 993,
                    'account_pairs': [
                        {'bam_account': '333', 'eur_account': '444'}
                    ]
                }
            ],
            'report_delivery': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'sender@gmail.com',
                'password': 'smtppass',
                'sender_email': 'sender@gmail.com',
                'recipient_email': 'recipient@gmail.com'
            },
            'encryption_key': 'test-key',
            'nisab_fallback_bam': 24624.0,
        }
        adapter = ZakatMonitorAdapter(config)
        adapter._set_env_from_config()

        # Primary
        assert os.environ.get('EMAIL_USERNAME') == 'first@gmail.com'
        assert os.environ.get('BAM_ACCOUNT') == '111'
        # Company
        assert os.environ.get('COMPANY_EMAIL_USERNAME') == 'second@gmail.com'
        assert os.environ.get('COMPANY_BAM_ACCOUNT') == '333'

        adapter._restore_env()

    def test_report_delivery_maps_to_smtp_env(self):
        """Report delivery config should set SMTP/sender/recipient env vars"""
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'first@gmail.com',
                    'password': 'pass1',
                    'imap_server': 'imap.gmail.com',
                    'imap_port': 993,
                    'account_pairs': [
                        {'bam_account': '111', 'eur_account': '222'}
                    ]
                }
            ],
            'report_delivery': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'reports@gmail.com',
                'password': 'reportpass',
                'sender_email': 'reports@gmail.com',
                'recipient_email': 'boss@gmail.com'
            },
            'encryption_key': 'test-key',
        }
        adapter = ZakatMonitorAdapter(config)
        adapter._set_env_from_config()

        assert os.environ.get('SMTP_SERVER') == 'smtp.gmail.com'
        assert os.environ.get('SMTP_PORT') == '587'
        assert os.environ.get('SENDER_EMAIL') == 'reports@gmail.com'
        assert os.environ.get('RECIPIENT_EMAIL') == 'boss@gmail.com'

        adapter._restore_env()


class TestOldFormatEnvInjection:
    """Tests for backward-compatible old config format"""

    def test_old_format_sets_env(self):
        """Old format config should still set env vars correctly"""
        config = {
            'email': {
                'username': 'test@example.com',
                'password': 'testpass',
                'imap_server': 'imap.gmail.com',
                'imap_port': 993,
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender_email': 'test@example.com',
                'recipient_email': 'recipient@example.com',
            },
            'accounts': {
                'bam_account': '123456',
                'eur_account': '789012'
            },
            'encryption_key': 'test-encryption-key',
            'nisab_fallback_bam': 24624.0
        }
        adapter = ZakatMonitorAdapter(config)
        adapter._set_env_from_config()

        assert os.environ.get('EMAIL_USERNAME') == 'test@example.com'
        assert os.environ.get('EMAIL_PASSWORD') == 'testpass'
        assert os.environ.get('BAM_ACCOUNT') == '123456'
        assert os.environ.get('EUR_ACCOUNT') == '789012'
        assert os.environ.get('ZAKAT_ENCRYPTION_KEY') == 'test-encryption-key'

        adapter._restore_env()

    def test_env_restore(self):
        """Should restore environment to previous state after old format"""
        original_env = os.environ.copy()

        config = {
            'email': {'username': 'x@x.com', 'password': 'p'},
            'accounts': {'bam_account': '1', 'eur_account': '2'},
            'encryption_key': 'k',
        }
        adapter = ZakatMonitorAdapter(config)
        adapter._set_env_from_config()
        adapter._restore_env()

        for key in ['EMAIL_USERNAME', 'EMAIL_PASSWORD', 'BAM_ACCOUNT',
                    'EUR_ACCOUNT', 'ZAKAT_ENCRYPTION_KEY']:
            if key in original_env:
                assert os.environ.get(key) == original_env[key]
            else:
                assert key not in os.environ
