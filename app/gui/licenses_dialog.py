"""Licenses viewer — opens generated HTML in a WebView window."""

import wx

from app.core.license_discovery import get_page_order
from app.core.paths import get_runtime_content_path
from app.gui.html_viewer import show_viewer


def show_licenses(parent: wx.Window) -> None:
    """Open licenses viewer in a WebView window."""
    base_path = get_runtime_content_path("html/licenses")
    page_order = get_page_order(base_path)
    show_viewer(parent, title="Open-Source Licenses",
                base_path=base_path, page_order=page_order,
                singleton_key="licenses", size=(1000, 650))
