"""Tests for app.gui.api_key_dialog module."""

from unittest.mock import MagicMock, patch

import pytest
import wx

from app.gui.dialogs.api_key import show_api_key_dialog


class TestShowApiKeyDialog:
    """Tests for show_api_key_dialog()."""

    @patch("app.gui.dialogs.api_key.save_api_key")
    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_ok_returns_key(self, MockDialog, mock_save, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_OK
        dlg.GetValue.return_value = "sk-test-key"
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result == "sk-test-key"
        mock_save.assert_called_once_with("sk-test-key")
        dlg.Destroy.assert_called()

    @patch("app.gui.dialogs.api_key.save_api_key")
    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_cancel_returns_none(self, MockDialog, mock_save, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_CANCEL
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result is None
        mock_save.assert_not_called()
        dlg.Destroy.assert_called()

    @patch("app.gui.dialogs.api_key.save_api_key")
    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_empty_returns_none(self, MockDialog, mock_save, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_OK
        dlg.GetValue.return_value = ""
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result is None
        mock_save.assert_not_called()

    @patch("app.gui.dialogs.api_key.save_api_key")
    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_strips_whitespace(self, MockDialog, mock_save, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_OK
        dlg.GetValue.return_value = "  sk-key  "
        MockDialog.return_value = dlg

        result = show_api_key_dialog(None)
        assert result == "sk-key"
        mock_save.assert_called_once_with("sk-key")

    @patch("app.gui.dialogs.api_key.wx.TextEntryDialog")
    def test_destroy_always_called(self, MockDialog, wx_app):
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_CANCEL
        MockDialog.return_value = dlg

        show_api_key_dialog(None)
        dlg.Destroy.assert_called_once()
