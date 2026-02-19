"""Tests for app.gui.help_dialog module (WebView help system)."""

import wx
from unittest.mock import patch
from pathlib import Path

from app.gui import help_dialog
from app.gui.help_dialog import (
    show_help, _get_help_index_path, _get_help_base_path,
    _PAGE_ORDER, _PageMatch, _build_page_index, _count_occurrences,
    _TextExtractor, _HELP_REL_PATH, _WINDOW_TITLE,
)

import pytest


# --- Shared fixtures ---

@pytest.fixture
def help_window(wx_app, wx_frame):
    """Open help window and yield it; destroy on teardown."""
    help_dialog._help_window_ref = None
    show_help(wx_frame)
    window = help_dialog._help_window_ref()
    yield window
    if window and not window.IsBeingDeleted():
        window.Destroy()


def _get_toolbar(window: wx.Frame) -> wx.ToolBar:
    """Return the toolbar from the help window."""
    return [c for c in window.GetChildren() if isinstance(c, wx.ToolBar)][0]


# --- Path tests ---

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

    def test_help_rel_path_is_consistent(self):
        """_HELP_REL_PATH should end with en.lproj."""
        assert _HELP_REL_PATH.name == "en.lproj"
        assert "GreetingCards.help" in str(_HELP_REL_PATH)


# --- Content file tests ---

class TestHelpContentFiles:
    """Tests that all help content pages exist."""

    def test_all_pages_exist(self):
        base = _get_help_base_path()
        for rel_path in _PAGE_ORDER:
            full_path = base / rel_path
            assert full_path.exists(), f"Missing help page: {full_path}"

    def test_css_exists(self):
        base = _get_help_base_path()
        assert (base / "css" / "help.css").exists()

    def test_pages_contain_sidebar(self):
        """All pages should include the CSS sidebar nav."""
        base = _get_help_base_path()
        for rel_path in _PAGE_ORDER:
            content = (base / rel_path).read_text()
            assert 'class="sidebar"' in content, f"No sidebar in {rel_path}"
            assert 'class="content"' in content, f"No content div in {rel_path}"

    def test_each_page_marks_itself_active(self):
        """Each page should have exactly one 'active' link in the sidebar."""
        base = _get_help_base_path()
        for rel_path in _PAGE_ORDER:
            content = (base / rel_path).read_text()
            assert content.count('class="active"') == 1, \
                f"Expected 1 active link in {rel_path}, found {content.count('class=\"active\"')}"


# --- TextExtractor tests ---

class TestTextExtractor:
    """Tests for _TextExtractor HTML parser."""

    def _extract(self, html: str) -> str:
        ext = _TextExtractor()
        ext.feed(html)
        return ext.get_text()

    def test_extracts_content_div_text(self):
        html = '<div class="content"><p>Hello world</p></div>'
        assert "Hello world" in self._extract(html)

    def test_ignores_sidebar(self):
        html = ('<div class="sidebar"><h2>Nav</h2></div>'
                '<div class="content"><p>Body</p></div>')
        text = self._extract(html)
        assert "Body" in text
        assert "Nav" not in text

    def test_ignores_text_outside_content(self):
        html = '<title>Page Title</title><div class="content">Inner</div>'
        text = self._extract(html)
        assert "Inner" in text
        assert "Page Title" not in text

    def test_ignores_script_inside_content(self):
        html = '<div class="content">Text<script>var x=1;</script> more</div>'
        text = self._extract(html)
        assert "Text" in text
        assert "more" in text
        assert "var" not in text

    def test_ignores_style_inside_content(self):
        html = '<div class="content">A<style>.x{color:red}</style>B</div>'
        text = self._extract(html)
        assert "A" in text
        assert "B" in text
        assert "color" not in text

    def test_handles_nested_divs_in_content(self):
        html = '<div class="content"><div class="inner">Nested</div> Outer</div>'
        text = self._extract(html)
        assert "Nested" in text
        assert "Outer" in text

    def test_empty_html(self):
        assert self._extract("") == ""

    def test_no_content_div(self):
        html = "<p>No content div here</p>"
        assert self._extract(html) == ""

    def test_matches_content_in_multi_class(self):
        """class='main content' should still match."""
        html = '<div class="main content"><p>Found</p></div>'
        assert "Found" in self._extract(html)

    def test_ignores_content_substring_class(self):
        """class='not-content' should NOT match."""
        html = '<div class="not-content"><p>Hidden</p></div>'
        assert self._extract(html) == ""


# --- Page index tests ---

class TestBuildPageIndex:
    """Tests for _build_page_index()."""

    def test_returns_all_pages(self):
        base = _get_help_base_path()
        index = _build_page_index(base)
        for page in _PAGE_ORDER:
            assert page in index

    def test_text_is_lowercase(self):
        base = _get_help_base_path()
        index = _build_page_index(base)
        for page, text in index.items():
            assert text == text.lower(), f"Text for {page} is not lowercase"

    def test_text_strips_html_tags(self):
        base = _get_help_base_path()
        index = _build_page_index(base)
        for page, text in index.items():
            assert "<" not in text, f"HTML tag found in {page}"
            assert ">" not in text, f"HTML tag found in {page}"

    def test_content_searchable(self):
        """Known words should be found on expected pages."""
        base = _get_help_base_path()
        index = _build_page_index(base)
        # index.html has "greeting cards help"
        assert "greeting cards help" in index["index.html"]

    def test_only_extracts_content_div(self):
        """Only text from .content div should appear; sidebar/title excluded."""
        base = _get_help_base_path()
        index = _build_page_index(base)
        # "contents" is the sidebar heading — must not appear in any page
        for page, text in index.items():
            assert "contents" not in text, \
                f"Sidebar heading 'contents' found in {page} index"

    def test_missing_file_returns_empty_string(self, tmp_path):
        """Gracefully handle missing files."""
        index = _build_page_index(tmp_path)
        for page in _PAGE_ORDER:
            assert index[page] == ""


