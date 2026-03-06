"""Tests for app.core.config module."""

from pathlib import Path
from unittest.mock import patch

from app.core.config import (
    DEFAULT_AI_MODEL,
    _plist_path,
    _read_plist,
    _write_plist,
    get_ai_model,
    has_prompted_auto_update,
    save_ai_model,
    set_prompted_auto_update,
)


class TestGetAiModel:
    """Tests for get_ai_model()."""

    def test_returns_default_when_unset(self):
        """Returns DEFAULT_AI_MODEL when plist has no model key."""
        with patch("app.core.config._read_plist", return_value={}), patch("app.core.config._write_plist"):
            assert get_ai_model() == DEFAULT_AI_MODEL

    def test_returns_saved_model(self):
        """Returns the model saved in plist."""
        with patch("app.core.config._read_plist", return_value={"AI_MODEL": "claude-opus-4-6"}):
            assert get_ai_model() == "claude-opus-4-6"

    def test_returns_default_for_invalid_model(self):
        """Falls back to default if plist contains an invalid model ID."""
        with (
            patch("app.core.config._read_plist", return_value={"AI_MODEL": "invalid-model"}),
            patch("app.core.config._write_plist"),
        ):
            assert get_ai_model() == DEFAULT_AI_MODEL

    def test_saves_default_when_stale(self):
        """Persists default back to plist when stored model is invalid."""
        with (
            patch("app.core.config._read_plist", return_value={"AI_MODEL": "old-model"}),
            patch("app.core.config._write_plist") as mock_write,
        ):
            get_ai_model()
            mock_write.assert_called_once()
            written = mock_write.call_args[0][0]
            assert written["AI_MODEL"] == DEFAULT_AI_MODEL


class TestSaveAiModel:
    """Tests for save_ai_model()."""

    def test_saves_to_plist(self):
        """Persists model ID to plist."""
        with patch("app.core.config._read_plist", return_value={}), patch("app.core.config._write_plist") as mock_write:
            save_ai_model("claude-opus-4-6")
            mock_write.assert_called_once()
            written = mock_write.call_args[0][0]
            assert written["AI_MODEL"] == "claude-opus-4-6"

    def test_preserves_existing_plist_data(self):
        """Existing plist data is preserved when saving model."""
        with (
            patch("app.core.config._read_plist", return_value={"ANTHROPIC_API_KEY": "sk-key"}),
            patch("app.core.config._write_plist") as mock_write,
        ):
            save_ai_model("claude-haiku-4-5")
            written = mock_write.call_args[0][0]
            assert written["ANTHROPIC_API_KEY"] == "sk-key"
            assert written["AI_MODEL"] == "claude-haiku-4-5"


class TestHasPromptedAutoUpdate:
    """Tests for has_prompted_auto_update()."""

    def test_default_false(self):
        """Returns False when plist has no auto-update prompted flag."""
        with patch("app.core.config._read_plist", return_value={}):
            assert has_prompted_auto_update() is False

    def test_true_when_set(self):
        """Returns True when flag is set in plist."""
        with patch("app.core.config._read_plist", return_value={"AUTO_UPDATE_PROMPTED": True}):
            assert has_prompted_auto_update() is True


class TestSetPromptedAutoUpdate:
    """Tests for set_prompted_auto_update()."""

    def test_sets_flag(self):
        """Sets the auto-update prompted flag in plist."""
        with patch("app.core.config._read_plist", return_value={}), patch("app.core.config._write_plist") as mock_write:
            set_prompted_auto_update()
            mock_write.assert_called_once()
            written = mock_write.call_args[0][0]
            assert written["AUTO_UPDATE_PROMPTED"] is True

    def test_preserves_existing_plist_data(self):
        """Existing plist data is preserved when setting flag."""
        with (
            patch("app.core.config._read_plist", return_value={"ANTHROPIC_API_KEY": "sk-key"}),
            patch("app.core.config._write_plist") as mock_write,
        ):
            set_prompted_auto_update()
            written = mock_write.call_args[0][0]
            assert written["ANTHROPIC_API_KEY"] == "sk-key"
            assert written["AUTO_UPDATE_PROMPTED"] is True


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
