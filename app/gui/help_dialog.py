"""Help system — thin wrapper around the shared HTML viewer."""

import sys
from pathlib import Path

import wx

from app.core.help_builder import get_page_order
from app.core.paths import is_bundled
from app.gui.html_viewer import show_viewer

_HELP_REL_PATH = Path("_runtime_content") / "html" / "help"


def show_help(parent: wx.Window) -> None:
    """Open help in a WebView window."""
    base_path = _get_help_base_path()
    page_order = get_page_order(base_path)
    show_viewer(parent, title="Greeting Cards Help",
                base_path=base_path, page_order=page_order,
                singleton_key="help")


def _get_help_base_path() -> Path:
    """Return path to help directory."""
    if is_bundled():
        return Path(sys._MEIPASS) / _HELP_REL_PATH
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / _HELP_REL_PATH


def _get_help_index_path() -> Path:
    """Return path to help index.html."""
    return _get_help_base_path() / "index.html"
