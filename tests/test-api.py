"""Tests for API endpoints"""
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from run_app import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_returns_200(self, client):
        """Health endpoint should return 200 with status"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "zekat-monitor"

    def test_health_has_version(self, client):
        """Health endpoint should include version"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "0.1.0"


class TestNisabEndpoint:
    """Tests for /api/nisab endpoint"""

    def test_nisab_returns_fallback(self, client):
        """Nisab endpoint should return fallback value"""
        response = client.get("/api/nisab")
        assert response.status_code == 200
        data = response.json()
        assert "nisab_bam" in data
        assert data["nisab_bam"] == 24624.0
        assert data["source"] in ["web", "fallback"]


class TestStatusEndpoint:
    """Tests for /api/status endpoint"""

    def test_status_returns_200(self, client):
        """Status endpoint should return 200"""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "initialized" in data


class TestSetupEndpoint:
    """Tests for POST /api/setup with multi-source config"""

    @pytest.fixture(autouse=True)
    def setup_temp_dir(self):
        """Use temp dir for config storage"""
        self.temp_dir = Path(tempfile.mkdtemp())
        from app.storage.config import ConfigStorage
        patcher = patch(
            'app.api.routes.get_config_storage',
            return_value=ConfigStorage(data_dir=self.temp_dir)
        )
        self.mock_storage = patcher.start()
        yield
        patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_setup_with_single_source(self, client):
        """Setup with one email source should succeed"""
        payload = {
            "master_password": "strongpass123",
            "email_sources": [
                {
                    "email": "test@gmail.com",
                    "password": "apppass",
                    "account_pairs": [
                        {"bam_account": "111", "eur_account": "222"}
                    ]
                }
            ],
            "report_delivery": {
                "username": "sender@gmail.com",
                "password": "apppass",
                "sender_email": "sender@gmail.com",
                "recipient_email": "recipient@gmail.com"
            },
            "encryption_key": "dGVzdGtleQ=="
        }
        response = client.post("/api/setup", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_setup_with_multiple_sources(self, client):
        """Setup with multiple email sources should succeed"""
        payload = {
            "master_password": "strongpass123",
            "email_sources": [
                {
                    "email": "personal@gmail.com",
                    "password": "pass1",
                    "account_pairs": [
                        {"bam_account": "111", "eur_account": "222"}
                    ]
                },
                {
                    "email": "business@gmail.com",
                    "password": "pass2",
                    "account_pairs": [
                        {"bam_account": "333", "eur_account": "444"},
                        {"bam_account": "555", "eur_account": "666"}
                    ]
                }
            ],
            "report_delivery": {
                "username": "sender@gmail.com",
                "password": "apppass",
                "sender_email": "sender@gmail.com",
                "recipient_email": "recipient@gmail.com"
            },
            "encryption_key": "dGVzdGtleQ=="
        }
        response = client.post("/api/setup", json=payload)
        assert response.status_code == 200

    def test_setup_with_year_progress_override(self, client):
        """Setup with year progress override should store it"""
        payload = {
            "master_password": "strongpass123",
            "email_sources": [
                {
                    "email": "test@gmail.com",
                    "password": "apppass",
                    "account_pairs": [
                        {"bam_account": "111", "eur_account": "222"}
                    ]
                }
            ],
            "report_delivery": {
                "username": "sender@gmail.com",
                "password": "apppass",
                "sender_email": "sender@gmail.com",
                "recipient_email": "recipient@gmail.com"
            },
            "encryption_key": "dGVzdGtleQ==",
            "year_progress_override": {
                "enabled": True,
                "months_above_nisab": 8,
                "as_of_hijri_date": "15/06/1446"
            }
        }
        response = client.post("/api/setup", json=payload)
        assert response.status_code == 200

    def test_setup_empty_sources_rejected(self, client):
        """Setup with no email sources should fail validation"""
        payload = {
            "master_password": "strongpass123",
            "email_sources": [],
            "report_delivery": {
                "username": "sender@gmail.com",
                "password": "apppass",
                "sender_email": "sender@gmail.com",
                "recipient_email": "recipient@gmail.com"
            },
            "encryption_key": "dGVzdGtleQ=="
        }
        response = client.post("/api/setup", json=payload)
        assert response.status_code == 422


class TestGetSettingsEndpoint:
    """Tests for GET /api/settings/full masked view"""

    @pytest.fixture(autouse=True)
    def setup_config(self):
        """Create temp dir and seed config"""
        self.temp_dir = Path(tempfile.mkdtemp())
        from app.storage.config import ConfigStorage
        storage = ConfigStorage(data_dir=self.temp_dir)
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'personal@gmail.com',
                    'password': 'secret123',
                    'imap_server': 'imap.gmail.com',
                    'imap_port': 993,
                    'account_pairs': [
                        {'bam_account': '1234567890', 'eur_account': '0987654321'}
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
            'encryption_key': 'dGVzdGtleQ==',
            'additional_assets': 5000.0,
            'nisab_fallback_bam': 24624.0,
            'year_progress_override': {
                'enabled': True,
                'months_above_nisab': 8,
                'as_of_hijri_date': '15/06/1446'
            }
        }
        storage.save_config(config, 'testpassword')
        patcher = patch(
            'app.api.routes.get_config_storage',
            return_value=ConfigStorage(data_dir=self.temp_dir)
        )
        patcher.start()
        yield
        patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_get_settings_returns_masked_emails(self, client):
        """Email addresses should be masked"""
        response = client.get("/api/settings/full?master_password=testpassword")
        assert response.status_code == 200
        resp = response.json()
        assert resp["success"] is True
        data = resp["data"]
        source = data["email_sources"][0]
        assert "***" in source["email"]
        assert source["password"] == "********"

    def test_get_settings_returns_masked_accounts(self, client):
        """Account numbers should be masked"""
        response = client.get("/api/settings/full?master_password=testpassword")
        data = response.json()["data"]
        pair = data["email_sources"][0]["account_pairs"][0]
        assert pair["bam_account"].startswith("****")
        assert pair["eur_account"].startswith("****")

    def test_get_settings_returns_report_delivery(self, client):
        """Report delivery should be present and masked"""
        response = client.get("/api/settings/full?master_password=testpassword")
        data = response.json()["data"]
        assert "report_delivery" in data
        assert data["report_delivery"]["password"] == "********"

    def test_get_settings_returns_year_progress(self, client):
        """Year progress override should be visible (not sensitive)"""
        response = client.get("/api/settings/full?master_password=testpassword")
        data = response.json()["data"]
        assert data["year_progress_override"]["enabled"] is True
        assert data["year_progress_override"]["months_above_nisab"] == 8

    def test_get_settings_returns_additional_settings(self, client):
        """Additional assets and nisab should be visible"""
        response = client.get("/api/settings/full?master_password=testpassword")
        data = response.json()["data"]
        assert data["additional_assets"] == 5000.0
        assert data["nisab_fallback_bam"] == 24624.0


class TestEmailSourceCRUD:
    """Tests for email source add/delete endpoints"""

    @pytest.fixture(autouse=True)
    def setup_config(self):
        """Seed config with one email source"""
        self.temp_dir = Path(tempfile.mkdtemp())
        from app.storage.config import ConfigStorage
        storage = ConfigStorage(data_dir=self.temp_dir)
        self.password = 'testpassword'
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
            'encryption_key': 'dGVzdGtleQ==',
            'additional_assets': 0.0,
            'nisab_fallback_bam': 24624.0,
        }
        storage.save_config(config, self.password)
        patcher = patch(
            'app.api.routes.get_config_storage',
            return_value=ConfigStorage(data_dir=self.temp_dir)
        )
        patcher.start()
        yield
        patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_add_email_source(self, client):
        """Should add a new email source"""
        payload = {
            "master_password": self.password,
            "email_source": {
                "email": "second@gmail.com",
                "password": "pass2",
                "account_pairs": [
                    {"bam_account": "333", "eur_account": "444"}
                ]
            }
        }
        response = client.post("/api/settings/email-sources", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_id"] is not None

    def test_delete_email_source(self, client):
        """Should delete an email source"""
        # First add a second source
        add_payload = {
            "master_password": self.password,
            "email_source": {
                "email": "second@gmail.com",
                "password": "pass2",
                "account_pairs": [
                    {"bam_account": "333", "eur_account": "444"}
                ]
            }
        }
        add_resp = client.post("/api/settings/email-sources", json=add_payload)
        source_id = add_resp.json()["source_id"]

        # Now delete it
        response = client.request(
            "DELETE",
            f"/api/settings/email-sources/{source_id}",
            json={"master_password": self.password}
        )
        assert response.status_code == 200

    def test_delete_last_source_rejected(self, client):
        """Should reject deletion of the last email source"""
        response = client.request(
            "DELETE",
            "/api/settings/email-sources/src-1",
            json={"master_password": self.password}
        )
        assert response.status_code == 400

    def test_delete_nonexistent_source(self, client):
        """Should return 404 for nonexistent source"""
        response = client.request(
            "DELETE",
            "/api/settings/email-sources/nonexistent",
            json={"master_password": self.password}
        )
        assert response.status_code == 404


class TestYearProgressEndpoint:
    """Tests for PUT /api/settings/year-progress"""

    @pytest.fixture(autouse=True)
    def setup_config(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        from app.storage.config import ConfigStorage
        storage = ConfigStorage(data_dir=self.temp_dir)
        self.password = 'testpassword'
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'test@gmail.com',
                    'password': 'pass',
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
            'encryption_key': 'dGVzdGtleQ==',
            'additional_assets': 0.0,
            'nisab_fallback_bam': 24624.0,
        }
        storage.save_config(config, self.password)
        patcher = patch(
            'app.api.routes.get_config_storage',
            return_value=ConfigStorage(data_dir=self.temp_dir)
        )
        patcher.start()
        yield
        patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_set_year_progress(self, client):
        """Should set year progress override"""
        payload = {
            "master_password": self.password,
            "enabled": True,
            "months_above_nisab": 8,
            "as_of_hijri_date": "15/06/1446"
        }
        response = client.put("/api/settings/year-progress", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_disable_year_progress(self, client):
        """Should disable year progress override"""
        payload = {
            "master_password": self.password,
            "enabled": False
        }
        response = client.put("/api/settings/year-progress", json=payload)
        assert response.status_code == 200

    def test_invalid_months_rejected(self, client):
        """Months > 11 should be rejected"""
        payload = {
            "master_password": self.password,
            "enabled": True,
            "months_above_nisab": 15,
            "as_of_hijri_date": "15/06/1446"
        }
        response = client.put("/api/settings/year-progress", json=payload)
        assert response.status_code == 422


class TestRestartSetupEndpoint:
    """Tests for POST /api/settings/restart-setup"""

    @pytest.fixture(autouse=True)
    def setup_config(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        from app.storage.config import ConfigStorage
        storage = ConfigStorage(data_dir=self.temp_dir)
        self.password = 'testpassword'
        self.config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'test@gmail.com',
                    'password': 'pass',
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
            'encryption_key': 'dGVzdGtleQ==',
            'additional_assets': 0.0,
            'nisab_fallback_bam': 24624.0,
        }
        storage.save_config(self.config, self.password)
        patcher = patch(
            'app.api.routes.get_config_storage',
            return_value=ConfigStorage(data_dir=self.temp_dir)
        )
        patcher.start()
        yield
        patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_restart_setup_returns_full_config(self, client):
        """Should return decrypted config for pre-filling wizard"""
        payload = {"master_password": self.password}
        response = client.post("/api/settings/restart-setup", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["config"]["email_sources"][0]["email"] == "test@gmail.com"

    def test_restart_setup_wrong_password(self, client):
        """Should reject wrong password"""
        payload = {"master_password": "wrongpassword"}
        response = client.post("/api/settings/restart-setup", json=payload)
        assert response.status_code == 401

    def test_restart_setup_no_config(self, client):
        """Should 404 if no config exists"""
        from app.storage.config import ConfigStorage
        ConfigStorage(data_dir=self.temp_dir).delete_config()

        payload = {"master_password": self.password}
        response = client.post("/api/settings/restart-setup", json=payload)
        assert response.status_code == 404


class TestUpdateSettingsEndpoint:
    """Tests for PUT /api/settings with new multi-source schema"""

    @pytest.fixture(autouse=True)
    def setup_config(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        from app.storage.config import ConfigStorage
        storage = ConfigStorage(data_dir=self.temp_dir)
        self.password = 'testpassword'
        config = {
            'email_sources': [
                {
                    'id': 'src-1',
                    'email': 'old@gmail.com',
                    'password': 'oldpass',
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
            'encryption_key': 'dGVzdGtleQ==',
            'additional_assets': 0.0,
            'nisab_fallback_bam': 24624.0,
        }
        storage.save_config(config, self.password)
        self._storage = ConfigStorage(data_dir=self.temp_dir)
        patcher = patch(
            'app.api.routes.get_config_storage',
            return_value=self._storage
        )
        patcher.start()
        yield
        patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_update_email_sources(self, client):
        """Should replace email sources"""
        payload = {
            "master_password": self.password,
            "email_sources": [
                {
                    "email": "new@gmail.com",
                    "password": "newpass",
                    "account_pairs": [
                        {"bam_account": "999", "eur_account": "888"}
                    ]
                }
            ]
        }
        response = client.put("/api/settings", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify stored config was updated
        config = self._storage.load_config(self.password)
        assert config['email_sources'][0]['email'] == 'new@gmail.com'

    def test_update_report_delivery(self, client):
        """Should update report delivery"""
        payload = {
            "master_password": self.password,
            "report_delivery": {
                "username": "new-sender@gmail.com",
                "password": "newsmtp",
                "sender_email": "new-sender@gmail.com",
                "recipient_email": "new-recipient@gmail.com"
            }
        }
        response = client.put("/api/settings", json=payload)
        assert response.status_code == 200

        config = self._storage.load_config(self.password)
        assert config['report_delivery']['recipient_email'] == 'new-recipient@gmail.com'

    def test_update_additional_assets(self, client):
        """Should update additional assets"""
        payload = {
            "master_password": self.password,
            "additional_assets": 10000.0
        }
        response = client.put("/api/settings", json=payload)
        assert response.status_code == 200

        config = self._storage.load_config(self.password)
        assert config['additional_assets'] == 10000.0

    def test_update_preserves_unchanged_fields(self, client):
        """Updating one field should not overwrite others"""
        payload = {
            "master_password": self.password,
            "nisab_fallback_bam": 30000.0
        }
        response = client.put("/api/settings", json=payload)
        assert response.status_code == 200

        config = self._storage.load_config(self.password)
        assert config['nisab_fallback_bam'] == 30000.0
        # Other fields preserved
        assert config['email_sources'][0]['email'] == 'old@gmail.com'
        assert config['additional_assets'] == 0.0

    def test_update_wrong_password(self, client):
        """Should reject wrong password"""
        payload = {
            "master_password": "wrongpassword",
            "additional_assets": 5000.0
        }
        response = client.put("/api/settings", json=payload)
        assert response.status_code == 401


class TestSetupPageView:
    def test_setup_page_accessible(self, client):
        """Setup page should be accessible"""
        response = client.get("/setup")
        assert response.status_code == 200

    def test_setup_page_restart_mode(self, client):
        """Setup page should accept restart query param"""
        response = client.get("/setup?restart=true")
        assert response.status_code == 200
