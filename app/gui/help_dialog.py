"""Help system — WebView-based help viewer."""

import sys
import weakref
from pathlib import Path

import wx

from app.core.paths import is_bundled
from app.gui.icons import load_sf_symbol

# Singleton weakref for help window
_help_window_ref = None

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


def show_help(parent):
    """Open help in a WebView window."""
    global _help_window_ref

    # Reuse existing window if still alive
    if _help_window_ref is not None:
        window = _help_window_ref()
        if window is not None and not window.IsBeingDeleted():
            window.Raise()
            return

    import wx.html2

    frame = wx.Frame(parent, title="Greeting Cards Help", size=(800, 600),
                     style=wx.DEFAULT_FRAME_STYLE)

    sizer = wx.BoxSizer(wx.VERTICAL)

    # Toolbar with Home / Prev / Next
    base_path = _get_help_base_path()
    toolbar = wx.ToolBar(frame, style=wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
    toolbar.SetToolBitmapSize(wx.Size(24, 24))

    _ICON_KW = dict(point_size=16, weight=0.0)  # Regular weight to match main toolbar
    home_bmp = load_sf_symbol("house", **_ICON_KW) or wx.NullBitmap
    home_id = toolbar.AddTool(wx.ID_ANY, "Home", home_bmp,
                              shortHelp="Home").GetId()

    prev_bmp = load_sf_symbol("chevron.left", **_ICON_KW) or wx.NullBitmap
    prev_id = toolbar.AddTool(wx.ID_ANY, "Previous", prev_bmp,
                              shortHelp="Previous page").GetId()

    next_bmp = load_sf_symbol("chevron.right", **_ICON_KW) or wx.NullBitmap
    next_id = toolbar.AddTool(wx.ID_ANY, "Next", next_bmp,
                              shortHelp="Next page").GetId()

    toolbar.EnableTool(prev_id, False)
    toolbar.Realize()
    sizer.Add(toolbar, 0, wx.EXPAND)

    # WebView — HTML pages have built-in CSS sidebar
    index_path = _get_help_index_path()
    url = index_path.as_uri()
    webview = wx.html2.WebView.New(frame)
    webview.LoadURL(url)
    sizer.Add(webview, 1, wx.EXPAND)

    frame.SetSizer(sizer)
    frame.CenterOnParent()
    frame.Show()

    _help_window_ref = weakref.ref(frame)

    # --- Navigation helpers ---
    def _current_index():
        """Return index of current page in _PAGE_ORDER, or -1."""
        current_url = webview.GetCurrentURL()
        for i, page in enumerate(_PAGE_ORDER):
            if current_url.endswith(page):
                return i
        return -1

    def _update_nav_buttons(evt=None):
        idx = _current_index()
        toolbar.EnableTool(prev_id, idx > 0)
        toolbar.EnableTool(next_id, 0 <= idx < len(_PAGE_ORDER) - 1)
        if evt:
            evt.Skip()

    def on_home(evt):
        webview.LoadURL((base_path / "index.html").as_uri())

    def on_prev(evt):
        idx = _current_index()
        if idx > 0:
            webview.LoadURL((base_path / _PAGE_ORDER[idx - 1]).as_uri())

    def on_next(evt):
        idx = _current_index()
        if 0 <= idx < len(_PAGE_ORDER) - 1:
            webview.LoadURL((base_path / _PAGE_ORDER[idx + 1]).as_uri())

    frame.Bind(wx.EVT_TOOL, on_home, id=home_id)
    frame.Bind(wx.EVT_TOOL, on_prev, id=prev_id)
    frame.Bind(wx.EVT_TOOL, on_next, id=next_id)
    webview.Bind(wx.html2.EVT_WEBVIEW_NAVIGATED, _update_nav_buttons)


def _get_help_base_path() -> Path:
    """Return path to help en.lproj directory."""
    if is_bundled():
        return Path(sys._MEIPASS) / "help" / "GreetingCards.help" / "Contents" / "Resources" / "en.lproj"
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "help" / "GreetingCards.help" / "Contents" / "Resources" / "en.lproj"


def _get_help_index_path() -> Path:
    """Return path to help index.html."""
    return _get_help_base_path() / "index.html"
