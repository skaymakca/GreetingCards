"""Tests for app.core.paths module."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.core.paths import is_bundled, get_data_dir, get_db_path


class TestIsBundled:
    """Tests for is_bundled()."""

    def test_not_bundled_no_meipass(self):
        """Returns False when _MEIPASS is absent."""
        if hasattr(sys, "_MEIPASS"):
            pytest.skip("_MEIPASS unexpectedly present")
        assert is_bundled() is False

    def test_bundled_with_meipass(self):
        """Returns True when _MEIPASS is set."""
        with patch.object(sys, "_MEIPASS", "/tmp/bundle", create=True):
            assert is_bundled() is True

    def test_not_bundled_meipass_none(self):
        """Returns False when _MEIPASS is None."""
        with patch.object(sys, "_MEIPASS", None, create=True):
            assert is_bundled() is False


class TestGetDataDir:
    """Tests for get_data_dir()."""

    def test_dev_mode_returns_local_subdir(self):
        """In dev mode, returns the .local/ subdirectory of project root."""
        result = get_data_dir()
        assert result.name == ".local"
        # Parent should be the project root (contains main.py)
        assert (result.parent / "main.py").exists()

    def test_dev_mode_creates_local_dir(self):
        """In dev mode, .local/ directory is auto-created."""
        result = get_data_dir()
        assert result.is_dir()

    def test_bundled_mode_returns_app_support(self):
        """In bundled mode, returns ~/Library/Application Support/GreetingCards."""
        fake_home = Path("/fake/home")
        with patch.object(sys, "_MEIPASS", "/tmp/bundle", create=True), \
             patch.object(Path, "home", return_value=fake_home), \
             patch.object(Path, "mkdir"):
            result = get_data_dir()
            assert result == fake_home / "Library" / "Application Support" / "GreetingCards"

    def test_bundled_mode_creates_directory(self):
        """In bundled mode, auto-creates the data directory."""
        fake_home = Path("/fake/home")
        mock_mkdir = MagicMock()
        with patch.object(sys, "_MEIPASS", "/tmp/bundle", create=True), \
             patch.object(Path, "home", return_value=fake_home), \
             patch.object(Path, "mkdir", mock_mkdir):
            get_data_dir()
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestGetDbPath:
    """Tests for get_db_path()."""

    def test_returns_sqlite_path(self):
        """Returns a .sqlite file path in the data dir."""
        result = get_db_path()
        assert result.name == "GreetingCards.sqlite"
        assert result.parent == get_data_dir()

    def test_has_sqlite_extension(self):
        """The database path has .sqlite extension."""
        assert get_db_path().suffix == ".sqlite"
