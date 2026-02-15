"""Tests for app.core.config module."""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.config import get_api_key, save_api_key, _plist_path, _read_plist, _write_plist


class TestGetApiKey:
    """Tests for get_api_key()."""

    def test_returns_env_var(self):
        """Environment variable is highest priority."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}), \
             patch("app.core.config.is_bundled", return_value=False):
            assert get_api_key() == "sk-test-key"

    def test_ignores_placeholder(self):
        """Placeholder value 'your-api-key-here' is treated as unset."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "your-api-key-here"}, clear=False), \
             patch("app.core.config.is_bundled", return_value=False), \
             patch("dotenv.load_dotenv"):
            # After dotenv, env still has placeholder
            result = get_api_key()
            assert result is None

    def test_dev_mode_loads_dotenv(self):
        """In dev mode, loads .env file."""
        mock_load = MagicMock()
        with patch.dict(os.environ, {}, clear=True), \
             patch("app.core.config.is_bundled", return_value=False), \
             patch("dotenv.load_dotenv", mock_load):
            get_api_key()
            mock_load.assert_called_once()

    def test_dev_mode_dotenv_key(self):
        """In dev mode, key from .env is returned."""
        def fake_load_dotenv():
            os.environ["ANTHROPIC_API_KEY"] = "sk-from-dotenv"

        with patch.dict(os.environ, {}, clear=True), \
             patch("app.core.config.is_bundled", return_value=False), \
             patch("dotenv.load_dotenv", side_effect=fake_load_dotenv):
            assert get_api_key() == "sk-from-dotenv"

    def test_bundled_mode_reads_plist(self):
        """In bundled mode, reads from preferences.plist."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("app.core.config.is_bundled", return_value=True), \
             patch("app.core.config._read_plist", return_value={"ANTHROPIC_API_KEY": "sk-plist"}):
            assert get_api_key() == "sk-plist"

    def test_bundled_mode_no_plist_key(self):
        """In bundled mode, returns None if plist has no key."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("app.core.config.is_bundled", return_value=True), \
             patch("app.core.config._read_plist", return_value={}):
            assert get_api_key() is None

    def test_env_takes_precedence_over_plist(self):
        """Env var is checked before plist."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env"}), \
             patch("app.core.config.is_bundled", return_value=True):
            assert get_api_key() == "sk-env"

    def test_returns_none_when_nothing_configured(self):
        """Returns None when no key is set anywhere."""
        with patch.dict(os.environ, {}, clear=True), \
             patch("app.core.config.is_bundled", return_value=False), \
             patch("dotenv.load_dotenv"):
            assert get_api_key() is None


class TestSaveApiKey:
    """Tests for save_api_key()."""

    def test_saves_to_plist_and_environ(self):
        """Persists key to plist and sets env var."""
        with patch("app.core.config._read_plist", return_value={}) as mock_read, \
             patch("app.core.config._write_plist") as mock_write, \
             patch.dict(os.environ, {}, clear=True):
            save_api_key("sk-new-key")
            mock_write.assert_called_once()
            written = mock_write.call_args[0][0]
            assert written["ANTHROPIC_API_KEY"] == "sk-new-key"
            assert os.environ["ANTHROPIC_API_KEY"] == "sk-new-key"

    def test_save_updates_existing_plist(self):
        """Existing plist data is preserved when saving."""
        with patch("app.core.config._read_plist", return_value={"other": "data"}), \
             patch("app.core.config._write_plist") as mock_write, \
             patch.dict(os.environ, {}, clear=True):
            save_api_key("sk-key")
            written = mock_write.call_args[0][0]
            assert written["other"] == "data"
            assert written["ANTHROPIC_API_KEY"] == "sk-key"


class TestPlistPath:
    """Tests for _plist_path()."""

    def test_returns_preferences_plist(self):
        with patch("app.core.config.get_data_dir", return_value=Path("/data")):
            assert _plist_path() == Path("/data/preferences.plist")
