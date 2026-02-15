"""Tests for app.gui.help_dialog module."""
import wx
import pytest

from app.gui.help_dialog import HelpDialog


class TestHelpDialog:
    """Tests for HelpDialog."""

    def test_creation(self, wx_app, wx_frame):
        dlg = HelpDialog(wx_frame)
        assert dlg is not None
        dlg.Destroy()

    def test_title(self, wx_app, wx_frame):
        dlg = HelpDialog(wx_frame)
        assert dlg.GetTitle() == "Help"
        dlg.Destroy()

    def test_html_contains_workflow(self, wx_app, wx_frame):
        dlg = HelpDialog(wx_frame)
        html = dlg._generate_html()
        assert "Workflow" in html
        dlg.Destroy()

    def test_html_contains_shortcuts(self, wx_app, wx_frame):
        dlg = HelpDialog(wx_frame)
        html = dlg._generate_html()
        assert "Keyboard Shortcuts" in html
        dlg.Destroy()

    def test_html_contains_zoom(self, wx_app, wx_frame):
        dlg = HelpDialog(wx_frame)
        html = dlg._generate_html()
        assert "Zoom" in html
        dlg.Destroy()

    def test_escape_key_handler_exists(self, wx_app, wx_frame):
        dlg = HelpDialog(wx_frame)
        # Verify the _on_key method exists
        assert hasattr(dlg, "_on_key")
        dlg.Destroy()
