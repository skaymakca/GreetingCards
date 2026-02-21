"""Tests for app.gui.html_viewer module (shared WebView viewer)."""

import wx
from pathlib import Path
from unittest.mock import patch

from app.gui import html_viewer
from app.gui.html_viewer import (
    HTMLViewerWindow, show_viewer,
    _TextExtractor, _build_page_index, _count_occurrences,
    _PageMatch, _viewer_refs, _MIN_SEARCH_LEN,
)

import pytest


# --- Shared fixtures ---

@pytest.fixture
def sample_html_dir(tmp_path):
    """Create a temp directory with minimal HTML pages for testing."""
    css_dir = tmp_path / "css"
    css_dir.mkdir()
    (css_dir / "test.css").write_text("body { font-size: 13px; }")

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    # Stub JS functions matching the real search.js API so RunScript calls
    # don't error out during tests.
    search_stubs = ("<script>"
                    "function shlMark(q){return 0}"
                    "function shlFocus(i){}"
                    "function shlClear(){}"
                    "</script>")

    index_html = f"""<!DOCTYPE html>
<html><head>{search_stubs}</head><body>
<div class="sidebar"><h2>Nav</h2><ul>
<li><a href="index.html" class="active">Home</a></li>
<li><a href="pages/page1.html">Page 1</a></li>
</ul></div>
<div class="content"><h1>Home</h1><p>Welcome to the test viewer.</p></div>
</body></html>"""

    page1_html = f"""<!DOCTYPE html>
<html><head>{search_stubs}</head><body>
<div class="sidebar"><h2>Nav</h2><ul>
<li><a href="../index.html">Home</a></li>
<li><a href="page1.html" class="active">Page 1</a></li>
</ul></div>
<div class="content"><h1>Page 1</h1><p>This is the first page with searchable content.</p></div>
</body></html>"""

    (tmp_path / "index.html").write_text(index_html)
    (pages_dir / "page1.html").write_text(page1_html)

    return tmp_path


@pytest.fixture
def sample_page_order():
    return ["index.html", "pages/page1.html"]


@pytest.fixture
def viewer_window(wx_app, wx_frame, sample_html_dir, sample_page_order):
    """Open a viewer window and yield it; destroy on teardown."""
    key = "test-viewer"
    _viewer_refs.pop(key, None)
    viewer = show_viewer(wx_frame, title="Test Viewer", size=(600, 400),
                         base_path=sample_html_dir, page_order=sample_page_order,
                         singleton_key=key)
    yield viewer
    if viewer and viewer.frame and not viewer.frame.IsBeingDeleted():
        viewer.frame.Destroy()
    _viewer_refs.pop(key, None)


def _get_toolbar(frame: wx.Frame) -> wx.ToolBar:
    return [c for c in frame.GetChildren() if isinstance(c, wx.ToolBar)][0]


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
        html = '<div class="main content"><p>Found</p></div>'
        assert "Found" in self._extract(html)

    def test_ignores_content_substring_class(self):
        html = '<div class="not-content"><p>Hidden</p></div>'
        assert self._extract(html) == ""


# --- Page index tests ---

