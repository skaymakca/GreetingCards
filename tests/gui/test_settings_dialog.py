"""Tests for app.gui.settings_dialog module."""
from unittest.mock import patch, MagicMock

import wx

from app.gui.settings_dialog import (
    GeneralPreferencesPage, AdvancedPreferencesPage,
    create_preferences_editor, get_commit_hash,
)


class TestGetCommitHash:
    """Tests for get_commit_hash."""

    @patch("app.gui.settings_dialog.subprocess.check_output", return_value=b"abc1234\n")
    def test_commit_hash(self, mock_git, wx_app):
        assert get_commit_hash() == "abc1234"

    @patch("app.gui.settings_dialog.subprocess.check_output", side_effect=FileNotFoundError("no git"))
    def test_commit_hash_fallback(self, mock_git, wx_app):
        assert get_commit_hash() == ""


class TestGeneralPreferencesPage:
    """Tests for GeneralPreferencesPage."""

    def test_creation(self, wx_app):
        page = GeneralPreferencesPage()
        assert page is not None

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_create_window(self, mock_key, wx_app, wx_frame):
        page = GeneralPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        assert isinstance(panel, wx.Panel)
        panel.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value="sk-existing")
    def test_existing_key_populated(self, mock_key, wx_app, wx_frame):
        page = GeneralPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        assert page._key_entry.GetValue() == "sk-existing"
        panel.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    @patch("app.gui.settings_dialog.save_api_key")
    def test_save_api_key(self, mock_save, mock_key, wx_app, wx_frame):
        page = GeneralPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-new")
        page._save_api_key(None)
        mock_save.assert_called_once_with("sk-new")
        assert page._key_status.GetLabel() == "Saved"
        panel.Destroy()

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_save_empty_key_shows_error(self, mock_key, wx_app, wx_frame):
        page = GeneralPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("")
        page._save_api_key(None)
        assert "empty" in page._key_status.GetLabel().lower()
        panel.Destroy()

    @patch("app.gui.settings_dialog.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_model_dropdown_exists_with_default(self, mock_key, mock_model, wx_app, wx_frame):
        page = GeneralPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        assert hasattr(page, "_model_choice")
        assert isinstance(page._model_choice, wx.Choice)
        # Sonnet 4.6 is index 1 in AI_MODELS
        assert page._model_choice.GetSelection() == 1
        assert "Sonnet" in page._model_choice.GetString(1)
        panel.Destroy()

    @patch("app.gui.settings_dialog.save_ai_model")
    @patch("app.gui.settings_dialog.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_model_selection_saves(self, mock_key, mock_model, mock_save, wx_app, wx_frame):
        page = GeneralPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        page._model_choice.SetSelection(0)  # Haiku
        page._on_model_changed(None)
        mock_save.assert_called_once_with("claude-haiku-4-5-20251001")
        panel.Destroy()


class TestAdvancedPreferencesPage:
    """Tests for AdvancedPreferencesPage."""

    def test_creation(self, wx_app):
        page = AdvancedPreferencesPage()
        assert page is not None

    def test_creation_with_callback(self, wx_app):
        callback = MagicMock()
        page = AdvancedPreferencesPage(on_db_reset=callback)
        assert page._on_db_reset is callback

    def test_create_window(self, wx_app, wx_frame):
        page = AdvancedPreferencesPage()
        panel = page.CreateWindow(wx_frame)
        assert isinstance(panel, wx.Panel)
        panel.Destroy()

    @patch("app.gui.settings_dialog.reset_database")
    @patch("app.gui.settings_dialog.wx.MessageBox", return_value=wx.OK)
    def test_reset_card_data_confirmed(self, mock_msgbox, mock_reset, wx_app, wx_frame):
        callback = MagicMock()
        page = AdvancedPreferencesPage(on_db_reset=callback)
        page._reset_card_data(None)
        mock_reset.assert_called_once()
        callback.assert_called_once()

    @patch("app.gui.settings_dialog.reset_database")
    @patch("app.gui.settings_dialog.wx.MessageBox", return_value=wx.CANCEL)
    def test_reset_card_data_cancelled(self, mock_msgbox, mock_reset, wx_app, wx_frame):
        page = AdvancedPreferencesPage()
        page._reset_card_data(None)
        mock_reset.assert_not_called()


class TestCreatePreferencesEditor:
    """Tests for create_preferences_editor factory function."""

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_creates_editor(self, mock_key, wx_app):
        editor = create_preferences_editor()
        assert isinstance(editor, wx.PreferencesEditor)

    @patch("app.gui.settings_dialog.get_api_key", return_value=None)
    def test_creates_editor_with_callback(self, mock_key, wx_app):
        callback = MagicMock()
        editor = create_preferences_editor(on_db_reset=callback)
        assert isinstance(editor, wx.PreferencesEditor)
