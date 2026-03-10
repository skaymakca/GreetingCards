# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Shared HTML viewer — WebView window with toolbar, sidebar navigation, and search."""

import json
import weakref
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

import wx
import wx.html2

from app.gui.icons import load_menu_icon, load_sf_symbol
from app.gui.styles import Color, Layout

# Singleton weakrefs keyed by viewer type
_viewer_refs: dict[str, weakref.ref] = {}


def _toolbar_icon(name: str) -> wx.Bitmap:
    """Load an SF Symbol sized for the HTML viewer toolbar (regular weight)."""
    return load_sf_symbol(name, point_size=16, weight=0.0) or wx.NullBitmap


class _PageMatch(NamedTuple):
    """A page that matched a search query."""

    page: str
    match_count: int


class _TextExtractor(HTMLParser):
    """Extract visible text from the .content div only.

    Ignores everything outside <div class="content">, plus script/style.
    """

    _SKIP_TAGS = frozenset(("script", "style", "pre"))

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._in_content = False
        self._content_depth = 0  # nested div depth inside .content
        self._skip_depth = 0  # nested script/style/pre depth

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._in_content and tag in self._SKIP_TAGS:
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
        if self._skip_depth > 0 and tag in self._SKIP_TAGS:
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


# noinspection PyUnusedLocal,PyUnresolvedReferences
class _SearchController:
    """Cross-page search state machine for HTMLViewerWindow.

    Owns the text index, search cursors, and JavaScript bridge calls.
    The view creates this controller and wires toolbar/search events to it.
    """

    def __init__(
        self,
        *,
        webview: wx.Window,
        search_ctrl: wx.SearchCtrl,
        search_label: wx.StaticText,
        toolbar: wx.ToolBar,
        prev_id: int,
        next_id: int,
        prev_match_id: int,
        next_match_id: int,
        page_order: list[str],
        page_index: dict[str, str],
        base_path: Path,
        frame: wx.Frame,
    ) -> None:
        # Widget references (injected, not owned)
        self._webview = webview
        self._search_ctrl = search_ctrl
        self._search_label = search_label
        self._toolbar = toolbar
        self._prev_id = prev_id
        self._next_id = next_id
        self._prev_match_id = prev_match_id
        self._next_match_id = next_match_id
        self._page_order = page_order
        self._page_index = page_index
        self._base_path = base_path

        # Search state
        self._search_pages: list[_PageMatch] = []
        self._page_cursor = 0
        self._match_cursor = 0
        self._page_ready = False
        self._pending_mark = False
        self._pending_focus = False
        self._last_query = ""
        self._debounce_timer = wx.Timer(frame)

    # ── Queries ──

    def _total_matches(self) -> int:
        return sum(m.match_count for m in self._search_pages)

    def _global_position(self) -> int:
        return sum(m.match_count for m in self._search_pages[: self._page_cursor]) + self._match_cursor + 1

    # ── View update ──

    def _update_search_ui(self) -> None:
        total = self._total_matches()
        has_results = total > 0
        self._toolbar.EnableTool(self._prev_match_id, has_results)
        self._toolbar.EnableTool(self._next_match_id, has_results)
        if has_results:
            self._search_label.SetLabel(f"{self._global_position()} of {total}")
        elif self._search_ctrl.GetValue():
            self._search_label.SetLabel("No results")
        else:
            self._search_label.SetLabel("")

    def _update_nav_buttons(self) -> None:
        idx, _ = self.current_page_info()
        self._toolbar.EnableTool(self._prev_id, idx > 0)
        self._toolbar.EnableTool(self._next_id, 0 <= idx < len(self._page_order) - 1)

    # ── JS bridge ──

    def _mark_all(self) -> None:
        if not self._page_ready:
            return
        query = self._search_ctrl.GetValue()
        self._last_query = query
        self._webview.RunScript(f"shlMark({json.dumps(query)})")

    def _focus_match(self, idx: int) -> None:
        if not self._page_ready:
            return
        self._webview.RunScript(f"shlFocus({idx})")

    def _clear_highlights(self) -> None:
        if not self._page_ready:
            return
        self._last_query = ""
        self._webview.RunScript("shlClear()")

    # ── Public: core search logic ──

    def run_search(self, query: str) -> None:
        self._search_pages.clear()
        self._page_cursor = 0
        self._match_cursor = 0
        if not query or len(query) < Layout.HTML_VIEWER_MIN_SEARCH_LEN:
            self._pending_mark = False
            self._pending_focus = False
            self._clear_highlights()
            self._update_search_ui()
            return
        q = query.lower()
        for page in self._page_order:
            count = _count_occurrences(self._page_index.get(page, ""), q)
            if count > 0:
                self._search_pages.append(_PageMatch(page, count))
        self._update_search_ui()
        if self._search_pages:
            _, current = self.current_page_info()
            start_idx = 0
            for i, m in enumerate(self._search_pages):
                if m.page == current:
                    start_idx = i
                    break
            self._navigate_to_page(start_idx, 0)
        else:
            self._clear_highlights()

    # ── Navigation ──

    def _navigate_to_page(self, pg_idx: int, mt_idx: int) -> None:
        self._page_cursor = pg_idx
        self._match_cursor = mt_idx
        page = self._search_pages[pg_idx].page
        current_url = self._webview.GetCurrentURL()
        base_url = current_url.split("#")[0]
        if base_url.endswith(page):
            query = self._search_ctrl.GetValue()
            if query != self._last_query:
                self._mark_all()
            self._focus_match(self._match_cursor)
            self._update_search_ui()
        else:
            self._page_ready = False
            self._pending_mark = True
            self._pending_focus = True
            self._webview.LoadURL((self._base_path / page).as_uri())

    def current_page_info(self) -> tuple[int, str]:
        """Return (index, rel_path) of the current page."""
        current_url = self._webview.GetCurrentURL()
        base_url = current_url.split("#")[0]
        for i, page in enumerate(self._page_order):
            if base_url.endswith(page):
                return i, page
        return -1, ""

    # ── Public: reset all state ──

    def clear(self) -> None:
        self._debounce_timer.Stop()
        self._search_ctrl.ChangeValue("")
        self._search_pages.clear()
        self._page_cursor = 0
        self._match_cursor = 0
        self._pending_mark = False
        self._pending_focus = False
        self._clear_highlights()
        self._update_search_ui()

    def stop(self) -> None:
        """Stop timer and prevent RunScript on dead WebView."""
        self._debounce_timer.Stop()
        self._page_ready = False

    # ── Event handlers ──

    def on_search_text(self, evt: wx.CommandEvent) -> None:
        query = self._search_ctrl.GetValue()
        if len(query) < Layout.HTML_VIEWER_MIN_SEARCH_LEN:
            self._debounce_timer.Stop()
            self.run_search("")
            return
        self._debounce_timer.Stop()
        self._debounce_timer.StartOnce(Layout.HTML_VIEWER_DEBOUNCE_MS)

    def on_debounce_timer(self, evt: wx.TimerEvent) -> None:
        self.run_search(self._search_ctrl.GetValue())

    def on_search_cancel(self, evt: wx.CommandEvent) -> None:
        self.clear()

    def on_prev_match(self, evt: wx.CommandEvent) -> None:
        if not self._search_pages:
            return
        if self._match_cursor > 0:
            self._match_cursor -= 1
            self._focus_match(self._match_cursor)
            self._update_search_ui()
        else:
            prev_pg = (self._page_cursor - 1) % len(self._search_pages)
            self._navigate_to_page(prev_pg, self._search_pages[prev_pg].match_count - 1)

    def on_next_match(self, evt: wx.CommandEvent) -> None:
        if not self._search_pages:
            return
        if self._match_cursor < self._search_pages[self._page_cursor].match_count - 1:
            self._match_cursor += 1
            self._focus_match(self._match_cursor)
            self._update_search_ui()
        else:
            next_pg = (self._page_cursor + 1) % len(self._search_pages)
            self._navigate_to_page(next_pg, 0)

    def on_page_loaded(self, evt: wx.Event) -> None:
        self._page_ready = True
        self._update_nav_buttons()
        if self._pending_mark:
            self._pending_mark = False
            self._mark_all()
        if self._pending_focus:
            self._pending_focus = False
            self._focus_match(self._match_cursor)
            self._update_search_ui()
        evt.Skip()

    @property
    def debounce_timer(self) -> wx.Timer:
        return self._debounce_timer


