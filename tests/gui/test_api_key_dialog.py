"""Tests for app.gui.api_key_dialog module."""

from unittest.mock import MagicMock, patch

import wx

from app.gui.dialogs.api_key import show_api_key_dialog


class TestShowApiKeyDialog:
    """Tests for show_api_key_dialog()."""

    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_ok_returns_key(self, MockDialog, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_OK
        dlg.GetValue.return_value = "sk-test-key"
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result == "sk-test-key"
        dlg.Destroy.assert_called()

    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_cancel_returns_none(self, MockDialog, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_CANCEL
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result is None
        dlg.Destroy.assert_called()

    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_empty_returns_none(self, MockDialog, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_OK
        dlg.GetValue.return_value = ""
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result is None

    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_strips_whitespace(self, MockDialog, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_OK
        dlg.GetValue.return_value = "  sk-key  "
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result == "sk-key"

    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_destroy_always_called(self, MockDialog, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_CANCEL
        MockDialog.return_value = dlg

        show_api_key_dialog(None)
        dlg.Destroy.assert_called_once()
