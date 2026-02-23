"""Tests for app.gui.help_dialog module (help system wrapper)."""

import wx
from unittest.mock import patch
from pathlib import Path

from app.gui.help_dialog import show_help
from app.gui.html_viewer import (
    _PageMatch, _build_page_index, _count_occurrences,
    _TextExtractor, _viewer_refs,
)
from app.core.help_builder import (
    get_page_order, _parse_frontmatter, _read_help_pages,
    _validate_numbering,
)
from app.core.paths import get_runtime_content_path


def _get_help_base_path() -> Path:
    """Helper to get the help base path for tests."""
    return get_runtime_content_path("html/help")

import pytest


# --- Shared fixtures ---

@pytest.fixture
def help_window(wx_app, wx_frame):
    """Open help window and yield it; destroy on teardown."""
    _viewer_refs.pop("help", None)
    show_help(wx_frame)
    ref = _viewer_refs.get("help")
    window = ref() if ref else None
    yield window
    if window and not window.IsBeingDeleted():
        window.Destroy()
    _viewer_refs.pop("help", None)


def _get_toolbar(window: wx.Frame) -> wx.ToolBar:
    """Return the toolbar from the help window."""
    return [c for c in window.GetChildren() if isinstance(c, wx.ToolBar)][0]


# --- Path tests ---

class TestHelpBasePath:
    """Tests for help base path resolution."""

    def test_returns_path_object(self):
        result = _get_help_base_path()
        assert isinstance(result, Path)

    def test_path_ends_with_help(self):
        result = _get_help_base_path()
        assert str(result).endswith("html/help")

    def test_path_exists_in_dev_mode(self):
        result = _get_help_base_path()
        assert result.exists(), f"Help base not found at {result}"

    def test_index_exists(self):
        result = _get_help_base_path() / "index.html"
        assert result.exists(), f"Help index not found at {result}"


# --- Content file tests ---

class TestHelpContentFiles:
    """Tests that all help content pages exist."""

    def test_all_pages_exist(self):
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        for rel_path in page_order:
            full_path = base / rel_path
            assert full_path.exists(), f"Missing help page: {full_path}"

    def test_pages_contain_sidebar(self):
        """All pages should include the CSS sidebar nav."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        for rel_path in page_order:
            content = (base / rel_path).read_text()
            assert 'class="sidebar"' in content, f"No sidebar in {rel_path}"
            assert 'class="content"' in content, f"No content div in {rel_path}"

    def test_each_page_marks_itself_active(self):
        """Each page should have exactly one 'active' link in the sidebar."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        for rel_path in page_order:
            content = (base / rel_path).read_text()
            assert content.count('class="active"') == 1, \
                f"Expected 1 active link in {rel_path}, found {content.count('class=\"active\"')}"

    def test_pages_reference_shared_css(self):
        """All pages should reference the shared viewer.css."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        for rel_path in page_order:
            content = (base / rel_path).read_text()
            assert "viewer.css" in content, f"No viewer.css reference in {rel_path}"

    def test_pages_include_search_js(self):
        """All pages should include the search.js script."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        for rel_path in page_order:
            content = (base / rel_path).read_text()
            assert "search.js" in content, f"No search.js reference in {rel_path}"


# --- Page order tests ---

class TestGetPageOrder:
    """Tests for get_page_order() — reads page_order.txt manifest."""

    def test_index_is_first(self):
        page_order = get_page_order(_get_help_base_path())
        assert page_order[0] == "index.html"

    def test_has_expected_page_count(self):
        page_order = get_page_order(_get_help_base_path())
        assert len(page_order) == 8

    def test_all_pages_are_html(self):
        page_order = get_page_order(_get_help_base_path())
        assert all(p.endswith(".html") for p in page_order)

    def test_order_matches_nav_order(self):
        """Page order should follow the numeric prefix in markdown filenames."""
        page_order = get_page_order(_get_help_base_path())
        expected = [
            "index.html",
            "pages/getting-started.html",
            "pages/toolbar.html",
            "pages/card-list.html",
            "pages/preview.html",
            "pages/shortcuts.html",
            "pages/ai-models.html",
            "pages/tips.html",
        ]
        assert page_order == expected


# --- Page index tests (using real help files) ---

class TestBuildPageIndex:
    """Tests for _build_page_index() against real help content."""

    def test_returns_all_pages(self):
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(base, page_order)
        for page in page_order:
            assert page in index

    def test_text_is_lowercase(self):
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(base, page_order)
        for page, text in index.items():
            assert text == text.lower(), f"Text for {page} is not lowercase"

    def test_text_strips_html_tags(self):
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(base, page_order)
        for page, text in index.items():
            assert "<" not in text, f"HTML tag found in {page}"
            assert ">" not in text, f"HTML tag found in {page}"

    def test_content_searchable(self):
        """Known words should be found on expected pages."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(base, page_order)
        assert "greeting cards help" in index["index.html"]

    def test_only_extracts_content_div(self):
        """Only text from .content div should appear; sidebar/title excluded."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(base, page_order)
        for page, text in index.items():
            assert "contents" not in text, \
                f"Sidebar heading 'contents' found in {page} index"

    def test_missing_file_returns_empty_string(self, tmp_path):
        """Gracefully handle missing files."""
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(tmp_path, page_order)
        for page in page_order:
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
        assert _count_occurrences("card card card", "card") == 3

    def test_non_overlapping(self):
        assert _count_occurrences("aaa", "aa") == 1

    def test_counts_on_real_index(self):
        """Verify counts against real help page index."""
        base = _get_help_base_path()
        page_order = get_page_order(_get_help_base_path())
        index = _build_page_index(base, page_order)
        assert _count_occurrences(index["index.html"], "greeting cards help") >= 1

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

