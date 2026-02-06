"""
Tests for encrypted storage layer (config and history)
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from cryptography.fernet import Fernet
import base64

from app.storage.config import ConfigStorage
from app.storage.history import HistoryStorage


class TestConfigStorage:
    """Tests for ConfigStorage"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test data"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    @pytest.fixture
    def config_storage(self, temp_dir):
        """Create ConfigStorage instance with temp directory"""
        return ConfigStorage(data_dir=temp_dir)

    def test_save_and_load_config_roundtrip(self, config_storage):
        """Test that we can save and load config successfully"""
        test_config = {
            'email': {
                'username': 'test@example.com',
                'password': 'secret123'
            },
            'accounts': {
                'bam_account': '1234567890',
                'eur_account': '0987654321'
            }
        }
        master_password = 'my-strong-password-123'

        # Save config
        assert config_storage.save_config(test_config, master_password) is True

        # Load config
        loaded_config = config_storage.load_config(master_password)

        # Verify round-trip
        assert loaded_config == test_config

    def test_load_with_wrong_password(self, config_storage):
        """Test that loading with wrong password fails"""
        test_config = {'key': 'value'}
        correct_password = 'correct-password'
        wrong_password = 'wrong-password'

        # Save with correct password
        config_storage.save_config(test_config, correct_password)

        # Try to load with wrong password
        with pytest.raises(ValueError, match="Incorrect master password"):
            config_storage.load_config(wrong_password)

    def test_load_nonexistent_config(self, config_storage):
        """Test that loading non-existent config raises error"""
        with pytest.raises(FileNotFoundError):
            config_storage.load_config('any-password')

    def test_config_exists(self, config_storage):
        """Test config_exists method"""
        assert config_storage.config_exists() is False

        # Save a config
        config_storage.save_config({'test': 'data'}, 'password')

        assert config_storage.config_exists() is True

    def test_delete_config(self, config_storage):
        """Test config deletion"""
        # Save a config
        config_storage.save_config({'test': 'data'}, 'password')
        assert config_storage.config_exists() is True

        # Delete it
        assert config_storage.delete_config() is True
        assert config_storage.config_exists() is False

        # Delete non-existent
        assert config_storage.delete_config() is False

    def test_update_config(self, config_storage):
        """Test updating config fields"""
        initial_config = {
            'email': {
                'username': 'old@example.com',
                'password': 'oldpass'
            },
            'accounts': {
                'bam_account': '1111'
            }
        }
        password = 'test-password'

        # Save initial config
        config_storage.save_config(initial_config, password)

        # Update some fields
        updates = {
            'email': {
                'username': 'new@example.com'
            },
            'accounts': {
                'eur_account': '2222'
            }
        }

        updated_config = config_storage.update_config(password, updates)

        # Verify updates applied correctly
        assert updated_config['email']['username'] == 'new@example.com'
        assert updated_config['email']['password'] == 'oldpass'  # unchanged
        assert updated_config['accounts']['bam_account'] == '1111'  # unchanged
        assert updated_config['accounts']['eur_account'] == '2222'  # new field

    def test_empty_password_rejected(self, config_storage):
        """Test that empty password is rejected"""
        with pytest.raises(ValueError, match="Master password cannot be empty"):
            config_storage.save_config({'test': 'data'}, '')

        # Save a config first
        config_storage.save_config({'test': 'data'}, 'valid-password')

        with pytest.raises(ValueError, match="Master password cannot be empty"):
            config_storage.load_config('')

    def test_invalid_config_type_rejected(self, config_storage):
        """Test that non-dict config is rejected"""
        with pytest.raises(ValueError, match="Config must be a dictionary"):
            config_storage.save_config("not a dict", "password")

        with pytest.raises(ValueError, match="Config must be a dictionary"):
            config_storage.save_config(['not', 'a', 'dict'], "password")