# noinspection PyUnusedLocal,PyTypeChecker,PyUnresolvedReferences
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
        if not page_order:
            raise ValueError("page_order must not be empty")

        self._page_order = page_order
        self._base_path = base_path

        frame = wx.Frame(parent, title=title, size=size, style=wx.DEFAULT_FRAME_STYLE)
        self._frame = frame

        sizer = wx.BoxSizer(wx.VERTICAL)

        # Build text index for search
        page_index = _build_page_index(base_path, page_order)

        # Toolbar
        toolbar = wx.ToolBar(frame, style=wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
        toolbar.SetToolBitmapSize(Layout.HTML_VIEWER_TOOL_BITMAP_SIZE)

        home_bmp = _toolbar_icon("house")
        home_id = toolbar.AddTool(wx.ID_ANY, "Home", home_bmp, shortHelp="Home").GetId()

        prev_bmp = _toolbar_icon("chevron.left")
        prev_id = toolbar.AddTool(wx.ID_ANY, "Previous", prev_bmp, shortHelp="Previous page").GetId()

        next_bmp = _toolbar_icon("chevron.right")
        next_id = toolbar.AddTool(wx.ID_ANY, "Next", next_bmp, shortHelp="Next page").GetId()

        # Search controls (right side)
        toolbar.AddStretchableSpace()

        search_label = wx.StaticText(
            toolbar, label="", size=(Layout.HTML_VIEWER_LABEL_WIDTH, -1), style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE
        )
        search_label.SetForegroundColour(Color.TEXT_SECONDARY)
        toolbar.AddControl(search_label)

        search_ctrl = wx.SearchCtrl(toolbar, size=(Layout.HTML_VIEWER_SEARCH_MIN_WIDTH, -1))
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
            fixed_w = (
                Layout.HTML_VIEWER_NUM_TOOLS * Layout.HTML_VIEWER_TOOL_WIDTH_EST
                + Layout.HTML_VIEWER_LABEL_WIDTH
                + Layout.HTML_VIEWER_TOOLBAR_MARGIN
            )
            new_w = max(Layout.HTML_VIEWER_SEARCH_MIN_WIDTH, tb_w - fixed_w)
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

        # Menu bar so this viewer gets its own Cmd+W / Cmd+F / Help on macOS.
        # On macOS, the focused frame's menu bar becomes the global menu bar.
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_CLOSE, "Close Window\tCtrl+W")
        menubar.Append(file_menu, "&File")
        edit_menu = wx.Menu()
        find_id = wx.NewIdRef()
        find_item = edit_menu.Append(find_id, "Find\tCtrl+F")
        find_icon = load_menu_icon("magnifyingglass")
        if find_icon:
            find_item.SetBitmap(find_icon)
        menubar.Append(edit_menu, "&Edit")
        menubar.Append(build_help_menu(frame), "&Help")
        frame.SetMenuBar(menubar)
        frame.Bind(wx.EVT_MENU, lambda e: frame.Close(), id=wx.ID_CLOSE)
        frame.Bind(wx.EVT_MENU, lambda e: search_ctrl.SetFocus(), id=find_id)

        frame.CenterOnParent()

        frame.Show()

        # --- Search controller ---
        search = _SearchController(
            webview=webview,
            search_ctrl=search_ctrl,
            search_label=search_label,
            toolbar=toolbar,
            prev_id=prev_id,
            next_id=next_id,
            prev_match_id=prev_match_id,
            next_match_id=next_match_id,
            page_order=page_order,
            page_index=page_index,
            base_path=base_path,
            frame=frame,
        )

        # --- Navigation event handlers ---
        # noinspection PyShadowingNames
        def on_home(evt: wx.CommandEvent) -> None:
            search.clear()
            webview.LoadURL((base_path / page_order[0]).as_uri())

        def on_prev(evt: wx.CommandEvent) -> None:
            search.clear()
            idx, _ = search.current_page_info()
            if idx > 0:
                webview.LoadURL((base_path / page_order[idx - 1]).as_uri())

        def on_next(evt: wx.CommandEvent) -> None:
            search.clear()
            idx, _ = search.current_page_info()
            if 0 <= idx < len(page_order) - 1:
                webview.LoadURL((base_path / page_order[idx + 1]).as_uri())

        # noinspection PyShadowingNames
        def on_navigating(evt: wx.Event) -> None:
            url = evt.GetURL()  # type: ignore[attr-defined]
            # noinspection HttpUrlsUsage
            if url.startswith(("http://", "https://")):
                evt.Veto()  # type: ignore[attr-defined]
                wx.LaunchDefaultBrowser(url)
            else:
                evt.Skip()

        # --- Event wiring ---
        frame.Bind(wx.EVT_TOOL, on_home, id=home_id)
        frame.Bind(wx.EVT_TOOL, on_prev, id=prev_id)
        frame.Bind(wx.EVT_TOOL, on_next, id=next_id)
        frame.Bind(wx.EVT_TOOL, search.on_prev_match, id=prev_match_id)
        frame.Bind(wx.EVT_TOOL, search.on_next_match, id=next_match_id)
        search_ctrl.Bind(wx.EVT_TEXT, search.on_search_text)
        search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, search.on_search_cancel)
        frame.Bind(wx.EVT_TIMER, search.on_debounce_timer, search.debounce_timer)
        webview.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING, on_navigating)
        webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, search.on_page_loaded)

        # Cmd+F is handled by the Edit > Find menu item above

        # Expose refresh_colors on the frame so appearance observers can find it
        frame.refresh_colors = self.refresh_colors  # type: ignore[attr-defined]

        # Stop debounce timer on close/destroy to prevent RunScript on a dead
        # WebView.  EVT_CLOSE covers user close; EVT_WINDOW_DESTROY covers
        # programmatic Destroy() calls (e.g. test teardown).
        def _stop_timer(evt: wx.Event) -> None:
            search.stop()
            evt.Skip()

        frame.Bind(wx.EVT_CLOSE, _stop_timer)
        frame.Bind(wx.EVT_WINDOW_DESTROY, _stop_timer)

        # Initial search ctrl sizing
        wx.CallAfter(_resize_search_ctrl)

    def refresh_colors(self) -> None:
        """Update toolbar icons and border for current appearance mode."""
        for tool_id, symbol_name in self._tool_icons:
            bmp = _toolbar_icon(symbol_name)
            self._toolbar.SetToolNormalBitmap(tool_id, wx.BitmapBundle(bmp))
        self._toolbar.Realize()
        self._tb_line.SetBackgroundColour(Color.BORDER)
        self._frame.Refresh()

    @property
    def frame(self) -> wx.Frame:
        return self._frame


