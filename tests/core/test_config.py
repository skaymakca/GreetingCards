"""Tests for app.core.config module."""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.config import (
    get_api_key, save_api_key, _plist_path, _read_plist, _write_plist,
    get_ai_model, save_ai_model, DEFAULT_AI_MODEL,
)


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


class TestGetAiModel:
    """Tests for get_ai_model()."""

    def test_returns_default_when_unset(self):
        """Returns DEFAULT_AI_MODEL when plist has no model key."""
        with patch("app.core.config._read_plist", return_value={}), \
             patch("app.core.config._write_plist"):
            assert get_ai_model() == DEFAULT_AI_MODEL

    def test_returns_saved_model(self):
        """Returns the model saved in plist."""
        with patch("app.core.config._read_plist", return_value={"AI_MODEL": "claude-opus-4-6"}):
            assert get_ai_model() == "claude-opus-4-6"

    def test_returns_default_for_invalid_model(self):
        """Falls back to default if plist contains an invalid model ID."""
        with patch("app.core.config._read_plist", return_value={"AI_MODEL": "invalid-model"}), \
             patch("app.core.config._write_plist"):
            assert get_ai_model() == DEFAULT_AI_MODEL

    def test_saves_default_when_stale(self):
        """Persists default back to plist when stored model is invalid."""
        with patch("app.core.config._read_plist", return_value={"AI_MODEL": "old-model"}), \
             patch("app.core.config._write_plist") as mock_write:
            get_ai_model()
            mock_write.assert_called_once()
            written = mock_write.call_args[0][0]
            assert written["AI_MODEL"] == DEFAULT_AI_MODEL


class TestSaveAiModel:
    """Tests for save_ai_model()."""

    def test_saves_to_plist(self):
        """Persists model ID to plist."""
        with patch("app.core.config._read_plist", return_value={}), \
             patch("app.core.config._write_plist") as mock_write:
            save_ai_model("claude-opus-4-6")
            mock_write.assert_called_once()
            written = mock_write.call_args[0][0]
            assert written["AI_MODEL"] == "claude-opus-4-6"

    def test_preserves_existing_plist_data(self):
        """Existing plist data is preserved when saving model."""
        with patch("app.core.config._read_plist", return_value={"ANTHROPIC_API_KEY": "sk-key"}), \
             patch("app.core.config._write_plist") as mock_write:
            save_ai_model("claude-haiku-4-5-20251001")
            written = mock_write.call_args[0][0]
            assert written["ANTHROPIC_API_KEY"] == "sk-key"
            assert written["AI_MODEL"] == "claude-haiku-4-5-20251001"


class TestPlistPath:
    """Tests for _plist_path()."""

    def test_returns_preferences_plist(self):
        with patch("app.core.config.get_data_dir", return_value=Path("/data")):
            assert _plist_path() == Path("/data/preferences.plist")


class TestReadPlist:
    """Tests for _read_plist()."""

    def test_reads_existing_plist(self, tmp_path):
        """Reads data from an existing plist file."""
        import plistlib
        plist_file = tmp_path / "preferences.plist"
        with open(plist_file, "wb") as f:
            plistlib.dump({"key": "value"}, f)
        with patch("app.core.config._plist_path", return_value=plist_file):
            result = _read_plist()
        assert result == {"key": "value"}

    def test_returns_empty_dict_when_missing(self, tmp_path):
        """Returns empty dict when plist file doesn't exist."""
        plist_file = tmp_path / "nonexistent.plist"
        with patch("app.core.config._plist_path", return_value=plist_file):
            result = _read_plist()
        assert result == {}


class TestWritePlist:
    """Tests for _write_plist()."""

    def test_writes_plist_file(self, tmp_path):
        """Writes data to a plist file."""
        import plistlib
        plist_file = tmp_path / "preferences.plist"
        with patch("app.core.config._plist_path", return_value=plist_file):
            _write_plist({"ANTHROPIC_API_KEY": "sk-test"})
        with open(plist_file, "rb") as f:
            data = plistlib.load(f)
        assert data == {"ANTHROPIC_API_KEY": "sk-test"}

    def test_overwrites_existing_plist(self, tmp_path):
        """Overwrites existing plist file."""
        import plistlib
        plist_file = tmp_path / "preferences.plist"
        with open(plist_file, "wb") as f:
            plistlib.dump({"old": "data"}, f)
        with patch("app.core.config._plist_path", return_value=plist_file):
            _write_plist({"new": "data"})
        with open(plist_file, "rb") as f:
            data = plistlib.load(f)
        assert data == {"new": "data"}
