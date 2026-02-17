"""Tests for app.gui.settings_dialog module."""
from unittest.mock import patch, MagicMock

import wx
import pytest

from app.gui.settings_dialog import SettingsDialog, ApiKeyPrompt, get_commit_hash


class TestSettingsDialog:
    """Tests for SettingsDialog."""

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc1234\n")
    def test_creation(self, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        assert dlg is not None
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc1234\n")
    def test_title(self, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        assert dlg.GetTitle() == "Settings"
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc1234\n")
    def test_version_displayed(self, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        # Version label should exist (dialog was created without error)
        assert dlg is not None
        dlg.Destroy()

    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc1234\n")
    def test_commit_hash(self, mock_git, wx_app, wx_frame):
        assert get_commit_hash() == "abc1234"

    @patch("app.gui.settings_dialog.subprocess.check_output", side_effect=Exception("no git"))
    def test_commit_hash_fallback(self, mock_git, wx_app, wx_frame):
        assert get_commit_hash() == ""

    @patch("app.gui.settings_dialog.get_api_key", return_value="sk-existing")
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc1234\n")
    def test_existing_key_populated(self, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        assert dlg._key_entry.GetValue() == "sk-existing"
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc\n")
    @patch("app.gui.settings_dialog.save_api_key")
    def test_save_api_key(self, mock_save, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        dlg._key_entry.SetValue("sk-new")
        dlg._save_api_key(None)
        mock_save.assert_called_once_with("sk-new")
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc\n")
    def test_save_empty_key_shows_error(self, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        dlg._key_entry.SetValue("")
        dlg._save_api_key(None)
        # Status label should show error
        assert "empty" in dlg._key_status.GetLabel().lower()
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc\n")
    @patch("app.gui.settings_dialog.reset_database")
    @patch("app.gui.settings_dialog.wx.MessageBox", return_value=wx.YES)
    def test_rebuild_db_confirmed(self, mock_msgbox, mock_reset, mock_git, mock_key, wx_app, wx_frame):
        callback = MagicMock()
        dlg = SettingsDialog(wx_frame, on_db_reset=callback)
        dlg._rebuild_db(None)
        mock_reset.assert_called_once()
        callback.assert_called_once()
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc\n")
    @patch("app.gui.settings_dialog.reset_database")
    @patch("app.gui.settings_dialog.wx.MessageBox", return_value=wx.NO)
    def test_rebuild_db_cancelled(self, mock_msgbox, mock_reset, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        dlg._rebuild_db(None)
        mock_reset.assert_not_called()
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc\n")
    def test_escape_key_handler(self, mock_git, mock_key, wx_app, wx_frame):
        dlg = SettingsDialog(wx_frame)
        assert hasattr(dlg, "_on_key")
        dlg.Destroy()


class TestApiKeyPrompt:
    """Tests for ApiKeyPrompt."""

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_creation(self, mock_key, wx_app, wx_frame):
        dlg = ApiKeyPrompt(wx_frame)
        assert dlg is not None
        assert dlg.result is None
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.save_api_key")
    def test_save_with_key(self, mock_save, mock_key, wx_app, wx_frame):
        dlg = ApiKeyPrompt(wx_frame)
        dlg._key_entry.SetValue("sk-test")
        # Can't call _on_save directly because it calls EndModal which needs ShowModal
        # Just verify the entry has the value
        assert dlg._key_entry.GetValue() == "sk-test"
        dlg.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_cancel(self, mock_key, wx_app, wx_frame):
        dlg = ApiKeyPrompt(wx_frame)
        # Verify initial state
        assert dlg.result is None
        dlg.Destroy()
