"""
Encrypted balance history storage

Manages local encrypted history file in ~/Library/Application Support/Zekat/history.enc
Uses the same encryption key as the main config for consistency.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from cryptography.fernet import Fernet, InvalidToken
import base64


class HistoryStorage:
    """Local encrypted balance history storage"""

    def __init__(self, encryption_key: str, data_dir: Optional[Path] = None):
        """
        Initialize history storage.

        Args:
            encryption_key: Base64-encoded Fernet encryption key
            data_dir: Custom data directory. Defaults to ~/Library/Application Support/Zekat/

        Raises:
            ValueError: If encryption_key is invalid
        """
        if not encryption_key:
            raise ValueError("Encryption key cannot be empty")

        try:
            self.cipher = Fernet(encryption_key.encode('utf-8') if isinstance(encryption_key, str) else encryption_key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")

        if data_dir is None:
            self.data_dir = Path.home() / "Library" / "Application Support" / "Zekat"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "history.enc"

    def save_history(self, history: List[Dict[str, Any]]) -> bool:
        """
        Encrypt and save balance history.

        Args:
            history: List of balance history entries

        Returns:
            True if saved successfully

        Raises:
            ValueError: If history is invalid
        """
        if not isinstance(history, list):
            raise ValueError("History must be a list")

        # Serialize to JSON
        history_json = json.dumps(history, indent=2)

        # Encrypt
        encrypted_data = self.cipher.encrypt(history_json.encode('utf-8'))

        # Save
        with open(self.history_file, 'wb') as f:
            f.write(encrypted_data)

        # Set file permissions to user-only
        import os
        os.chmod(self.history_file, 0o600)

        return True

    def load_history(self) -> List[Dict[str, Any]]:
        """
        Load and decrypt balance history.

        Returns:
            List of balance history entries, or empty list if file doesn't exist

        Raises:
            ValueError: If file is corrupted or encryption key is wrong
        """
        if not self.history_file.exists():
            return []

        try:
            # Read encrypted data
            with open(self.history_file, 'rb') as f:
                encrypted_data = f.read()

            # Decrypt
            decrypted_data = self.cipher.decrypt(encrypted_data)
            history_json = decrypted_data.decode('utf-8')

            # Parse JSON
            history = json.loads(history_json)

            if not isinstance(history, list):
                raise ValueError("Corrupted history file: expected list")

            return history

        except InvalidToken:
            raise ValueError("Failed to decrypt history: wrong encryption key or corrupted file")
        except json.JSONDecodeError as e:
            raise ValueError(f"Corrupted history file: invalid JSON - {e}")

    def append_entry(self, entry: Dict[str, Any]) -> bool:
        """
        Append a new entry to history.

        Args:
            entry: Balance history entry to append

        Returns:
            True if appended successfully
        """
        if not isinstance(entry, dict):
            raise ValueError("Entry must be a dictionary")

        # Load existing history
        history = self.load_history()

        # Append new entry
        history.append(entry)

        # Save updated history
        return self.save_history(history)

    def get_recent_entries(self, count: int = 12) -> List[Dict[str, Any]]:
        """
        Get the most recent N history entries.

        Args:
            count: Number of recent entries to retrieve

        Returns:
            List of most recent entries (newest last)
        """
        history = self.load_history()
        return history[-count:] if len(history) > count else history

    def clear_history(self) -> bool:
        """
        Clear all history (saves empty list).

        Returns:
            True if cleared successfully
        """
        return self.save_history([])

    def history_exists(self) -> bool:
        """Check if history file exists"""
        return self.history_file.exists()

    def delete_history(self) -> bool:
        """
        Delete the history file.

        Returns:
            True if deleted, False if file didn't exist
        """
        if self.history_file.exists():
            self.history_file.unlink()
            return True
        return False

    def get_entry_count(self) -> int:
        """
        Get total number of history entries.

        Returns:
            Number of entries in history
        """
        history = self.load_history()
        return len(history)

    def filter_entries(self, filter_func) -> List[Dict[str, Any]]:
        """
        Filter history entries using a custom function.

        Args:
            filter_func: Function that takes an entry dict and returns bool

        Returns:
            List of entries that match the filter
        """
        history = self.load_history()
        return [entry for entry in history if filter_func(entry)]
