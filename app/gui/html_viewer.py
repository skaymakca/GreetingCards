"""Shared HTML viewer — WebView window with toolbar, sidebar navigation, and search."""

import json
import weakref
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

import wx

from app.gui.icons import load_sf_symbol
from app.gui.styles import Color

# Singleton weakrefs keyed by viewer type
_viewer_refs: dict[str, weakref.ref] = {}

_TOOL_BITMAP_SIZE = wx.Size(24, 24)
_LABEL_WIDTH = 80
_SEARCH_MIN_WIDTH = 150


def _toolbar_icon(name: str) -> wx.Bitmap:
    """Load an SF Symbol sized for the HTML viewer toolbar (regular weight)."""
    return load_sf_symbol(name, point_size=16, weight=0.0) or wx.NullBitmap


_TOOL_WIDTH_EST = 36
_TOOLBAR_MARGIN = 24
_NUM_TOOLS = 5

_MIN_SEARCH_LEN = 3
_DEBOUNCE_MS = 200


class _PageMatch(NamedTuple):
    """A page that matched a search query."""

    page: str
    match_count: int


class _TextExtractor(HTMLParser):
    """Extract visible text from the .content div only.

    Ignores everything outside <div class="content">, plus script/style.
    """

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._in_content = False
        self._content_depth = 0  # nested div depth inside .content
        self._skip_depth = 0  # nested script/style depth

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._in_content and tag in ("script", "style"):
            self._skip_depth += 1
            return
        if tag == "div":
            if not self._in_content:
                classes = (dict(attrs).get("class") or "").split()
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


def _build_page_index(base_path: Path, page_order: list[str]) -> dict[str, str]:
    """Read all pages and return rel-path -> lowercase plain text."""
    index: dict[str, str] = {}
    for page in page_order:
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