# noinspection PyTypeChecker
def build_help_menu(frame: wx.Frame) -> wx.Menu:
    """Build a Help menu with viewer items and bind events.

    Opens each viewer as a singleton.  When called from a viewer frame,
    ``frame.GetParent()`` should be the main window so that new viewers
    are parented correctly.
    """
    from app.core.services.config_service import ConfigService
    from app.gui.dialogs.changelog import show_changelog
    from app.gui.dialogs.help import show_help
    from app.gui.dialogs.licenses import show_licenses

    parent = frame.GetParent() or frame

    menu = wx.Menu()

    help_item = menu.Append(wx.ID_HELP, "Greeting Cards Help")
    help_icon = load_menu_icon("book")
    if help_icon:
        help_item.SetBitmap(help_icon)

    whats_new_id = wx.NewIdRef()
    whats_new_item = menu.Append(whats_new_id, "What's New")
    whats_new_icon = load_menu_icon("newspaper")
    if whats_new_icon:
        whats_new_item.SetBitmap(whats_new_icon)

    licenses_id = wx.NewIdRef()
    licenses_item = menu.Append(licenses_id, "Licenses")
    licenses_icon = load_menu_icon("doc.text")
    if licenses_icon:
        licenses_item.SetBitmap(licenses_icon)

    menu.AppendSeparator()

    github_id = wx.NewIdRef()
    github_item = menu.Append(github_id, "GitHub Repository")
    github_icon = load_menu_icon("arrow.up.forward.square")
    if github_icon:
        github_item.SetBitmap(github_icon)

    frame.Bind(wx.EVT_MENU, lambda e: show_help(parent), id=wx.ID_HELP)
    frame.Bind(wx.EVT_MENU, lambda e: show_changelog(parent), id=whats_new_id)
    frame.Bind(wx.EVT_MENU, lambda e: show_licenses(parent), id=licenses_id)
    frame.Bind(wx.EVT_MENU, lambda e: wx.LaunchDefaultBrowser(ConfigService.get_github_url()), id=github_id)

    return menu


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
        try:
            if frame is not None and not frame.IsBeingDeleted():
                frame.Raise()
                return None
        except RuntimeError as exc:
            if "C++ object" not in str(exc):
                raise
            # C++ object already deleted; create a new one

    viewer = HTMLViewerWindow(
        parent, title=title, size=size, base_path=base_path, page_order=page_order, search_hint=search_hint
    )
    _viewer_refs[singleton_key] = weakref.ref(viewer.frame)
    return viewer