class TestHistoryStorage:
    """Tests for HistoryStorage"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test data"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    @pytest.fixture
    def encryption_key(self):
        """Generate a Fernet encryption key for testing"""
        return Fernet.generate_key().decode('utf-8')

    @pytest.fixture
    def history_storage(self, temp_dir, encryption_key):
        """Create HistoryStorage instance with temp directory"""
        return HistoryStorage(encryption_key=encryption_key, data_dir=temp_dir)

    def test_save_and_load_history_roundtrip(self, history_storage):
        """Test that we can save and load history successfully"""
        test_history = [
            {
                'hijri_date': '01/01/1446',
                'gregorian_date': '2024-07-08',
                'balance_bam': 25000.0,
                'balance_eur': 1000.0,
                'nisab_threshold': 24624.0,
                'above_nisab': True
            },
            {
                'hijri_date': '01/02/1446',
                'gregorian_date': '2024-08-06',
                'balance_bam': 26000.0,
                'balance_eur': 1100.0,
                'nisab_threshold': 24624.0,
                'above_nisab': True
            }
        ]

        # Save history
        assert history_storage.save_history(test_history) is True

        # Load history
        loaded_history = history_storage.load_history()

        # Verify round-trip
        assert loaded_history == test_history

    def test_load_empty_history(self, history_storage):
        """Test that loading non-existent history returns empty list"""
        history = history_storage.load_history()
        assert history == []

    def test_append_entry(self, history_storage):
        """Test appending entries to history"""
        entry1 = {'date': '2024-01-01', 'balance': 25000}
        entry2 = {'date': '2024-02-01', 'balance': 26000}

        # Append first entry
        assert history_storage.append_entry(entry1) is True

        # Verify it was added
        history = history_storage.load_history()
        assert len(history) == 1
        assert history[0] == entry1

        # Append second entry
        assert history_storage.append_entry(entry2) is True

        # Verify both entries
        history = history_storage.load_history()
        assert len(history) == 2
        assert history[0] == entry1
        assert history[1] == entry2

    def test_get_recent_entries(self, history_storage):
        """Test getting recent N entries"""
        # Add 15 entries
        for i in range(15):
            history_storage.append_entry({'index': i, 'balance': 25000 + i * 100})

        # Get recent 12
        recent = history_storage.get_recent_entries(12)
        assert len(recent) == 12
        assert recent[0]['index'] == 3  # entries 3-14
        assert recent[-1]['index'] == 14

        # Get all when count > actual
        recent = history_storage.get_recent_entries(20)
        assert len(recent) == 15

    def test_clear_history(self, history_storage):
        """Test clearing history"""
        # Add some entries
        history_storage.append_entry({'balance': 25000})
        history_storage.append_entry({'balance': 26000})

        assert len(history_storage.load_history()) == 2

        # Clear history
        assert history_storage.clear_history() is True

        # Verify it's empty
        assert history_storage.load_history() == []

    def test_history_exists(self, history_storage):
        """Test history_exists method"""
        assert history_storage.history_exists() is False

        # Save some history
        history_storage.save_history([{'test': 'data'}])

        assert history_storage.history_exists() is True

    def test_delete_history(self, history_storage):
        """Test history deletion"""
        # Save history
        history_storage.save_history([{'test': 'data'}])
        assert history_storage.history_exists() is True

        # Delete it
        assert history_storage.delete_history() is True
        assert history_storage.history_exists() is False

        # Delete non-existent
        assert history_storage.delete_history() is False

    def test_get_entry_count(self, history_storage):
        """Test getting entry count"""
        assert history_storage.get_entry_count() == 0

        # Add entries
        for i in range(5):
            history_storage.append_entry({'index': i})

        assert history_storage.get_entry_count() == 5

    def test_filter_entries(self, history_storage):
        """Test filtering entries"""
        # Add mixed entries
        for i in range(10):
            history_storage.append_entry({
                'index': i,
                'balance': 25000 if i % 2 == 0 else 20000,
                'above_nisab': i % 2 == 0
            })

        # Filter for above nisab
        above_nisab = history_storage.filter_entries(
            lambda e: e.get('above_nisab', False)
        )

        assert len(above_nisab) == 5
        assert all(e['above_nisab'] for e in above_nisab)

    def test_invalid_encryption_key(self, temp_dir):
        """Test that invalid encryption key is rejected"""
        with pytest.raises(ValueError, match="Invalid encryption key"):
            HistoryStorage(encryption_key="not-a-valid-key", data_dir=temp_dir)

        with pytest.raises(ValueError, match="Encryption key cannot be empty"):
            HistoryStorage(encryption_key="", data_dir=temp_dir)

    def test_invalid_history_type_rejected(self, history_storage):
        """Test that non-list history is rejected"""
        with pytest.raises(ValueError, match="History must be a list"):
            history_storage.save_history("not a list")

        with pytest.raises(ValueError, match="History must be a list"):
            history_storage.save_history({'not': 'a list'})

    def test_invalid_entry_type_rejected(self, history_storage):
        """Test that non-dict entry is rejected"""
        with pytest.raises(ValueError, match="Entry must be a dictionary"):
            history_storage.append_entry("not a dict")

        with pytest.raises(ValueError, match="Entry must be a dictionary"):
            history_storage.append_entry(['not', 'a', 'dict'])