class TestHelpWebViewWindow:
    """Tests for the WebView help window."""

    def test_window_creation(self, help_window):
        assert help_window is not None
        assert help_window.GetTitle() == "Greeting Cards Help"

    def test_singleton_reuse(self, help_window):
        """Second call should raise existing window, not create new one."""
        with patch.object(help_window, "Raise") as mock_raise, \
             patch.object(help_window, "IsBeingDeleted", return_value=False):
            show_help(help_window.GetParent())
            mock_raise.assert_called_once()

    def test_creates_new_after_close(self, wx_app, wx_frame):
        """After old window is destroyed, a new one should be created."""
        _viewer_refs.pop("help", None)
        show_help(wx_frame)
        ref = _viewer_refs.get("help")
        window = ref() if ref else None
        window.Destroy()
        _viewer_refs.pop("help", None)

        show_help(wx_frame)
        ref2 = _viewer_refs.get("help")
        second_window = ref2() if ref2 else None
        assert second_window is not None
        second_window.Destroy()
        _viewer_refs.pop("help", None)


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
        """Page order should list all expected help pages."""
        page_order = get_page_order(_get_help_base_path())
        assert page_order[0] == "index.html"
        assert len(page_order) == 8
        assert all(p.endswith(".html") for p in page_order)


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
        """SearchCtrl should have 'Search' placeholder."""
        toolbar = _get_toolbar(help_window)
        search_ctrl = [c for c in toolbar.GetChildren()
                       if isinstance(c, wx.SearchCtrl)][0]
        assert search_ctrl.GetDescriptiveText() == "Search"

    def test_match_buttons_disabled_initially(self, help_window):
        """Prev/Next Match buttons should start disabled."""
        toolbar = _get_toolbar(help_window)
        tools = []
        for i in range(toolbar.GetToolsCount()):
            tool = toolbar.GetToolByPos(i)
            if tool.GetId() != wx.ID_SEPARATOR:
                tools.append(tool)
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


# --- Help builder: frontmatter parsing tests ---

class TestParseFrontmatter:
    """Tests for _parse_frontmatter()."""

    def test_basic_frontmatter(self):
        text = "---\ntitle: Home\n---\n\n# Content"
        meta, body = _parse_frontmatter(text)
        assert meta == {"title": "Home"}
        assert body == "# Content"

    def test_no_frontmatter(self):
        text = "# Just content"
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == "# Just content"

    def test_unclosed_frontmatter(self):
        text = "---\ntitle: Oops\nNo closing"
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_empty_frontmatter(self):
        text = "---\n---\n\nBody."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == "Body."

    def test_multiple_keys(self):
        text = "---\ntitle: Test\nauthor: Me\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert meta == {"title": "Test", "author": "Me"}


# --- Help builder: filename numbering validation tests ---

class TestValidateNumbering:
    """Tests for _validate_numbering()."""

    def test_valid_sequence(self):
        _validate_numbering([1, 2, 3], ["1 - a.md", "2 - b.md", "3 - c.md"])

    def test_single_file(self):
        _validate_numbering([1], ["1 - index.md"])

    def test_empty(self):
        _validate_numbering([], [])

    def test_duplicate_numbers(self):
        with pytest.raises(ValueError, match="Duplicate.*2"):
            _validate_numbering(
                [1, 2, 2], ["1 - a.md", "2 - b.md", "2 - c.md"]
            )

    def test_gap_in_sequence(self):
        with pytest.raises(ValueError, match="Gap.*expected 2"):
            _validate_numbering([1, 3], ["1 - a.md", "3 - c.md"])

    def test_not_starting_at_one(self):
        with pytest.raises(ValueError, match="start at 1"):
            _validate_numbering([2, 3], ["2 - a.md", "3 - b.md"])

    def test_out_of_order_is_ok(self):
        """Files can be discovered in any order; only values matter."""
        _validate_numbering([3, 1, 2], ["3 - c.md", "1 - a.md", "2 - b.md"])


# --- Help builder: read_help_pages tests ---

class TestReadHelpPages:
    """Tests for _read_help_pages() with real content."""

    def test_reads_all_pages(self):
        content_dir = Path(__file__).resolve().parent.parent.parent / "content" / "html"
        pages = _read_help_pages(content_dir)
        assert len(pages) == 8

    def test_pages_sorted_by_order(self):
        content_dir = Path(__file__).resolve().parent.parent.parent / "content" / "html"
        pages = _read_help_pages(content_dir)
        assert pages[0].slug == "index"
        assert pages[-1].slug == "tips"

    def test_title_from_frontmatter(self):
        content_dir = Path(__file__).resolve().parent.parent.parent / "content" / "html"
        pages = _read_help_pages(content_dir)
        assert pages[0].title == "Home"

    def test_body_html_not_empty(self):
        content_dir = Path(__file__).resolve().parent.parent.parent / "content" / "html"
        pages = _read_help_pages(content_dir)
        for page in pages:
            assert page.body_html, f"Empty body for {page.slug}"

    def test_bad_filename_raises(self, tmp_path):
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "bad-name.md").write_text("---\ntitle: Bad\n---\nContent")
        with pytest.raises(ValueError, match="doesn't match"):
            _read_help_pages(tmp_path)

    def test_missing_number_raises(self, tmp_path):
        help_dir = tmp_path / "help"
        help_dir.mkdir()
        (help_dir / "1 - a.md").write_text("---\ntitle: A\n---\nA")
        (help_dir / "3 - c.md").write_text("---\ntitle: C\n---\nC")
        with pytest.raises(ValueError, match="Gap"):
            _read_help_pages(tmp_path)
