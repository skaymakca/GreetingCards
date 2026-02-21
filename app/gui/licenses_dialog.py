"""Licenses viewer — opens generated HTML in a WebView window."""

import sys
from pathlib import Path

import wx

from app.core.license_discovery import get_page_order
from app.core.paths import is_bundled
from app.gui.html_viewer import show_viewer

_LICENSES_HTML_REL_PATH = Path("_runtime_content") / "html" / "licenses"


def _get_licenses_base_path() -> Path:
    """Return path to licenses HTML directory."""
    if is_bundled():
        return Path(sys._MEIPASS) / _LICENSES_HTML_REL_PATH
    return Path(__file__).resolve().parent.parent.parent / _LICENSES_HTML_REL_PATH


def show_licenses(parent: wx.Window) -> None:
    """Open licenses viewer in a WebView window."""
    base_path = _get_licenses_base_path()
    page_order = get_page_order(base_path)
    show_viewer(parent, title="Open-Source Licenses",
                base_path=base_path, page_order=page_order,
                singleton_key="licenses", size=(1000, 650))
