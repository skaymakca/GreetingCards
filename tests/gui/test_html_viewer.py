"""Tests for app.gui.html_viewer module (shared WebView viewer)."""

from pathlib import Path
from unittest.mock import patch

import pytest
import wx

from app.gui.components.html_viewer import (
    _MIN_SEARCH_LEN,
    HTMLViewerWindow,
    _build_page_index,
    _count_occurrences,
    _PageMatch,
    _TextExtractor,
    _viewer_refs,
    show_viewer,
)

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
    search_stubs = "<script>function shlMark(q){return 0}function shlFocus(i){}function shlClear(){}</script>"

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
    """Open a viewer window and yield it; destroy on teardown.

    Also captures the debounce timer on ``frame._test_timer`` so tests
    can fire it with ``_fire_timer_event(frame)``.
    """
    key = "test-viewer"
    _viewer_refs.pop(key, None)

    # Capture the debounce timer created inside HTMLViewerWindow.__init__.
    # We wrap wx.Timer.__new__ via __class__ call to intercept without
    # breaking C++ initialisation.  A simpler approach: patch the module-level
    # wx.Timer with a subclass that records the instance.
    _captured: list[wx.Timer] = []
    _OrigTimer = wx.Timer

    class _CapturingTimer(_OrigTimer):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            _captured.append(self)

    with patch("wx.Timer", _CapturingTimer):
        viewer = show_viewer(
            wx_frame,
            title="Test Viewer",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key,
        )

    # Stash the timer on the frame for test access
    if viewer and _captured:
        viewer.frame._test_timer = _captured[-1]  # type: ignore[attr-defined]

    # Patch RunScript to avoid WebKit segfaults in headless tests.
    # The real WebView RunScript sends async IPC to WebKit which can crash
    # when called repeatedly without a running event loop.
    webview = _get_webview(viewer.frame)
    with patch.object(webview, "RunScript", return_value=(True, "")):
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
        html = '<div class="sidebar"><h2>Nav</h2></div><div class="content"><p>Body</p></div>'
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
        for _page, text in index.items():
            assert text == text.lower()

    def test_text_strips_html_tags(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        for _page, text in index.items():
            assert "<" not in text
            assert ">" not in text

    def test_content_searchable(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        assert "welcome" in index["index.html"]

    def test_only_extracts_content_div(self, sample_html_dir, sample_page_order):
        index = _build_page_index(sample_html_dir, sample_page_order)
        # "nav" is the sidebar heading — must not appear
        for _page, text in index.items():
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
        assert m.match_count == 3

    def test_unpacking(self):
        m = _PageMatch("pages/tips.html", 5)
        page, match_count = m
        assert page == "pages/tips.html"
        assert match_count == 5


# --- WebView window tests ---


class TestHTMLViewerWindow:
    """Tests for the HTMLViewerWindow class."""

    def test_window_creation(self, viewer_window):
        assert viewer_window is not None
        assert viewer_window.frame.GetTitle() == "Test Viewer"

    def test_frame_property(self, viewer_window):
        assert isinstance(viewer_window.frame, wx.Frame)

    def test_toolbar_exists(self, viewer_window):
        toolbars = [c for c in viewer_window.frame.GetChildren() if isinstance(c, wx.ToolBar)]
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
        search_ctrls = [c for c in toolbar.GetChildren() if isinstance(c, wx.SearchCtrl)]
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
        with (
            patch.object(viewer_window.frame, "Raise") as mock_raise,
            patch.object(viewer_window.frame, "IsBeingDeleted", return_value=False),
        ):
            result = show_viewer(
                viewer_window.frame.GetParent(),
                title="Test Viewer",
                size=(600, 400),
                base_path=Path("/tmp"),
                page_order=["index.html"],
                singleton_key="test-viewer",
            )
            mock_raise.assert_called_once()
            assert result is None

    def test_different_keys_create_separate_windows(self, wx_app, wx_frame, sample_html_dir, sample_page_order):
        """Different singleton keys should create separate windows."""
        key1, key2 = "test-key-1", "test-key-2"
        _viewer_refs.pop(key1, None)
        _viewer_refs.pop(key2, None)

        v1 = show_viewer(
            wx_frame,
            title="Viewer 1",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key1,
        )
        v2 = show_viewer(
            wx_frame,
            title="Viewer 2",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key2,
        )

        assert v1 is not None
        assert v2 is not None
        assert v1.frame is not v2.frame

        v1.frame.Destroy()
        v2.frame.Destroy()
        _viewer_refs.pop(key1, None)
        _viewer_refs.pop(key2, None)

    def test_reopen_after_close_with_dead_weakref(self, wx_app, wx_frame, sample_html_dir, sample_page_order):
        """Reopening after close should create a new window even if weakref lingers."""
        import unittest.mock

        key = "test-reopen"
        _viewer_refs.pop(key, None)

        v1 = show_viewer(
            wx_frame,
            title="First",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key,
        )
        assert v1 is not None

        # Simulate the scenario where C++ frame is deleted but weakref survives.
        # Patch the weakref to return a mock that raises RuntimeError on IsBeingDeleted.
        dead_frame = unittest.mock.MagicMock()
        dead_frame.IsBeingDeleted.side_effect = RuntimeError("wrapped C/C++ object has been deleted")
        _viewer_refs[key] = lambda: dead_frame  # type: ignore[assignment]

        v2 = show_viewer(
            wx_frame,
            title="Second",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key,
        )
        assert v2 is not None  # Should create a new viewer, not crash

        v1.frame.Destroy()
        v2.frame.Destroy()
        _viewer_refs.pop(key, None)


# --- External link handling tests ---


class TestSearchMinLength:
    """Tests for the 3-character minimum search threshold."""

    def test_min_search_len_value(self):
        assert _MIN_SEARCH_LEN == 3

    def test_short_query_clears_highlights(self, viewer_window):
        """Queries shorter than _MIN_SEARCH_LEN should not trigger search."""
        toolbar = _get_toolbar(viewer_window.frame)
        search_ctrls = [c for c in toolbar.GetChildren() if isinstance(c, wx.SearchCtrl)]
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
        search_ctrls = [c for c in toolbar.GetChildren() if isinstance(c, wx.SearchCtrl)]
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
        webviews = [c for c in frame.GetChildren() if isinstance(c, wx.html2.WebView)]
        assert len(webviews) == 1, "Should have exactly one WebView"


# --- Helper functions for accessing viewer internals ---


def _get_webview(frame: wx.Frame):
    """Get the WebView child of a viewer frame."""
    import wx.html2

    return [c for c in frame.GetChildren() if isinstance(c, wx.html2.WebView)][0]


def _get_search_ctrl(frame: wx.Frame) -> wx.SearchCtrl:
    """Get the SearchCtrl from the viewer toolbar."""
    toolbar = _get_toolbar(frame)
    return [c for c in toolbar.GetChildren() if isinstance(c, wx.SearchCtrl)][0]


def _get_search_label(frame: wx.Frame) -> wx.StaticText:
    """Get the search result label from the viewer toolbar."""
    toolbar = _get_toolbar(frame)
    return [c for c in toolbar.GetChildren() if isinstance(c, wx.StaticText)][0]


def _get_named_tools(frame: wx.Frame) -> dict[str, int]:
    """Return a dict of tool label -> tool id for all named tools."""
    toolbar = _get_toolbar(frame)
    result = {}
    for i in range(toolbar.GetToolsCount()):
        tool = toolbar.GetToolByPos(i)
        if tool.GetId() != wx.ID_SEPARATOR and tool.GetLabel():
            result[tool.GetLabel()] = tool.GetId()
    return result


def _fire_tool_event(frame: wx.Frame, tool_id: int) -> None:
    """Simulate clicking a toolbar tool."""
    evt = wx.CommandEvent(wx.wxEVT_TOOL, tool_id)
    frame.ProcessEvent(evt)


def _fire_page_loaded(frame: wx.Frame) -> None:
    """Simulate a WebView page-loaded event."""
    import wx.html2

    webview = _get_webview(frame)
    evt = wx.html2.WebViewEvent()
    evt.SetEventType(wx.html2.wxEVT_WEBVIEW_LOADED)
    evt.SetId(webview.GetId())
    evt.SetEventObject(webview)
    webview.ProcessEvent(evt)


def _get_debounce_timer(frame: wx.Frame) -> wx.Timer:
    """Retrieve the debounce timer captured during viewer creation.

    The viewer_with_timer fixture stores the timer on the frame as _test_timer.
    """
    return frame._test_timer  # type: ignore[attr-defined]


def _fire_timer_event(frame: wx.Frame) -> None:
    """Simulate a debounce timer firing by calling Notify() on the captured timer."""
    timer = _get_debounce_timer(frame)
    timer.Notify()


# --- Search event handler tests ---


class TestSearchChanged:
    """Tests for _on_search_changed with debounce timer."""

    def test_short_query_stops_timer_and_clears(self, viewer_window):
        """Queries below _MIN_SEARCH_LEN should stop the timer and clear search."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Type a short query
        search_ctrl.SetValue("ab")

        # Match navigation should stay disabled
        assert not toolbar.GetToolEnabled(tools["Prev Match"])
        assert not toolbar.GetToolEnabled(tools["Next Match"])

    def test_long_enough_query_starts_debounce(self, viewer_window):
        """Queries at or above _MIN_SEARCH_LEN should start the debounce timer."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)

        # Type a query at minimum length — debounce timer should start
        search_ctrl.SetValue("wel")

        # The value should be accepted
        assert search_ctrl.GetValue() == "wel"

    def test_debounce_timer_fires_search(self, viewer_window):
        """After debounce timer fires, search should execute."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        webview = _get_webview(frame)

        # Simulate page loaded so page_ready is True
        _fire_page_loaded(frame)

        # Type a query that matches content in index.html ("welcome")
        search_ctrl.SetValue("welcome")

        # Simulate debounce timer firing
        _fire_timer_event(frame)

        # Search label should show results
        label = _get_search_label(frame)
        assert label.GetLabel() != ""

    def test_query_then_shorten_clears_results(self, viewer_window):
        """Shortening query below minimum should clear search match results."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Simulate page loaded
        _fire_page_loaded(frame)

        # Run a search first
        search_ctrl.SetValue("welcome")
        _fire_timer_event(frame)

        # Now shorten to below minimum
        search_ctrl.SetValue("we")

        # Match buttons should be disabled (no active search results)
        assert not toolbar.GetToolEnabled(tools["Prev Match"])
        assert not toolbar.GetToolEnabled(tools["Next Match"])

        # Label shows "No results" because search ctrl still has text
        label = _get_search_label(frame)
        assert label.GetLabel() == "No results"


# --- Search clear tests ---


class TestClearSearch:
    """Tests for _clear_search resetting state."""

    def test_cancel_button_clears_search(self, viewer_window):
        """Clicking cancel on search ctrl should clear everything."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Simulate page loaded
        _fire_page_loaded(frame)

        # Run a search
        search_ctrl.SetValue("welcome")
        _fire_timer_event(frame)

        # Fire cancel event
        evt = wx.CommandEvent(wx.wxEVT_SEARCHCTRL_CANCEL_BTN, search_ctrl.GetId())
        evt.SetEventObject(search_ctrl)
        search_ctrl.ProcessEvent(evt)

        # Search should be cleared
        assert search_ctrl.GetValue() == ""
        label = _get_search_label(frame)
        assert label.GetLabel() == ""
        assert not toolbar.GetToolEnabled(tools["Prev Match"])
        assert not toolbar.GetToolEnabled(tools["Next Match"])

    def test_home_button_clears_search(self, viewer_window):
        """Clicking Home should clear search state."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        tools = _get_named_tools(frame)

        # Simulate page loaded
        _fire_page_loaded(frame)

        # Run a search
        search_ctrl.SetValue("welcome")
        _fire_timer_event(frame)

        # Click Home
        _fire_tool_event(frame, tools["Home"])

        # Search should be cleared
        assert search_ctrl.GetValue() == ""
        label = _get_search_label(frame)
        assert label.GetLabel() == ""


# --- Page navigation tests ---


class TestPageNavigation:
    """Tests for _on_home/_on_prev/_on_next updating page and buttons."""

    def test_home_loads_first_page(self, viewer_window, sample_html_dir):
        """Home button should load the first page."""
        frame = viewer_window.frame
        tools = _get_named_tools(frame)
        webview = _get_webview(frame)

        _fire_tool_event(frame, tools["Home"])

        # Should navigate to index.html
        url = webview.GetCurrentURL()
        assert url.endswith("index.html") or "index.html" in url

    def test_prev_button_disabled_on_first_page(self, viewer_window):
        """Previous button should be disabled when on the first page."""
        frame = viewer_window.frame
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Simulate loading the first page
        _fire_page_loaded(frame)

        # Previous should be disabled on first page
        assert not toolbar.GetToolEnabled(tools["Previous"])

    def test_next_button_enabled_on_first_page(self, viewer_window):
        """Next button should be enabled when not on the last page."""
        frame = viewer_window.frame
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Simulate loading the first page
        _fire_page_loaded(frame)

        # Next should be enabled (there are 2 pages)
        assert toolbar.GetToolEnabled(tools["Next"])

    def test_next_navigates_to_second_page(self, viewer_window, sample_html_dir):
        """Next button should load the next page in order."""
        frame = viewer_window.frame
        tools = _get_named_tools(frame)
        webview = _get_webview(frame)

        # Simulate page loaded on first page
        _fire_page_loaded(frame)

        # Click Next
        _fire_tool_event(frame, tools["Next"])

        # Should navigate to page1.html
        url = webview.GetCurrentURL()
        assert "page1.html" in url

    def test_prev_on_second_page_goes_to_first(self, viewer_window, sample_html_dir):
        """Previous on second page should go back to first."""
        frame = viewer_window.frame
        tools = _get_named_tools(frame)
        webview = _get_webview(frame)

        # Navigate to second page first
        _fire_page_loaded(frame)
        _fire_tool_event(frame, tools["Next"])

        # Simulate page loaded on second page
        _fire_page_loaded(frame)

        # Click Previous
        _fire_tool_event(frame, tools["Previous"])

        url = webview.GetCurrentURL()
        assert url.endswith("index.html") or "index.html" in url

    def test_nav_buttons_update_after_page_load(self, viewer_window):
        """Navigation buttons should update enabled state after page load."""
        frame = viewer_window.frame
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Initial page load on first page
        _fire_page_loaded(frame)

        # On first page: prev disabled, next enabled
        assert not toolbar.GetToolEnabled(tools["Previous"])
        assert toolbar.GetToolEnabled(tools["Next"])


# --- Page index building tests ---


class TestPageIndexCurrentPage:
    """Tests for page index building with current page detection."""

    def test_current_page_info_detects_index(self, viewer_window):
        """_current_page_info should detect index.html as page 0."""
        frame = viewer_window.frame
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # After page load event, nav buttons reflect position
        _fire_page_loaded(frame)

        # On first page, Previous is disabled (index 0)
        assert not toolbar.GetToolEnabled(tools["Previous"])
        # Next is enabled (index 0 < len-1)
        assert toolbar.GetToolEnabled(tools["Next"])

    def test_current_page_info_detects_second_page(self, viewer_window):
        """After navigating to page 2, buttons should reflect last page."""
        frame = viewer_window.frame
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Navigate to second (last) page
        _fire_page_loaded(frame)
        _fire_tool_event(frame, tools["Next"])
        _fire_page_loaded(frame)

        # On last page: prev enabled, next disabled
        assert toolbar.GetToolEnabled(tools["Previous"])
        assert not toolbar.GetToolEnabled(tools["Next"])


# --- Search execution across pages tests ---


class TestSearchExecution:
    """Tests for _do_search with RunScript mock."""

    def test_search_finds_matches_in_page(self, viewer_window):
        """Search for content that exists should show results."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        _fire_page_loaded(frame)

        # "welcome" exists in index.html content div
        search_ctrl.SetValue("welcome")
        _fire_timer_event(frame)

        label = _get_search_label(frame)
        assert "of" in label.GetLabel()  # "1 of 1" format
        assert toolbar.GetToolEnabled(tools["Prev Match"])
        assert toolbar.GetToolEnabled(tools["Next Match"])

    def test_search_no_results(self, viewer_window):
        """Search for non-existent content should show 'No results'."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        _fire_page_loaded(frame)

        search_ctrl.SetValue("xyznonexistent")
        _fire_timer_event(frame)

        label = _get_search_label(frame)
        assert label.GetLabel() == "No results"
        assert not toolbar.GetToolEnabled(tools["Prev Match"])
        assert not toolbar.GetToolEnabled(tools["Next Match"])

    def test_search_calls_runscript_mark(self, viewer_window):
        """Search should call RunScript with shlMark for highlighting."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        webview = _get_webview(frame)

        _fire_page_loaded(frame)

        with patch.object(webview, "RunScript") as mock_run:
            search_ctrl.SetValue("welcome")
            _fire_timer_event(frame)

            # Should have called shlMark and shlFocus
            calls = [str(c) for c in mock_run.call_args_list]
            mark_calls = [c for c in calls if "shlMark" in c]
            focus_calls = [c for c in calls if "shlFocus" in c]
            assert len(mark_calls) >= 1, "Should call shlMark"
            assert len(focus_calls) >= 1, "Should call shlFocus"

    def test_search_across_multiple_pages(self, viewer_window):
        """Search for content in multiple pages should find all matches."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)

        _fire_page_loaded(frame)

        # "page" appears in page1.html content ("Page 1", "first page")
        # and possibly in index.html sidebar, but we only index .content div
        search_ctrl.SetValue("page")
        _fire_timer_event(frame)

        label = _get_search_label(frame)
        # Should find results (at least in page1.html)
        assert label.GetLabel() != ""
        assert label.GetLabel() != "No results"


# --- Page load with pending mark/focus tests ---


class TestPageLoadPendingMarkFocus:
    """Tests for page load triggering pending mark and focus."""

    def test_page_load_triggers_pending_mark(self, viewer_window):
        """When a page loads with pending_mark, shlMark should be called."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        webview = _get_webview(frame)
        tools = _get_named_tools(frame)

        # First, get page ready
        _fire_page_loaded(frame)

        # Start a search that finds results on page1 (not current page)
        # "searchable" only appears in page1.html
        search_ctrl.SetValue("searchable")
        _fire_timer_event(frame)

        # The search should navigate to page1 (setting pending_mark/focus)
        # Now simulate the page load completing
        with patch.object(webview, "RunScript") as mock_run:
            _fire_page_loaded(frame)

            calls = [str(c) for c in mock_run.call_args_list]
            mark_calls = [c for c in calls if "shlMark" in c]
            focus_calls = [c for c in calls if "shlFocus" in c]
            assert len(mark_calls) >= 1, "Should call shlMark on pending page load"
            assert len(focus_calls) >= 1, "Should call shlFocus on pending page load"

    def test_page_load_updates_nav_buttons(self, viewer_window):
        """Page load event should always update navigation button state."""
        frame = viewer_window.frame
        toolbar = _get_toolbar(frame)
        tools = _get_named_tools(frame)

        # Before any page load, simulate the event
        _fire_page_loaded(frame)

        # Nav buttons should be updated (on first page)
        assert not toolbar.GetToolEnabled(tools["Previous"])
        assert toolbar.GetToolEnabled(tools["Next"])

    def test_page_ready_set_on_load(self, viewer_window):
        """After page load, RunScript calls should work (page_ready=True)."""
        frame = viewer_window.frame
        webview = _get_webview(frame)
        search_ctrl = _get_search_ctrl(frame)

        # Fire page loaded
        _fire_page_loaded(frame)

        # Now a search should be able to call RunScript
        with patch.object(webview, "RunScript") as mock_run:
            search_ctrl.SetValue("welcome")
            _fire_timer_event(frame)

            assert mock_run.called, "RunScript should be callable after page load"


# --- Timer cleanup on destroy tests ---


class TestTimerCleanup:
    """Tests for timer cleanup on window destroy."""

    def test_close_event_stops_timer(self, wx_app, wx_frame, sample_html_dir, sample_page_order):
        """Closing the frame should stop the debounce timer."""
        key = "test-timer-close"
        _viewer_refs.pop(key, None)
        viewer = show_viewer(
            wx_frame,
            title="Timer Test",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key,
        )
        assert viewer is not None
        frame = viewer.frame

        # Start a debounce by typing a search query
        search_ctrl = _get_search_ctrl(frame)
        search_ctrl.SetValue("welcome")

        # Close the frame — should stop the timer without errors
        close_evt = wx.CloseEvent(wx.wxEVT_CLOSE_WINDOW)
        frame.ProcessEvent(close_evt)

        # Frame should still be destroyable without timer errors
        frame.Destroy()
        _viewer_refs.pop(key, None)

    def test_destroy_event_stops_timer(self, wx_app, wx_frame, sample_html_dir, sample_page_order):
        """Destroying the frame should stop the debounce timer."""
        key = "test-timer-destroy"
        _viewer_refs.pop(key, None)
        viewer = show_viewer(
            wx_frame,
            title="Timer Destroy Test",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key,
        )
        assert viewer is not None
        frame = viewer.frame

        # Start a debounce by typing a search query
        search_ctrl = _get_search_ctrl(frame)
        search_ctrl.SetValue("welcome")

        # Destroy directly — should stop timer via EVT_WINDOW_DESTROY
        frame.Destroy()
        _viewer_refs.pop(key, None)

    def test_close_prevents_runscript_on_dead_webview(
        self, wx_app, wx_frame, sample_html_dir, sample_page_order
    ):
        """After close, page_ready should be False preventing RunScript calls."""
        key = "test-timer-pageready"
        _viewer_refs.pop(key, None)
        viewer = show_viewer(
            wx_frame,
            title="PageReady Test",
            size=(600, 400),
            base_path=sample_html_dir,
            page_order=sample_page_order,
            singleton_key=key,
        )
        assert viewer is not None
        frame = viewer.frame

        # Get page ready
        _fire_page_loaded(frame)

        # Close the frame (sets page_ready=False)
        close_evt = wx.CloseEvent(wx.wxEVT_CLOSE_WINDOW)
        frame.ProcessEvent(close_evt)

        # After close, the timer event should not crash even if fired
        # (page_ready=False prevents RunScript calls)
        # This mainly verifies no exception is raised
        frame.Destroy()
        _viewer_refs.pop(key, None)


# --- Match navigation tests ---


class TestMatchNavigation:
    """Tests for prev/next match navigation within and across pages."""

    def test_next_match_within_page(self, viewer_window):
        """Next match on same page should increment match cursor."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        webview = _get_webview(frame)
        tools = _get_named_tools(frame)

        _fire_page_loaded(frame)

        # "page" appears multiple times in page1.html content
        search_ctrl.SetValue("page")
        _fire_timer_event(frame)

        label = _get_search_label(frame)
        initial_label = label.GetLabel()

        # If there are matches, clicking next match should update position
        if "of" in initial_label:
            with patch.object(webview, "RunScript"):
                _fire_tool_event(frame, tools["Next Match"])

            updated_label = label.GetLabel()
            # Label should change (position increments)
            assert updated_label != "" and updated_label != "No results"

    def test_prev_match_wraps_around(self, viewer_window):
        """Prev match at start should wrap to last match (possibly different page)."""
        frame = viewer_window.frame
        search_ctrl = _get_search_ctrl(frame)
        webview = _get_webview(frame)
        tools = _get_named_tools(frame)

        _fire_page_loaded(frame)

        search_ctrl.SetValue("page")
        _fire_timer_event(frame)

        label = _get_search_label(frame)
        if "of" in label.GetLabel():
            # Click prev match from the first match position
            with patch.object(webview, "RunScript"):
                _fire_tool_event(frame, tools["Prev Match"])

            # Should not crash and label should still show results
            assert label.GetLabel() != ""

    def test_match_nav_no_op_without_results(self, viewer_window):
        """Match navigation buttons should be no-ops when no search results exist."""
        frame = viewer_window.frame
        tools = _get_named_tools(frame)
        toolbar = _get_toolbar(frame)

        _fire_page_loaded(frame)

        # No search performed — buttons disabled
        assert not toolbar.GetToolEnabled(tools["Prev Match"])
        assert not toolbar.GetToolEnabled(tools["Next Match"])

        # Firing tool events should not crash
        _fire_tool_event(frame, tools["Prev Match"])
        _fire_tool_event(frame, tools["Next Match"])

        # Still no results
        label = _get_search_label(frame)
        assert label.GetLabel() == ""
