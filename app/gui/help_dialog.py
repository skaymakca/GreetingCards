"""Help system — WebView-based help viewer."""

import json
import sys
import weakref
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

import wx

from app.core.paths import is_bundled
from app.gui.icons import load_sf_symbol

# Singleton weakref for help window
_help_window_ref = None

_WINDOW_TITLE = "Greeting Cards Help"
_WINDOW_SIZE = (800, 600)
_TOOL_BITMAP_SIZE = wx.Size(24, 24)
_ICON_KW = dict(point_size=16, weight=0.0)  # Regular weight to match main toolbar
_LABEL_WIDTH = 80
_SEARCH_MIN_WIDTH = 150
_TOOL_WIDTH_EST = 36
_TOOLBAR_MARGIN = 24
_NUM_TOOLS = 5

_HELP_REL_PATH = Path("help")

# Page order for Prev/Next navigation
_PAGE_ORDER = [
    "index.html",
    "pages/getting-started.html",
    "pages/toolbar.html",
    "pages/card-list.html",
    "pages/preview.html",
    "pages/shortcuts.html",
    "pages/tips.html",
]


class _PageMatch(NamedTuple):
    """A help page that matched a search query."""
    page: str
    count: int


class _TextExtractor(HTMLParser):
    """Extract visible text from the .content div only.

    Ignores everything outside <div class="content">, plus script/style.
    """

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._in_content = False
        self._content_depth = 0   # nested div depth inside .content
        self._skip_depth = 0      # nested script/style depth

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._in_content and tag in ("script", "style"):
            self._skip_depth += 1
            return
        if tag == "div":
            if not self._in_content:
                classes = dict(attrs).get("class", "").split()
                if "content" in classes:
                    self._in_content = True
                    self._content_depth = 1
            else:
                self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth > 0 and tag in ("script", "style"):
            self._skip_depth -= 1
            return
        if self._in_content and tag == "div":
            self._content_depth -= 1
            if self._content_depth == 0:
                self._in_content = False

    def handle_data(self, data: str) -> None:
        if self._in_content and self._skip_depth == 0:
            self._pieces.append(data)

    def get_text(self) -> str:
        return " ".join(self._pieces)


def _build_page_index(base_path: Path) -> dict[str, str]:
    """Read all help pages and return rel-path -> lowercase plain text."""
    index: dict[str, str] = {}
    for page in _PAGE_ORDER:
        path = base_path / page
        if path.exists():
            extractor = _TextExtractor()
            extractor.feed(path.read_text(encoding="utf-8"))
            index[page] = extractor.get_text().lower()
        else:
            index[page] = ""
    return index


def _count_occurrences(text: str, query_lower: str) -> int:
    """Count non-overlapping case-insensitive occurrences."""
    if not query_lower:
        return 0
    count = 0
    start = 0
    while (idx := text.find(query_lower, start)) != -1:
        count += 1
        start = idx + len(query_lower)
    return count