# --- Count occurrences tests ---

class TestCountOccurrences:
    """Tests for _count_occurrences()."""

    def test_single_match(self):
        assert _count_occurrences("hello world", "world") == 1

    def test_multiple_matches(self):
        assert _count_occurrences("the card and the card list", "card") == 2

    def test_no_match(self):
        assert _count_occurrences("hello world", "xyz") == 0

    def test_empty_query(self):
        assert _count_occurrences("hello", "") == 0

    def test_case_sensitive_input(self):
        # function expects pre-lowercased text and query
        assert _count_occurrences("card card card", "card") == 3

    def test_non_overlapping(self):
        assert _count_occurrences("aaa", "aa") == 1

    def test_counts_on_real_index(self):
        """Verify counts against real help page index."""
        base = _get_help_base_path()
        index = _build_page_index(base)
        # "greeting cards help" appears at least once on index page
        assert _count_occurrences(index["index.html"], "greeting cards help") >= 1

    def test_empty_text(self):
        assert _count_occurrences("", "hello") == 0


# --- PageMatch NamedTuple tests ---

class TestPageMatch:
    """Tests for _PageMatch NamedTuple."""

    def test_fields(self):
        m = _PageMatch("index.html", 3)
        assert m.page == "index.html"
        assert m.count == 3

    def test_unpacking(self):
        m = _PageMatch("pages/tips.html", 5)
        page, count = m
        assert page == "pages/tips.html"
        assert count == 5


# --- WebView window tests ---

class TestHelpWebViewWindow:
    """Tests for the WebView help window."""

    def test_window_creation(self, help_window):
        assert help_window is not None
        assert help_window.GetTitle() == _WINDOW_TITLE

    def test_singleton_reuse(self, help_window):
        """Second call should raise existing window, not create new one."""
        with patch.object(help_window, "Raise") as mock_raise, \
             patch.object(help_window, "IsBeingDeleted", return_value=False):
            show_help(help_window.GetParent())
            mock_raise.assert_called_once()

    def test_creates_new_after_close(self, wx_app, wx_frame):
        """After old window is destroyed, a new one should be created."""
        help_dialog._help_window_ref = None
        show_help(wx_frame)
        window = help_dialog._help_window_ref()
        window.Destroy()
        help_dialog._help_window_ref = None

        show_help(wx_frame)
        second_window = help_dialog._help_window_ref()
        assert second_window is not None
        second_window.Destroy()


# --- Toolbar tests ---

class TestHelpToolbar:
    """Tests for the help window navigation toolbar."""

    def test_toolbar_exists(self, help_window):
        """Help window should have a toolbar."""
        toolbars = [c for c in help_window.GetChildren() if isinstance(c, wx.ToolBar)]
        assert len(toolbars) == 1

    def test_toolbar_has_five_tools(self, help_window):
        """Toolbar should have Home, Previous, Next, Prev Match, Next Match tools."""
        toolbar = _get_toolbar(help_window)
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR and tool.GetLabel():
                tools.append(tool)
        assert len(tools) == 5
        labels = [t.GetLabel() for t in tools]
        assert labels == ["Home", "Previous", "Next", "Prev Match", "Next Match"]

    def test_prev_disabled_on_home_page(self, help_window):
        """Previous button should be disabled when on index.html."""
        toolbar = _get_toolbar(help_window)
        prev_tool = toolbar.GetToolByPos(1)
        assert not toolbar.GetToolEnabled(prev_tool.GetId())

    def test_page_order_matches_expected_pages(self):
        """_PAGE_ORDER should list all expected help pages."""
        assert _PAGE_ORDER[0] == "index.html"
        assert len(_PAGE_ORDER) == 7
        assert all(p.endswith(".html") for p in _PAGE_ORDER)


# --- Search control tests ---

class TestHelpSearchCtrl:
    """Tests for the help search control."""

    def test_search_ctrl_exists(self, help_window):
        """Toolbar should contain a SearchCtrl."""
        toolbar = _get_toolbar(help_window)
        search_ctrls = [c for c in toolbar.GetChildren()
                        if isinstance(c, wx.SearchCtrl)]
        assert len(search_ctrls) == 1

    def test_search_ctrl_descriptive_text(self, help_window):
        """SearchCtrl should have 'Search help...' placeholder."""
        toolbar = _get_toolbar(help_window)
        search_ctrl = [c for c in toolbar.GetChildren()
                       if isinstance(c, wx.SearchCtrl)][0]
        assert search_ctrl.GetDescriptiveText() == "Search help..."

    def test_match_buttons_disabled_initially(self, help_window):
        """Prev/Next Match buttons should start disabled."""
        toolbar = _get_toolbar(help_window)
        # Get all tools (skip separators)
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR:
                tools.append(tool)
        # Prev Match and Next Match are the last two tools
        prev_match = tools[-2]
        next_match = tools[-1]
        assert not toolbar.GetToolEnabled(prev_match.GetId())
        assert not toolbar.GetToolEnabled(next_match.GetId())

    def test_search_label_exists(self, help_window):
        """Toolbar should contain a StaticText label for search results."""
        toolbar = _get_toolbar(help_window)
        labels = [c for c in toolbar.GetChildren()
                  if isinstance(c, wx.StaticText)]
        assert len(labels) == 1

    def test_search_label_empty_initially(self, help_window):
        """Search label should be empty when no search is active."""
        toolbar = _get_toolbar(help_window)
        label = [c for c in toolbar.GetChildren()
                 if isinstance(c, wx.StaticText)][0]
        assert label.GetLabel() == ""
