"""Changelog viewer — shows generated HTML in the shared HTML viewer."""

import wx

# Read-only content builder — no service facade needed
from app.core.content.template_env import get_page_order

# Stateless path utility — no service facade needed
from app.core.paths import get_runtime_content_path
from app.gui.components.html_viewer import show_viewer


def show_changelog(parent: wx.Window) -> None:
    """Open changelog in a WebView window."""
    base_path = get_runtime_content_path("html/changelog")
    page_order = get_page_order(base_path)

    show_viewer(parent, title="What's New", base_path=base_path, page_order=page_order, singleton_key="changelog")