# JS: highlight all case-insensitive matches inside .content only.
# Params: %s = JSON-encoded query, %d = 0-based index of match to focus.
# Returns the total match count on this page.
_HIGHLIGHT_JS = """(function() {
    if (!document.getElementById('_shl-css')) {
        var s = document.createElement('style');
        s.id = '_shl-css';
        s.textContent = 'mark._shl{background:#CCDEFF;border-radius:2px;padding:0 1px}'
            + 'mark._shl._cur{background:#007AFF;color:#fff;border-radius:2px;padding:0 1px}';
        document.head.appendChild(s);
    }
    var content = document.querySelector('.content');
    if (!content) return 0;
    var marks = content.querySelectorAll('mark._shl');
    for (var j = 0; j < marks.length; j++) {
        var m = marks[j], p = m.parentNode;
        while (m.firstChild) p.insertBefore(m.firstChild, m);
        p.removeChild(m);
    }
    content.normalize();
    var query = %s;
    var focusIdx = %d;
    if (!query) return 0;
    var lq = query.toLowerCase();
    var qLen = query.length;
    var walker = document.createTreeWalker(
        content, NodeFilter.SHOW_TEXT, null, false);
    var allMatches = [];
    while (walker.nextNode()) {
        var node = walker.currentNode;
        var lt = node.textContent.toLowerCase();
        var idx = 0;
        while ((idx = lt.indexOf(lq, idx)) !== -1) {
            allMatches.push({node: node, offset: idx});
            idx += qLen;
        }
    }
    for (var i = allMatches.length - 1; i >= 0; i--) {
        var match = allMatches[i];
        var range = document.createRange();
        range.setStart(match.node, match.offset);
        range.setEnd(match.node, match.offset + qLen);
        var mark = document.createElement('mark');
        mark.className = (i === focusIdx) ? '_shl _cur' : '_shl';
        range.surroundContents(mark);
    }
    var cur = document.querySelector('mark._cur');
    if (cur) cur.scrollIntoView({block: 'center'});
    return allMatches.length;
})()"""