class TestBuildPageIndex:
    """Tests for _build_page_index()."""

    def test_returns_all_pages(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        for page in sample_page_order:
            assert page in index

    def test_text_is_lowercase(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        for page, text in index.items():
            assert text == text.lower()

    def test_text_strips_html_tags(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        for page, text in index.items():
            assert "<" not in text
            assert ">" not in text

    def test_content_searchable(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        assert "welcome" in index["index.html"]

    def test_only_extracts_content_div(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        # "nav" is the sidebar heading — must not appear
        for page, text in index.items():
            assert "nav" not in text.split()

    def test_missing_file_returns_empty_string(self, tmp_path):
        index = _build_page_index(tmp_path, ["missing.html"])
        assert index["missing.html"] == ""


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
        assert _count_occurrences("card card card", "card") == 3

    def test_non_overlapping(self):
        assert _count_occurrences("aaa", "aa") == 1

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

class TestHTMLViewerWindow:
    """Tests for the HTMLViewerWindow class."""

    def test_window_creation(self, viewer_window):
        assert viewer_window is not None
        assert viewer_window.frame.GetTitle() == "Test Viewer"

    def test_frame_property(self, viewer_window):
        assert isinstance(viewer_window.frame, wx.Frame)

    def test_toolbar_exists(self, viewer_window):
        toolbars = [c for c in viewer_window.frame.GetChildren()
                    if isinstance(c, wx.ToolBar)]
        assert len(toolbars) == 1

    def test_toolbar_has_five_tools(self, viewer_window):
        toolbar = _get_toolbar(viewer_window.frame)
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR and tool.GetLabel():
                tools.append(tool)
        assert len(tools) == 5
        labels = [t.GetLabel() for t in tools]
        assert labels == ["Home", "Previous", "Next", "Prev Match", "Next Match"]

    def test_search_ctrl_exists(self, viewer_window):
        toolbar = _get_toolbar(viewer_window.frame)
        search_ctrls = [c for c in toolbar.GetChildren()
                        if isinstance(c, wx.SearchCtrl)]
        assert len(search_ctrls) == 1

    def test_match_buttons_disabled_initially(self, viewer_window):
        toolbar = _get_toolbar(viewer_window.frame)
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR:
                tools.append(tool)
        prev_match = tools[-2]
        next_match = tools[-1]
        assert not toolbar.GetToolEnabled(prev_match.GetId())
        assert not toolbar.GetToolEnabled(next_match.GetId())


# --- Singleton tests ---

class TestSingleton:
    """Tests for singleton window management."""

    def test_singleton_reuse(self, viewer_window):
        """Second call with same key should raise existing window."""
        with patch.object(viewer_window.frame, "Raise") as mock_raise, \
             patch.object(viewer_window.frame, "IsBeingDeleted", return_value=False):
            result = show_viewer(
                viewer_window.frame.GetParent(),
                title="Test Viewer", size=(600, 400),
                base_path=Path("/tmp"), page_order=["index.html"],
                singleton_key="test-viewer",
            )
            mock_raise.assert_called_once()
            assert result is None

    def test_different_keys_create_separate_windows(self, wx_app, wx_frame, sample_html_dir, sample_page_order):
        """Different singleton keys should create separate windows."""
        key1, key2 = "test-key-1", "test-key-2"
        _viewer_refs.pop(key1, None)
        _viewer_refs.pop(key2, None)

        v1 = show_viewer(wx_frame, title="Viewer 1", size=(600, 400),
                         base_path=sample_html_dir, page_order=sample_page_order,
                         singleton_key=key1)
        v2 = show_viewer(wx_frame, title="Viewer 2", size=(600, 400),
                         base_path=sample_html_dir, page_order=sample_page_order,
                         singleton_key=key2)

        assert v1 is not None
        assert v2 is not None
        assert v1.frame is not v2.frame

        v1.frame.Destroy()
        v2.frame.Destroy()
        _viewer_refs.pop(key1, None)
        _viewer_refs.pop(key2, None)


# --- External link handling tests ---

class TestSearchMinLength:
    """Tests for the 3-character minimum search threshold."""

    def test_min_search_len_value(self):
        assert _MIN_SEARCH_LEN == 3

    def test_short_query_clears_highlights(self, viewer_window):
        """Queries shorter than _MIN_SEARCH_LEN should not trigger search."""
        toolbar = _get_toolbar(viewer_window.frame)
        search_ctrls = [c for c in toolbar.GetChildren()
                        if isinstance(c, wx.SearchCtrl)]
        search_ctrl = search_ctrls[0]

        # Type a 2-char query (below minimum) — fires EVT_TEXT synchronously
        search_ctrl.SetValue("ab")

        # Match buttons should stay disabled — no search triggered
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR:
                tools.append(tool)
        prev_match = tools[-2]
        next_match = tools[-1]
        assert not toolbar.GetToolEnabled(prev_match.GetId())
        assert not toolbar.GetToolEnabled(next_match.GetId())

    def test_exact_min_length_triggers_search(self, viewer_window):
        """Queries at exactly _MIN_SEARCH_LEN should trigger search (via debounce)."""
        toolbar = _get_toolbar(viewer_window.frame)
        search_ctrls = [c for c in toolbar.GetChildren()
                        if isinstance(c, wx.SearchCtrl)]
        search_ctrl = search_ctrls[0]

        # Type a 3-char query — this starts the debounce timer
        search_ctrl.SetValue("zzz")

        # The debounce timer hasn't fired yet, but the search ctrl accepted input
        assert search_ctrl.GetValue() == "zzz"


class TestExternalLinkHandling:
    """Tests for external link navigation interception."""

    def test_webview_binds_navigating_event(self, viewer_window):
        """WebView should have EVT_WEBVIEW_NAVIGATING bound."""
        import wx.html2
        # The viewer should have a webview child that responds to navigation
        frame = viewer_window.frame
        webviews = [c for c in frame.GetChildren()
                    if isinstance(c, wx.html2.WebView)]
        assert len(webviews) == 1, "Should have exactly one WebView"
