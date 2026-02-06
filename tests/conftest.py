import os
import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set required environment variables for ZakatMonitor instantiation."""
    monkeypatch.setenv('BAM_ACCOUNT', '1234567890')
    monkeypatch.setenv('EUR_ACCOUNT', '0987654321')
    monkeypatch.setenv('ZAKAT_ENCRYPTION_KEY', 'dGVzdGtleV9mb3JfdGVzdGluZ19vbmx5XzEyMzQ1Njc=')
    monkeypatch.setenv('EMAIL_USERNAME', 'test@example.com')
    monkeypatch.setenv('EMAIL_PASSWORD', 'testpassword')
    monkeypatch.setenv('SENDER_EMAIL', 'test@example.com')
    monkeypatch.setenv('RECIPIENT_EMAIL', 'recipient@example.com')


@pytest.fixture
def monitor(mock_env, tmp_path, monkeypatch):
    """Create a ZakatMonitor instance with a temporary history file."""
    from cryptography.fernet import Fernet
    # Generate a valid Fernet key for tests
    key = Fernet.generate_key()
    monkeypatch.setenv('ZAKAT_ENCRYPTION_KEY', key.decode())
    monkeypatch.chdir(tmp_path)

    from zakat_monitor import ZakatMonitor
    return ZakatMonitor()


@pytest.fixture
def monitor_with_company(mock_env, tmp_path, monkeypatch):
    """Create a ZakatMonitor instance with company email source configured."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    monkeypatch.setenv('ZAKAT_ENCRYPTION_KEY', key.decode())
    monkeypatch.setenv('COMPANY_EMAIL_USERNAME', 'company@example.com')
    monkeypatch.setenv('COMPANY_EMAIL_PASSWORD', 'companypass')
    monkeypatch.setenv('COMPANY_BAM_ACCOUNT', '1111111111')
    monkeypatch.setenv('COMPANY_EUR_ACCOUNT', '2222222222')
    monkeypatch.chdir(tmp_path)
    from zakat_monitor import ZakatMonitor
    return ZakatMonitor()
