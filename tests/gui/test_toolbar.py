"""Tests for app.gui.components.toolbar.ToolbarManager."""

import wx

from app.gui.components.toolbar import ToolbarManager
from app.gui.main_window import MainWindow


def test_toolbar_manager_sets_browse_id(wx_app):
    """ToolbarManager.build_toolbar sets _browse_id on window."""
    window = MainWindow()
    assert hasattr(window, "_browse_id")
    assert window._browse_id is not None
    window._frame.Destroy()


def test_toolbar_manager_sets_reload_id(wx_app):
    """ToolbarManager.build_toolbar sets _reload_id on window."""
    window = MainWindow()
    assert hasattr(window, "_reload_id")
    tool = window._toolbar.FindById(window._reload_id)
    assert tool is not None
    window._frame.Destroy()


def test_toolbar_manager_sets_menu_ids(wx_app):
    """ToolbarManager.build_menu_bar sets all menu IDs on window."""
    window = MainWindow()
    for attr in ("_reload_menu_id", "_ai_menu_id", "_rename_menu_id", "_clear_menu_id", "_clear_ai_menu_id"):
        assert hasattr(window, attr), f"Missing {attr}"
    window._frame.Destroy()


def test_enable_action_tools_via_manager(wx_app):
    """enable_action_tools correctly enables/disables tools."""
    window = MainWindow()
    mgr = ToolbarManager(window)

    mgr.enable_action_tools(reload=True)
    assert window._toolbar.GetToolEnabled(window._reload_id)

    mgr.enable_action_tools(reload=False)
    assert not window._toolbar.GetToolEnabled(window._reload_id)

    window._frame.Destroy()


def test_refresh_icons_via_manager(wx_app):
    """refresh_icons calls load_sf_symbol for each tool icon."""
    from unittest.mock import patch

    window = MainWindow()
    mgr = ToolbarManager(window)

    with patch("app.gui.components.toolbar.load_sf_symbol", return_value=None) as mock_load:
        mgr.refresh_icons()
        symbol_names = [call.args[0] for call in mock_load.call_args_list]
        assert "arrow.clockwise" in symbol_names
        assert "sparkles" in symbol_names
        assert "pencil" in symbol_names

    window._frame.Destroy()
