"""Tests for app.gui.help_dialog module (WebView help system)."""

import wx
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.gui import help_dialog
from app.gui.help_dialog import show_help, _get_help_index_path, _PAGE_ORDER


class TestGetHelpIndexPath:
    """Tests for _get_help_index_path()."""

    def test_returns_path_object(self):
        result = _get_help_index_path()
        assert isinstance(result, Path)

    def test_path_ends_with_index_html(self):
        result = _get_help_index_path()
        assert result.name == "index.html"
        assert "GreetingCards.help" in str(result)

    def test_path_exists_in_dev_mode(self):
        result = _get_help_index_path()
        assert result.exists(), f"Help index not found at {result}"

    @patch("app.gui.help_dialog.is_bundled", return_value=True)
    def test_bundle_path_uses_meipass(self, mock_bundled):
        with patch("app.gui.help_dialog.sys") as mock_sys:
            mock_sys._MEIPASS = "/fake/bundle"
            result = _get_help_index_path()
            assert str(result).startswith("/fake/bundle")
            assert "GreetingCards.help" in str(result)


class TestHelpContentFiles:
    """Tests that all help content pages exist."""

    EXPECTED_PAGES = [
        "index.html",
        "pages/getting-started.html",
        "pages/toolbar.html",
        "pages/card-list.html",
        "pages/preview.html",
        "pages/shortcuts.html",
        "pages/tips.html",
    ]

    def test_all_pages_exist(self):
        base = _get_help_index_path().parent
        for rel_path in self.EXPECTED_PAGES:
            full_path = base / rel_path
            assert full_path.exists(), f"Missing help page: {full_path}"

    def test_css_exists(self):
        base = _get_help_index_path().parent
        assert (base / "css" / "help.css").exists()

    def test_pages_contain_sidebar(self):
        """All pages should include the CSS sidebar nav."""
        base = _get_help_index_path().parent
        for rel_path in self.EXPECTED_PAGES:
            content = (base / rel_path).read_text()
            assert 'class="sidebar"' in content, f"No sidebar in {rel_path}"
            assert 'class="content"' in content, f"No content div in {rel_path}"

    def test_each_page_marks_itself_active(self):
        """Each page should have exactly one 'active' link in the sidebar."""
        base = _get_help_index_path().parent
        for rel_path in self.EXPECTED_PAGES:
            content = (base / rel_path).read_text()
            assert content.count('class="active"') == 1, \
                f"Expected 1 active link in {rel_path}, found {content.count('class=\"active\"')}"


class TestHelpWebViewWindow:
    """Tests for the WebView help window."""

    def _open_and_get_window(self, wx_frame):
        """Helper: open help webview and return the frame."""
        help_dialog._help_window_ref = None
        show_help(wx_frame)
        return help_dialog._help_window_ref()

    def test_window_creation(self, wx_app, wx_frame):
        window = self._open_and_get_window(wx_frame)
        assert window is not None
        assert window.GetTitle() == "Greeting Cards Help"
        window.Destroy()

    def test_singleton_reuse(self, wx_app, wx_frame):
        """Second call should raise existing window, not create new one."""
        window = self._open_and_get_window(wx_frame)

        with patch.object(window, "Raise") as mock_raise, \
             patch.object(window, "IsBeingDeleted", return_value=False):
            show_help(wx_frame)
            mock_raise.assert_called_once()

        window.Destroy()

    def test_creates_new_after_close(self, wx_app, wx_frame):
        """After old window is destroyed, a new one should be created."""
        window = self._open_and_get_window(wx_frame)
        window.Destroy()
        help_dialog._help_window_ref = None

        show_help(wx_frame)
        second_window = help_dialog._help_window_ref()
        assert second_window is not None
        second_window.Destroy()


class TestHelpToolbar:
    """Tests for the help window navigation toolbar."""

    def _open_and_get_window(self, wx_frame):
        """Helper: open help webview and return the frame."""
        help_dialog._help_window_ref = None
        show_help(wx_frame)
        return help_dialog._help_window_ref()

    def test_toolbar_exists(self, wx_app, wx_frame):
        """Help window should have a toolbar."""
        window = self._open_and_get_window(wx_frame)
        toolbars = [c for c in window.GetChildren() if isinstance(c, wx.ToolBar)]
        assert len(toolbars) == 1
        window.Destroy()

    def test_toolbar_has_three_tools(self, wx_app, wx_frame):
        """Toolbar should have Home, Previous, Next tools."""
        window = self._open_and_get_window(wx_frame)
        toolbar = [c for c in window.GetChildren() if isinstance(c, wx.ToolBar)][0]
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR:
                tools.append(tool)
        assert len(tools) == 3
        labels = [t.GetLabel() for t in tools]
        assert labels == ["Home", "Previous", "Next"]
        window.Destroy()

    def test_prev_disabled_on_home_page(self, wx_app, wx_frame):
        """Previous button should be disabled when on index.html."""
        window = self._open_and_get_window(wx_frame)
        toolbar = [c for c in window.GetChildren() if isinstance(c, wx.ToolBar)][0]
        prev_tool = toolbar.GetToolByPos(1)
        assert not toolbar.GetToolEnabled(prev_tool.GetId())
        window.Destroy()

    def test_page_order_matches_expected_pages(self):
        """_PAGE_ORDER should match the expected help pages."""
        expected = TestHelpContentFiles.EXPECTED_PAGES
        assert _PAGE_ORDER == expected