class HTMLViewerWindow:
    """WebView-based HTML viewer with toolbar navigation and cross-page search."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        title: str,
        base_path: Path,
        page_order: list[str],
        size: tuple[int, int] = (800, 600),
        search_hint: str = "Search",
    ) -> None:
        import wx.html2

        self._page_order = page_order
        self._base_path = base_path

        frame = wx.Frame(parent, title=title, size=size, style=wx.DEFAULT_FRAME_STYLE)
        self._frame = frame

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Build text index for search
        page_index = _build_page_index(base_path, page_order)

        # Toolbar
        toolbar = wx.ToolBar(frame, style=wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
        toolbar.SetToolBitmapSize(_TOOL_BITMAP_SIZE)

        home_bmp = _toolbar_icon("house")
        home_id = toolbar.AddTool(wx.ID_ANY, "Home", home_bmp, shortHelp="Home").GetId()

        prev_bmp = _toolbar_icon("chevron.left")
        prev_id = toolbar.AddTool(wx.ID_ANY, "Previous", prev_bmp, shortHelp="Previous page").GetId()

        next_bmp = _toolbar_icon("chevron.right")
        next_id = toolbar.AddTool(wx.ID_ANY, "Next", next_bmp, shortHelp="Next page").GetId()

        # Search controls (right side)
        toolbar.AddStretchableSpace()

        search_label = wx.StaticText(
            toolbar, label="", size=(_LABEL_WIDTH, -1), style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE
        )
        search_label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        toolbar.AddControl(search_label)

        search_ctrl = wx.SearchCtrl(toolbar, size=(_SEARCH_MIN_WIDTH, -1))
        search_ctrl.SetDescriptiveText(search_hint)
        search_ctrl.ShowCancelButton(True)
        toolbar.AddControl(search_ctrl)

        prev_match_bmp = _toolbar_icon("chevron.up")
        prev_match_id = toolbar.AddTool(wx.ID_ANY, "Prev Match", prev_match_bmp, shortHelp="Previous match").GetId()

        next_match_bmp = _toolbar_icon("chevron.down")
        next_match_id = toolbar.AddTool(wx.ID_ANY, "Next Match", next_match_bmp, shortHelp="Next match").GetId()

        toolbar.EnableTool(prev_id, False)
        toolbar.EnableTool(prev_match_id, False)
        toolbar.EnableTool(next_match_id, False)
        toolbar.Realize()
        sizer.Add(toolbar, 0, wx.EXPAND)

        # Store toolbar references for refresh_colors()
        self._toolbar = toolbar
        self._tool_icons: list[tuple[int, str]] = [
            (home_id, "house"),
            (prev_id, "chevron.left"),
            (next_id, "chevron.right"),
            (prev_match_id, "chevron.up"),
            (next_match_id, "chevron.down"),
        ]

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

        # #ddd line to cover the native dark toolbar border (overlaps it by 1px)
        tb_line = wx.Panel(frame, size=(-1, 1))
        tb_line.SetBackgroundColour(Color.BORDER)
        sizer.Add(tb_line, 0, wx.EXPAND | wx.TOP, -1)
        self._tb_line = tb_line

        # WebView — HTML pages have built-in CSS sidebar
        url = (base_path / page_order[0]).as_uri()
        webview = wx.html2.WebView.New(frame, style=wx.BORDER_NONE)
        webview.LoadURL(url)
        sizer.Add(webview, 1, wx.EXPAND)

        frame.SetSizer(sizer)
        frame.CenterOnParent()
        frame.Show()

        # --- Search state ---
        search_pages: list[_PageMatch] = []
        page_cursor = 0
        match_cursor = 0
        page_ready = False  # True after first EVT_WEBVIEW_LOADED
        pending_mark = False  # Need full _mark_all after page load
        pending_focus = False  # Need _focus_match after page load
        last_query = ""  # Avoid redundant re-marking
        debounce_timer = wx.Timer(frame)

        # --- Navigation helpers ---
        def _current_page_info() -> tuple[int, str]:
            current_url = webview.GetCurrentURL()
            # Strip anchor fragment for matching
            base_url = current_url.split("#")[0]
            for i, page in enumerate(page_order):
                if base_url.endswith(page):
                    return i, page
            return -1, ""

        def _update_nav_buttons() -> None:
            idx, _ = _current_page_info()
            toolbar.EnableTool(prev_id, idx > 0)
            toolbar.EnableTool(next_id, 0 <= idx < len(page_order) - 1)

        def _total_matches() -> int:
            return sum(m.match_count for m in search_pages)

        def _global_position() -> int:
            nonlocal page_cursor, match_cursor
            return sum(m.match_count for m in search_pages[:page_cursor]) + match_cursor + 1

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

        def _mark_all() -> None:
            nonlocal last_query
            if not page_ready:
                return
            query = search_ctrl.GetValue()
            last_query = query
            webview.RunScript(f"shlMark({json.dumps(query)})")

        def _focus_match(idx: int) -> None:
            if not page_ready:
                return
            webview.RunScript(f"shlFocus({idx})")

        def _clear_highlights() -> None:
            nonlocal last_query
            if not page_ready:
                return
            last_query = ""
            webview.RunScript("shlClear()")

        def _run_search(query: str) -> None:
            nonlocal page_cursor, match_cursor, pending_mark, pending_focus
            search_pages.clear()
            page_cursor = 0
            match_cursor = 0
            if not query or len(query) < _MIN_SEARCH_LEN:
                pending_mark = False
                pending_focus = False
                _clear_highlights()
                _update_search_ui()
                return
            q = query.lower()
            for page in page_order:
                count = _count_occurrences(page_index.get(page, ""), q)
                if count > 0:
                    search_pages.append(_PageMatch(page, count))
            _update_search_ui()
            if search_pages:
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
            nonlocal page_ready, page_cursor, match_cursor, pending_mark, pending_focus
            page_cursor = pg_idx
            match_cursor = mt_idx
            page = search_pages[pg_idx].page
            current_url = webview.GetCurrentURL()
            base_url = current_url.split("#")[0]
            if base_url.endswith(page):
                query = search_ctrl.GetValue()
                if query != last_query:
                    _mark_all()
                _focus_match(match_cursor)
                _update_search_ui()
            else:
                page_ready = False
                pending_mark = True
                pending_focus = True
                webview.LoadURL((base_path / page).as_uri())

        def _clear_search() -> None:
            nonlocal page_cursor, match_cursor, pending_mark, pending_focus
            debounce_timer.Stop()
            search_ctrl.ChangeValue("")
            search_pages.clear()
            page_cursor = 0
            match_cursor = 0
            pending_mark = False
            pending_focus = False
            _clear_highlights()
            _update_search_ui()

        # --- Event handlers ---
        def on_home(evt: wx.CommandEvent) -> None:
            _clear_search()
            webview.LoadURL((base_path / page_order[0]).as_uri())

        def on_prev(evt: wx.CommandEvent) -> None:
            _clear_search()
            idx, _ = _current_page_info()
            if idx > 0:
                webview.LoadURL((base_path / page_order[idx - 1]).as_uri())

        def on_next(evt: wx.CommandEvent) -> None:
            _clear_search()
            idx, _ = _current_page_info()
            if 0 <= idx < len(page_order) - 1:
                webview.LoadURL((base_path / page_order[idx + 1]).as_uri())

        def on_search_text(evt: wx.CommandEvent) -> None:
            query = search_ctrl.GetValue()
            if len(query) < _MIN_SEARCH_LEN:
                debounce_timer.Stop()
                _run_search("")
                return
            debounce_timer.Stop()
            debounce_timer.StartOnce(_DEBOUNCE_MS)

        def on_debounce_timer(evt: wx.TimerEvent) -> None:
            _run_search(search_ctrl.GetValue())

        def on_search_cancel(evt: wx.CommandEvent) -> None:
            _clear_search()

        def on_prev_match(evt: wx.CommandEvent) -> None:
            nonlocal match_cursor
            if not search_pages:
                return
            if match_cursor > 0:
                match_cursor -= 1
                _focus_match(match_cursor)
                _update_search_ui()
            else:
                prev_pg = (page_cursor - 1) % len(search_pages)
                _navigate_to_page(prev_pg, search_pages[prev_pg].match_count - 1)

        def on_next_match(evt: wx.CommandEvent) -> None:
            nonlocal match_cursor
            if not search_pages:
                return
            if match_cursor < search_pages[page_cursor].match_count - 1:
                match_cursor += 1
                _focus_match(match_cursor)
                _update_search_ui()
            else:
                next_pg = (page_cursor + 1) % len(search_pages)
                _navigate_to_page(next_pg, 0)

        def on_navigating(evt) -> None:
            url = evt.GetURL()
            if url.startswith(("http://", "https://")):
                evt.Veto()
                wx.LaunchDefaultBrowser(url)
            else:
                evt.Skip()

        def on_page_loaded(evt) -> None:
            nonlocal page_ready, pending_mark, pending_focus
            page_ready = True
            _update_nav_buttons()
            if pending_mark:
                pending_mark = False
                _mark_all()
            if pending_focus:
                pending_focus = False
                _focus_match(match_cursor)
                _update_search_ui()
            evt.Skip()

        frame.Bind(wx.EVT_TOOL, on_home, id=home_id)
        frame.Bind(wx.EVT_TOOL, on_prev, id=prev_id)
        frame.Bind(wx.EVT_TOOL, on_next, id=next_id)
        frame.Bind(wx.EVT_TOOL, on_prev_match, id=prev_match_id)
        frame.Bind(wx.EVT_TOOL, on_next_match, id=next_match_id)
        search_ctrl.Bind(wx.EVT_TEXT, on_search_text)
        search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, on_search_cancel)
        frame.Bind(wx.EVT_TIMER, on_debounce_timer, debounce_timer)
        webview.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING, on_navigating)
        webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, on_page_loaded)

        # Cmd+F accelerator to focus search ctrl
        accel_id = wx.NewIdRef()
        frame.Bind(wx.EVT_MENU, lambda evt: search_ctrl.SetFocus(), id=accel_id)
        frame.SetAcceleratorTable(wx.AcceleratorTable([(wx.ACCEL_CMD, ord("F"), accel_id)]))

        # Expose refresh_colors on the frame so appearance observers can find it
        frame.refresh_colors = self.refresh_colors  # type: ignore[attr-defined]

        # Stop debounce timer on close/destroy to prevent RunScript on a dead
        # WebView.  EVT_CLOSE covers user close; EVT_WINDOW_DESTROY covers
        # programmatic Destroy() calls (e.g. test teardown).
        def _stop_timer(evt: wx.Event) -> None:
            nonlocal page_ready
            debounce_timer.Stop()
            page_ready = False
            evt.Skip()

        frame.Bind(wx.EVT_CLOSE, _stop_timer)
        frame.Bind(wx.EVT_WINDOW_DESTROY, _stop_timer)

        # Initial search ctrl sizing
        wx.CallAfter(_resize_search_ctrl)

    def refresh_colors(self) -> None:
        """Update toolbar icons and border for current appearance mode."""
        from app.gui.icons import clear_cache

        clear_cache()
        for tool_id, symbol_name in self._tool_icons:
            bmp = _toolbar_icon(symbol_name)
            self._toolbar.SetToolNormalBitmap(tool_id, wx.BitmapBundle(bmp))
        self._toolbar.Realize()
        self._tb_line.SetBackgroundColour(Color.BORDER)
        self._frame.Refresh()

    @property
    def frame(self) -> wx.Frame:
        return self._frame


def show_viewer(
    parent: wx.Window,
    *,
    title: str,
    base_path: Path,
    page_order: list[str],
    singleton_key: str,
    size: tuple[int, int] = (800, 600),
    search_hint: str = "Search",
) -> HTMLViewerWindow | None:
    """Show an HTML viewer window, reusing an existing one if still alive."""
    ref = _viewer_refs.get(singleton_key)
    if ref is not None:
        frame = ref()
        if frame is not None and not frame.IsBeingDeleted():
            frame.Raise()
            return None

    viewer = HTMLViewerWindow(
        parent, title=title, size=size, base_path=base_path, page_order=page_order, search_hint=search_hint
    )
    _viewer_refs[singleton_key] = weakref.ref(viewer.frame)
    return viewer
