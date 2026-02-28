"""Tests for app.gui.components.toolbar.ToolbarManager."""

from unittest.mock import MagicMock, patch

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
    window = MainWindow()
    mgr = ToolbarManager(window)

    with patch("app.gui.components.toolbar.load_sf_symbol", return_value=None) as mock_load:
        mgr.refresh_icons()
        symbol_names = [call.args[0] for call in mock_load.call_args_list]
        assert "arrow.clockwise" in symbol_names
        assert "sparkles" in symbol_names
        assert "pencil" in symbol_names

    window._frame.Destroy()


class TestOnUpdateActionMenu:
    """Tests for on_update_action_menu dynamic label updates (lines 257-283)."""

    def test_menu_item_disabled_when_tool_disabled(self, wx_app):
        """Menu item should be disabled when corresponding toolbar tool is disabled."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        # Reload tool is disabled by default
        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = window._reload_menu_id

        mgr.on_update_action_menu(event)

        event.Enable.assert_called_once_with(False)
        window._frame.Destroy()

    def test_menu_item_enabled_when_tool_enabled(self, wx_app):
        """Menu item should be enabled when corresponding toolbar tool is enabled."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        # Enable the reload tool
        window._toolbar.EnableTool(window._reload_id, True)

        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = window._reload_menu_id

        mgr.on_update_action_menu(event)

        event.Enable.assert_called_once_with(True)
        window._frame.Destroy()

    def test_ai_menu_shows_scoped_label_when_enabled_with_cards(self, wx_app):
        """AI menu should show scoped label with count when enabled and cards loaded."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        # Enable AI tool and simulate cards
        window._toolbar.EnableTool(window._ai_all_id, True)
        window._cards_by_hash = {"h1": MagicMock()}
        window._get_target_cards = MagicMock(return_value=([MagicMock(), MagicMock()], "visible"))

        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = window._ai_menu_id

        mgr.on_update_action_menu(event)

        event.Enable.assert_called_once_with(True)
        set_text_arg = event.SetText.call_args[0][0]
        assert "AI Analyze" in set_text_arg
        assert "Visible" in set_text_arg
        assert "(2)" in set_text_arg
        window._frame.Destroy()

    def test_ai_menu_shows_selected_scope(self, wx_app):
        """AI menu should show 'Selected' when scope is selected."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        window._toolbar.EnableTool(window._ai_all_id, True)
        window._cards_by_hash = {"h1": MagicMock()}
        window._get_target_cards = MagicMock(return_value=([MagicMock()], "selected"))

        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = window._ai_menu_id

        mgr.on_update_action_menu(event)

        set_text_arg = event.SetText.call_args[0][0]
        assert "Selected" in set_text_arg
        assert "(1)" in set_text_arg
        window._frame.Destroy()

    def test_ai_menu_shows_base_label_when_disabled(self, wx_app):
        """AI menu should show base label without count when tool is disabled."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        # AI tool is disabled by default
        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = window._ai_menu_id

        mgr.on_update_action_menu(event)

        event.Enable.assert_called_once_with(False)
        set_text_arg = event.SetText.call_args[0][0]
        assert set_text_arg == "AI Analyze\tCtrl+Shift+I"
        window._frame.Destroy()

    def test_clear_ai_menu_shows_base_label_when_disabled(self, wx_app):
        """Clear AI menu should show base label when tool is disabled."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = window._clear_ai_menu_id

        mgr.on_update_action_menu(event)

        set_text_arg = event.SetText.call_args[0][0]
        assert set_text_arg == "Clear AI Results"
        window._frame.Destroy()

    def test_unknown_menu_id_is_noop(self, wx_app):
        """Unknown menu ID should not crash or call Enable."""
        window = MainWindow()
        mgr = ToolbarManager(window)

        event = MagicMock(spec=wx.UpdateUIEvent)
        event.GetId.return_value = wx.NewIdRef()

        mgr.on_update_action_menu(event)

        event.Enable.assert_not_called()
        window._frame.Destroy()
