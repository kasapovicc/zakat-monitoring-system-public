"""
Encrypted configuration storage using Argon2id + Fernet

Master password → Argon2id KDF → Fernet encryption key → Encrypt config
Config stored in ~/Library/Application Support/Zekat/config.enc
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from argon2 import PasswordHasher
from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet, InvalidToken
import base64


class ConfigStorage:
    """Secure configuration storage with master password encryption"""

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize config storage.

        Args:
            data_dir: Custom data directory. Defaults to ~/Library/Application Support/Zekat/
        """
        if data_dir is None:
            self.data_dir = Path.home() / "Library" / "Application Support" / "Zekat"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "config.enc"

        # Argon2id parameters (OWASP recommended)
        self.argon2_time_cost = 2
        self.argon2_memory_cost = 19456  # 19 MiB
        self.argon2_parallelism = 1
        self.argon2_hash_len = 32  # 256 bits for Fernet key

    def _derive_key(self, master_password: str, salt: bytes) -> bytes:
        """
        Derive a Fernet key from master password using Argon2id.

        Args:
            master_password: User's master password
            salt: Salt for key derivation

        Returns:
            32-byte Fernet key
        """
        raw_hash = hash_secret_raw(
            secret=master_password.encode('utf-8'),
            salt=salt,
            time_cost=self.argon2_time_cost,
            memory_cost=self.argon2_memory_cost,
            parallelism=self.argon2_parallelism,
            hash_len=self.argon2_hash_len,
            type=Type.ID  # Argon2id
        )
        # Fernet expects URL-safe base64-encoded 32-byte key
        return base64.urlsafe_b64encode(raw_hash)

    def save_config(self, config: Dict[str, Any], master_password: str) -> bool:
        """
        Encrypt and save configuration.

        Args:
            config: Configuration dictionary to save
            master_password: Master password for encryption

        Returns:
            True if saved successfully

        Raises:
            ValueError: If config is invalid or password is empty
        """
        if not master_password:
            raise ValueError("Master password cannot be empty")

        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")

        # Generate random salt
        salt = os.urandom(16)

        # Derive encryption key
        fernet_key = self._derive_key(master_password, salt)
        cipher = Fernet(fernet_key)

        # Serialize config to JSON
        config_json = json.dumps(config, indent=2)

        # Encrypt
        encrypted_data = cipher.encrypt(config_json.encode('utf-8'))

        # Save salt + encrypted data
        # Format: 16 bytes salt + encrypted payload
        with open(self.config_file, 'wb') as f:
            f.write(salt)
            f.write(encrypted_data)

        # Set file permissions to user-only
        os.chmod(self.config_file, 0o600)

        return True

    def load_config(self, master_password: str) -> Dict[str, Any]:
        """
        Load and decrypt configuration.

        Args:
            master_password: Master password for decryption

        Returns:
            Decrypted configuration dictionary

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If password is wrong or file is corrupted
        """
        if not master_password:
            raise ValueError("Master password cannot be empty")

        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        # Read salt + encrypted data
        with open(self.config_file, 'rb') as f:
            salt = f.read(16)
            encrypted_data = f.read()

        if len(salt) != 16:
            raise ValueError("Corrupted config file: invalid salt")

        # Derive decryption key
        fernet_key = self._derive_key(master_password, salt)
        cipher = Fernet(fernet_key)

        try:
            # Decrypt
            decrypted_data = cipher.decrypt(encrypted_data)
            config_json = decrypted_data.decode('utf-8')

            # Parse JSON
            config = json.loads(config_json)

            return config

        except InvalidToken:
            raise ValueError("Incorrect master password or corrupted config file")
        except json.JSONDecodeError as e:
            raise ValueError(f"Corrupted config file: invalid JSON - {e}")

    def config_exists(self) -> bool:
        """Check if config file exists"""
        return self.config_file.exists()

    def delete_config(self) -> bool:
        """
        Delete the config file.

        Returns:
            True if deleted, False if file didn't exist
        """
        if self.config_file.exists():
            self.config_file.unlink()
            return True
        return False

    def update_config(self, master_password: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update specific config fields.

        Args:
            master_password: Master password for decryption/encryption
            updates: Dictionary of fields to update

        Returns:
            Updated configuration dictionary

        Raises:
            FileNotFoundError: If config doesn't exist
            ValueError: If password is wrong
        """
        # Load existing config
        config = self.load_config(master_password)

        # Deep merge updates
        def deep_update(d: dict, u: dict) -> dict:
            for k, v in u.items():
                if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                    d[k] = deep_update(d[k], v)
                else:
                    d[k] = v
            return d

        config = deep_update(config, updates)

        # Save updated config
        self.save_config(config, master_password)

        return config
