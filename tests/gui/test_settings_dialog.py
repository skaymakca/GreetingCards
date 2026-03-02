"""Tests for app.gui.settings_dialog module."""

from unittest.mock import MagicMock, patch

import wx

from app.gui.dialogs.settings import (
    AdvancedPreferencesPage,
    GeneralPreferencesPage,
    create_preferences_editor,
)

# Shared callback stubs for GeneralPreferencesPage construction
_STUB_CALLBACKS = {
    "get_api_key": lambda: None,
    "save_api_key": lambda _key: None,
    "get_ai_model": lambda: "claude-sonnet-4-6",
    "save_ai_model": lambda _model: None,
}


def _make_page(**overrides: object) -> GeneralPreferencesPage:
    """Create a GeneralPreferencesPage with stub callbacks (overridable)."""
    kw = {**_STUB_CALLBACKS, **overrides}
    return GeneralPreferencesPage(**kw)  # type: ignore[arg-type]


class TestGeneralPreferencesPage:
    """Tests for GeneralPreferencesPage."""

    def test_creation(self, wx_app):
        page = _make_page()
        assert page is not None

    def test_create_window(self, wx_app, wx_frame):
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        assert isinstance(panel, wx.Panel)
        panel.Destroy()

    def test_existing_key_populated(self, wx_app, wx_frame):
        page = _make_page(get_api_key=lambda: "sk-existing")
        panel = page.CreateWindow(wx_frame)
        assert page._key_entry.GetValue() == "sk-existing"
        panel.Destroy()

    def test_save_api_key(self, wx_app, wx_frame):
        mock_save = MagicMock()
        page = _make_page(save_api_key=mock_save)
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-new")
        page._save_api_key(None)
        mock_save.assert_called_once_with("sk-new")
        assert page._key_status.GetLabel() == "Saved"
        panel.Destroy()

    def test_save_empty_key_shows_error(self, wx_app, wx_frame):
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("")
        page._save_api_key(None)
        assert "empty" in page._key_status.GetLabel().lower()
        panel.Destroy()

    def test_status_shown_after_save(self, wx_app, wx_frame):
        """Status label is visible immediately after saving."""
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-test")
        page._save_api_key(None)
        assert page._key_status.IsShown()
        panel.Destroy()

    def test_status_auto_hides(self, wx_app, wx_frame):
        """Status label is hidden after the timer fires."""
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-test")
        page._save_api_key(None)
        assert page._key_status.IsShown()
        # Simulate timer firing
        page._cancel_status()
        assert not page._key_status.IsShown()
        panel.Destroy()

    def test_status_timer_resets_on_repeated_save(self, wx_app, wx_frame):
        """Saving again restarts the auto-hide timer."""
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-test")
        page._save_api_key(None)
        first_timer = page._status_timer
        page._save_api_key(None)
        # Timer object replaced (old one stopped, new one started)
        assert page._status_timer is not first_timer
        assert page._key_status.IsShown()
        panel.Destroy()

    def test_status_hidden_on_panel_hide(self, wx_app, wx_frame):
        """Status label is hidden when panel is hidden (window closing)."""
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-test")
        page._save_api_key(None)
        assert page._key_status.IsShown()
        # Simulate window closing (EVT_SHOW fires with show=False)
        hide_event = wx.ShowEvent()
        hide_event.SetShow(False)
        page._on_panel_shown(hide_event)
        assert not page._key_status.IsShown()
        assert page._status_timer is None
        panel.Destroy()

    def test_status_hidden_on_panel_reshow(self, wx_app, wx_frame):
        """Status label is hidden when panel is shown again (safety net)."""
        page = _make_page()
        panel = page.CreateWindow(wx_frame)
        page._key_entry.SetValue("sk-test")
        page._save_api_key(None)
        assert page._key_status.IsShown()
        # Simulate reopening (EVT_SHOW fires with show=True)
        show_event = wx.ShowEvent()
        show_event.SetShow(True)
        page._on_panel_shown(show_event)
        assert not page._key_status.IsShown()
        assert page._status_timer is None
        panel.Destroy()

    def test_model_dropdown_exists_with_default(self, wx_app, wx_frame):
        page = _make_page(get_ai_model=lambda: "claude-sonnet-4-6")
        panel = page.CreateWindow(wx_frame)
        assert hasattr(page, "_model_choice")
        assert isinstance(page._model_choice, wx.Choice)
        # Sonnet 4.6 is index 1 in AI_MODELS
        assert page._model_choice.GetSelection() == 1
        assert "Sonnet" in page._model_choice.GetString(1)
        panel.Destroy()

    def test_model_selection_saves(self, wx_app, wx_frame):
        mock_save = MagicMock()
        page = _make_page(
            get_ai_model=lambda: "claude-sonnet-4-6",
            save_ai_model=mock_save,
        )
        panel = page.CreateWindow(wx_frame)
        page._model_choice.SetSelection(0)  # Haiku
        page._on_model_changed(None)
        mock_save.assert_called_once_with("claude-haiku-4-5")
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

    @patch("app.gui.dialogs.settings.wx.MessageBox", return_value=wx.OK)
    def test_reset_card_data_confirmed(self, mock_msgbox, wx_app, wx_frame):
        callback = MagicMock()
        page = AdvancedPreferencesPage(on_db_reset=callback)
        page._reset_card_data(None)
        callback.assert_called_once()

    @patch("app.gui.dialogs.settings.wx.MessageBox", return_value=wx.CANCEL)
    def test_reset_card_data_cancelled(self, mock_msgbox, wx_app, wx_frame):
        callback = MagicMock()
        page = AdvancedPreferencesPage(on_db_reset=callback)
        page._reset_card_data(None)
        callback.assert_not_called()


class TestCreatePreferencesEditor:
    """Tests for create_preferences_editor factory function."""

    def test_creates_editor(self, wx_app):
        editor = create_preferences_editor(**_STUB_CALLBACKS)  # type: ignore[arg-type]
        assert isinstance(editor, wx.PreferencesEditor)

    def test_creates_editor_with_callback(self, wx_app):
        callback = MagicMock()
        editor = create_preferences_editor(on_db_reset=callback, **_STUB_CALLBACKS)  # type: ignore[arg-type]
        assert isinstance(editor, wx.PreferencesEditor)