def show_help(parent: wx.Window) -> None:
    """Open help in a WebView window."""
    global _help_window_ref

    # Reuse existing window if still alive
    if _help_window_ref is not None:
        window = _help_window_ref()
        if window is not None and not window.IsBeingDeleted():
            window.Raise()
            return

    import wx.html2

    frame = wx.Frame(parent, title=_WINDOW_TITLE, size=_WINDOW_SIZE,
                     style=wx.DEFAULT_FRAME_STYLE)

    sizer = wx.BoxSizer(wx.VERTICAL)

    # Toolbar with Home / Prev / Next
    base_path = _get_help_base_path()
    page_index = _build_page_index(base_path)
    toolbar = wx.ToolBar(frame, style=wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
    toolbar.SetToolBitmapSize(_TOOL_BITMAP_SIZE)

    home_bmp = load_sf_symbol("house", **_ICON_KW) or wx.NullBitmap
    home_id = toolbar.AddTool(wx.ID_ANY, "Home", home_bmp,
                              shortHelp="Home").GetId()

    prev_bmp = load_sf_symbol("chevron.left", **_ICON_KW) or wx.NullBitmap
    prev_id = toolbar.AddTool(wx.ID_ANY, "Previous", prev_bmp,
                              shortHelp="Previous page").GetId()

    next_bmp = load_sf_symbol("chevron.right", **_ICON_KW) or wx.NullBitmap
    next_id = toolbar.AddTool(wx.ID_ANY, "Next", next_bmp,
                              shortHelp="Next page").GetId()

    # Search controls (right side)
    toolbar.AddStretchableSpace()

    search_label = wx.StaticText(toolbar, label="", size=(_LABEL_WIDTH, -1),
                                 style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE)
    search_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
    toolbar.AddControl(search_label)

    search_ctrl = wx.SearchCtrl(toolbar, size=(_SEARCH_MIN_WIDTH, -1))
    search_ctrl.SetDescriptiveText("Search help...")
    search_ctrl.ShowCancelButton(True)
    toolbar.AddControl(search_ctrl)

    prev_match_bmp = load_sf_symbol("chevron.up", **_ICON_KW) or wx.NullBitmap
    prev_match_id = toolbar.AddTool(wx.ID_ANY, "Prev Match", prev_match_bmp,
                                    shortHelp="Previous match").GetId()

    next_match_bmp = load_sf_symbol("chevron.down", **_ICON_KW) or wx.NullBitmap
    next_match_id = toolbar.AddTool(wx.ID_ANY, "Next Match", next_match_bmp,
                                    shortHelp="Next match").GetId()

    toolbar.EnableTool(prev_id, False)
    toolbar.EnableTool(prev_match_id, False)
    toolbar.EnableTool(next_match_id, False)
    toolbar.Realize()
    sizer.Add(toolbar, 0, wx.EXPAND)

    # Dynamically resize search ctrl to fill available toolbar space
    def _resize_search_ctrl(evt: wx.SizeEvent | None = None) -> None:
        if evt:
            evt.Skip()
        tb_w = toolbar.GetSize().width
        fixed_w = _NUM_TOOLS * _TOOL_WIDTH_EST + _LABEL_WIDTH + _TOOLBAR_MARGIN
        new_w = max(_SEARCH_MIN_WIDTH, tb_w - fixed_w)
        if search_ctrl.GetSize().width != new_w:
            search_ctrl.SetMinSize(wx.Size(new_w, -1))
            toolbar.Realize()

    frame.Bind(wx.EVT_SIZE, _resize_search_ctrl)

    # WebView — HTML pages have built-in CSS sidebar
    url = _get_help_index_path().as_uri()
    webview = wx.html2.WebView.New(frame)
    webview.LoadURL(url)
    sizer.Add(webview, 1, wx.EXPAND)

    frame.SetSizer(sizer)
    frame.CenterOnParent()
    frame.Show()

    _help_window_ref = weakref.ref(frame)

    # --- Search state ---
    search_pages: list[_PageMatch] = []
    page_cursor = 0
    match_cursor = 0
    pending_highlight = False

    # --- Navigation helpers ---
    def _current_page_info() -> tuple[int, str]:
        """Return (index, rel_path) of current page, or (-1, '')."""
        current_url = webview.GetCurrentURL()
        for i, page in enumerate(_PAGE_ORDER):
            if current_url.endswith(page):
                return i, page
        return -1, ""

    def _update_nav_buttons() -> None:
        idx, _ = _current_page_info()
        toolbar.EnableTool(prev_id, idx > 0)
        toolbar.EnableTool(next_id, 0 <= idx < len(_PAGE_ORDER) - 1)

    def _total_matches() -> int:
        return sum(m.count for m in search_pages)

    def _global_position() -> int:
        nonlocal page_cursor, match_cursor
        return sum(m.count for m in search_pages[:page_cursor]) + match_cursor + 1

    def _update_search_ui() -> None:
        total = _total_matches()
        has_results = total > 0
        toolbar.EnableTool(prev_match_id, has_results)
        toolbar.EnableTool(next_match_id, has_results)
        if has_results:
            search_label.SetLabel(f"{_global_position()} of {total}")
        elif search_ctrl.GetValue():
            search_label.SetLabel("No results")
        else:
            search_label.SetLabel("")

    def _highlight_current() -> None:
        """Run JS to highlight matches on current page's .content only."""
        query = search_ctrl.GetValue()
        js = _HIGHLIGHT_JS % (json.dumps(query), match_cursor)
        webview.RunScript(js)

    def _clear_highlights() -> None:
        webview.RunScript(_HIGHLIGHT_JS % (json.dumps(""), 0))

    def _run_search(query: str) -> None:
        nonlocal page_cursor, match_cursor, pending_highlight
        search_pages.clear()
        page_cursor = 0
        match_cursor = 0
        if not query:
            pending_highlight = False
            _clear_highlights()
            _update_search_ui()
            return
        q = query.lower()
        for page in _PAGE_ORDER:
            count = _count_occurrences(page_index.get(page, ""), q)
            if count > 0:
                search_pages.append(_PageMatch(page, count))
        _update_search_ui()
        if search_pages:
            # Stay on current page if it has results
            _, current = _current_page_info()
            start_idx = 0
            for i, m in enumerate(search_pages):
                if m.page == current:
                    start_idx = i
                    break
            _navigate_to_page(start_idx, 0)
        else:
            _clear_highlights()

    def _navigate_to_page(pg_idx: int, mt_idx: int) -> None:
        nonlocal page_cursor, match_cursor, pending_highlight
        page_cursor = pg_idx
        match_cursor = mt_idx
        page = search_pages[pg_idx].page
        current_url = webview.GetCurrentURL()
        if current_url.endswith(page):
            _highlight_current()
            _update_search_ui()
        else:
            pending_highlight = True
            webview.LoadURL((base_path / page).as_uri())

    def _clear_search() -> None:
        """Reset search state and clear highlights."""
        nonlocal page_cursor, match_cursor, pending_highlight
        search_ctrl.ChangeValue("")  # ChangeValue doesn't fire EVT_TEXT
        search_pages.clear()
        page_cursor = 0
        match_cursor = 0
        pending_highlight = False
        _clear_highlights()
        _update_search_ui()

    # --- Event handlers ---
    def on_home(evt: wx.CommandEvent) -> None:
        _clear_search()
        webview.LoadURL((base_path / _PAGE_ORDER[0]).as_uri())

    def on_prev(evt: wx.CommandEvent) -> None:
        _clear_search()
        idx, _ = _current_page_info()
        if idx > 0:
            webview.LoadURL((base_path / _PAGE_ORDER[idx - 1]).as_uri())

    def on_next(evt: wx.CommandEvent) -> None:
        _clear_search()
        idx, _ = _current_page_info()
        if 0 <= idx < len(_PAGE_ORDER) - 1:
            webview.LoadURL((base_path / _PAGE_ORDER[idx + 1]).as_uri())

    def on_search_text(evt: wx.CommandEvent) -> None:
        _run_search(search_ctrl.GetValue())

    def on_search_cancel(evt: wx.CommandEvent) -> None:
        _clear_search()

    def on_prev_match(evt: wx.CommandEvent) -> None:
        nonlocal match_cursor
        if not search_pages:
            return
        if match_cursor > 0:
            match_cursor -= 1
            _highlight_current()
            _update_search_ui()
        else:
            prev_pg = (page_cursor - 1) % len(search_pages)
            _navigate_to_page(prev_pg, search_pages[prev_pg].count - 1)

    def on_next_match(evt: wx.CommandEvent) -> None:
        nonlocal match_cursor
        if not search_pages:
            return
        if match_cursor < search_pages[page_cursor].count - 1:
            match_cursor += 1
            _highlight_current()
            _update_search_ui()
        else:
            next_pg = (page_cursor + 1) % len(search_pages)
            _navigate_to_page(next_pg, 0)

    def on_page_loaded(evt: wx.html2.WebViewEvent) -> None:
        nonlocal pending_highlight
        _update_nav_buttons()
        if pending_highlight:
            pending_highlight = False
            _highlight_current()
            _update_search_ui()
        evt.Skip()

    frame.Bind(wx.EVT_TOOL, on_home, id=home_id)
    frame.Bind(wx.EVT_TOOL, on_prev, id=prev_id)
    frame.Bind(wx.EVT_TOOL, on_next, id=next_id)
    frame.Bind(wx.EVT_TOOL, on_prev_match, id=prev_match_id)
    frame.Bind(wx.EVT_TOOL, on_next_match, id=next_match_id)
    search_ctrl.Bind(wx.EVT_TEXT, on_search_text)
    search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, on_search_cancel)
    webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, on_page_loaded)

    # Cmd+F accelerator to focus search ctrl
    accel_id = wx.NewIdRef()
    frame.Bind(wx.EVT_MENU, lambda evt: search_ctrl.SetFocus(), id=accel_id)
    frame.SetAcceleratorTable(
        wx.AcceleratorTable([(wx.ACCEL_CMD, ord("F"), accel_id)])
    )

    # Initial search ctrl sizing
    wx.CallAfter(_resize_search_ctrl)


def _get_help_base_path() -> Path:
    """Return path to help directory."""
    if is_bundled():
        return Path(sys._MEIPASS) / _HELP_REL_PATH
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / _HELP_REL_PATH


def _get_help_index_path() -> Path:
    """Return path to help index.html."""
    return _get_help_base_path() / "index.html"
