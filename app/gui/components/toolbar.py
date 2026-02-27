"""Toolbar and menu bar construction for MainWindow.

ToolbarManager takes a MainWindow instance and sets toolbar/menu IDs directly
on it so existing attribute access patterns (e.g. window._reload_id) are
preserved throughout the codebase.
"""

from __future__ import annotations

from typing import Any

import wx
import wx.adv

from app.gui.components.html_viewer import build_help_menu
from app.gui.icons import load_menu_icon, load_sf_symbol
from app.gui.styles import Font, Layout


class ToolbarManager:
    """Creates and manages the toolbar and menu bar for MainWindow.

    All toolbar/menu IDs and widget references are stored directly on the
    ``window`` object so that existing call sites and tests continue to work
    without modification.
    """

    def __init__(self, window: Any) -> None:
        self._w = window

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def build_menu_bar(self) -> None:
        """Create the native macOS menu bar and bind events on window."""
        w = self._w
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_OPEN, "Open...\tCtrl+O")

        w._reload_menu_id = wx.NewIdRef()
        reload_item = file_menu.Append(w._reload_menu_id, "Reload\tCtrl+Shift+R")
        reload_icon = load_menu_icon("arrow.clockwise")
        if reload_icon:
            reload_item.SetBitmap(reload_icon)

        file_menu.AppendSeparator()

        w._ai_menu_id = wx.NewIdRef()
        ai_item = file_menu.Append(w._ai_menu_id, "AI Analyze\tCtrl+Shift+I")
        ai_icon = load_menu_icon("sparkles")
        if ai_icon:
            ai_item.SetBitmap(ai_icon)

        w._clear_ai_menu_id = wx.NewIdRef()
        clear_ai_item = file_menu.Append(w._clear_ai_menu_id, "Clear AI Results")
        clear_ai_icon = load_menu_icon("eraser")
        if clear_ai_icon:
            clear_ai_item.SetBitmap(clear_ai_icon)

        file_menu.AppendSeparator()

        w._rename_menu_id = wx.NewIdRef()
        rename_item = file_menu.Append(w._rename_menu_id, "Rename Files...\tCtrl+R")
        rename_icon = load_menu_icon("pencil")
        if rename_icon:
            rename_item.SetBitmap(rename_icon)

        w._clear_menu_id = wx.NewIdRef()
        clear_item = file_menu.Append(w._clear_menu_id, "Clear All")
        clear_icon = load_menu_icon("xmark.circle")
        if clear_icon:
            clear_item.SetBitmap(clear_icon)

        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_PREFERENCES, "Settings...\tCtrl+,")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_CLOSE, "Close Window\tCtrl+W")
        file_menu.Append(wx.ID_EXIT, "Quit Greeting Cards\tCtrl+Q")
        menubar.Append(file_menu, "&File")

        # Edit menu
        edit_menu = wx.Menu()

        w._find_menu_id = wx.NewIdRef()
        find_item = edit_menu.Append(w._find_menu_id, "Find...\tCtrl+F")
        find_icon = load_menu_icon("magnifyingglass")
        if find_icon:
            find_item.SetBitmap(find_icon)

        edit_menu.AppendSeparator()

        select_all_item = edit_menu.Append(wx.ID_SELECTALL, "Select All\tCtrl+A")
        select_all_icon = load_menu_icon("checkmark.circle")
        if select_all_icon:
            select_all_item.SetBitmap(select_all_icon)

        w._select_none_id = wx.NewIdRef()
        select_none_item = edit_menu.Append(w._select_none_id, "Select None\tCtrl+Shift+A")
        select_none_icon = load_menu_icon("circle")
        if select_none_icon:
            select_none_item.SetBitmap(select_none_icon)

        edit_menu.AppendSeparator()

        w._remove_menu_id = wx.NewIdRef()
        remove_item = edit_menu.Append(w._remove_menu_id, "Remove\tCtrl+Backspace")
        remove_icon = load_menu_icon("minus.circle")
        if remove_icon:
            remove_item.SetBitmap(remove_icon)

        menubar.Append(edit_menu, "&Edit")

        # Help menu — shared items + About (main window only)
        help_menu = build_help_menu(w._frame)
        help_menu.PrependSeparator()
        help_menu.Prepend(wx.ID_ABOUT, "About Greeting Cards")
        menubar.Append(help_menu, "&Help")

        w._frame.SetMenuBar(menubar)

        # Bind events
        w._frame.Bind(wx.EVT_MENU, lambda e: w._show_about(), id=wx.ID_ABOUT)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._add_files_folders(), id=wx.ID_OPEN)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._show_preferences(), id=wx.ID_PREFERENCES)
        w._frame.Bind(wx.EVT_MENU, w._on_close_window, id=wx.ID_CLOSE)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._frame.Close(), id=wx.ID_EXIT)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._search_ctrl.SetFocus(), id=w._find_menu_id)
        w._frame.Bind(wx.EVT_MENU, w._on_select_all, id=wx.ID_SELECTALL)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._review_panel.select_none(), id=w._select_none_id)
        w._frame.Bind(wx.EVT_MENU, w._on_remove_menu, id=w._remove_menu_id)
        w._frame.Bind(wx.EVT_UPDATE_UI, w._on_update_remove_menu, id=w._remove_menu_id)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._reload_cards(), id=w._reload_menu_id)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._start_ai_all(), id=w._ai_menu_id)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._start_rename(), id=w._rename_menu_id)
        w._frame.Bind(wx.EVT_MENU, lambda e: w._clear_all(), id=w._clear_menu_id)
        w._frame.Bind(wx.EVT_MENU, w._on_clear_ai_results, id=w._clear_ai_menu_id)
        w._frame.Bind(wx.EVT_UPDATE_UI, self.on_update_action_menu, id=w._reload_menu_id)
        w._frame.Bind(wx.EVT_UPDATE_UI, self.on_update_action_menu, id=w._ai_menu_id)
        w._frame.Bind(wx.EVT_UPDATE_UI, self.on_update_action_menu, id=w._rename_menu_id)
        w._frame.Bind(wx.EVT_UPDATE_UI, self.on_update_action_menu, id=w._clear_menu_id)
        w._frame.Bind(wx.EVT_UPDATE_UI, self.on_update_action_menu, id=w._clear_ai_menu_id)

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    # noinspection DuplicatedCode
    def build_toolbar(self) -> None:
        """Build the wx.ToolBar and set IDs and widget refs on window."""
        w = self._w
        toolbar = wx.ToolBar(w._panel, style=wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
        toolbar.SetToolBitmapSize(wx.Size(Layout.TOOLBAR_ICON_SIZE, Layout.TOOLBAR_ICON_SIZE))

        # Add Files tool
        browse_bmp = load_sf_symbol("folder.badge.plus", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        w._browse_id = toolbar.AddTool(
            wx.ID_ANY,
            "Add Files",
            browse_bmp,
            shortHelp="Add PDF files or folders to analyze (can add from multiple sources)",
        ).GetId()

        # Reload tool
        reload_bmp = load_sf_symbol("arrow.clockwise", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        w._reload_id = toolbar.AddTool(
            wx.ID_ANY, "Reload", reload_bmp, shortHelp="Re-check loaded files for changes or deletions (\u21e7\u2318R)"
        ).GetId()
        toolbar.EnableTool(w._reload_id, False)

        toolbar.AddSeparator()

        # AI Analyze tool
        ai_bmp = load_sf_symbol("sparkles", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        w._ai_all_id = toolbar.AddTool(
            wx.ID_ANY, "AI Analyze", ai_bmp, shortHelp="Analyze cards with AI to extract family names (\u21e7\u2318I)"
        ).GetId()
        toolbar.EnableTool(w._ai_all_id, False)

        # Rename tool
        rename_bmp = load_sf_symbol("pencil", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        w._rename_id = toolbar.AddTool(
            wx.ID_ANY, "Rename", rename_bmp, shortHelp="Rename all files based on detected family names"
        ).GetId()
        toolbar.EnableTool(w._rename_id, False)

        # Clear tool
        clear_bmp = load_sf_symbol("xmark.circle", point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
        w._clear_id = toolbar.AddTool(
            wx.ID_ANY, "Clear", clear_bmp, shortHelp="Clear all loaded cards and reset the application"
        ).GetId()
        toolbar.EnableTool(w._clear_id, False)

        toolbar.AddSeparator()

        # Year controls
        year_label = wx.StaticText(toolbar, label="Year:")
        year_label.SetFont(Font.BODY())
        toolbar.AddControl(year_label)
        w._year_ctrl = wx.TextCtrl(toolbar, value=str(w._year), size=(Layout.YEAR_WIDTH, -1))
        w._year_ctrl.SetToolTip("Year to use in renamed file names (e.g., 2024)")
        toolbar.AddControl(w._year_ctrl)

        toolbar.AddStretchableSpace()

        # Search control
        w._search_ctrl = wx.SearchCtrl(toolbar, style=wx.TE_PROCESS_ENTER, size=(Layout.SEARCH_WIDTH, -1))
        w._search_ctrl.ShowSearchButton(True)
        w._search_ctrl.ShowCancelButton(True)
        w._search_ctrl.SetDescriptiveText("Filter cards...")
        w._search_ctrl.SetToolTip("Filter cards by file name or family name")
        w._search_ctrl.Bind(wx.EVT_TEXT, w._on_search_text)
        w._search_ctrl.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, w._on_search_cancel)
        toolbar.AddControl(w._search_ctrl)

        toolbar.Realize()
        w._toolbar = toolbar

        # Bind tool events
        w._frame.Bind(wx.EVT_TOOL, lambda e: w._add_files_folders(), id=w._browse_id)
        w._frame.Bind(wx.EVT_TOOL, lambda e: w._reload_cards(), id=w._reload_id)
        w._frame.Bind(wx.EVT_TOOL, lambda e: w._start_ai_all(), id=w._ai_all_id)
        w._frame.Bind(wx.EVT_TOOL, lambda e: w._start_rename(), id=w._rename_id)
        w._frame.Bind(wx.EVT_TOOL, lambda e: w._clear_all(), id=w._clear_id)

    # ------------------------------------------------------------------
    # Runtime operations (called by MainWindow delegates)
    # ------------------------------------------------------------------

    def enable_action_tools(
        self,
        *,
        reload: bool | None = None,
        ai: bool | None = None,
        rename: bool | None = None,
        clear: bool | None = None,
    ) -> None:
        """Enable or disable action toolbar tools. Pass None to leave unchanged."""
        w = self._w
        if reload is not None:
            w._toolbar.EnableTool(w._reload_id, reload)
        if ai is not None:
            w._toolbar.EnableTool(w._ai_all_id, ai)
        if rename is not None:
            w._toolbar.EnableTool(w._rename_id, rename)
        if clear is not None:
            w._toolbar.EnableTool(w._clear_id, clear)

    def on_update_action_menu(self, event: wx.UpdateUIEvent) -> None:
        """Enable/disable action menu items and update labels dynamically."""
        w = self._w
        menu_to_tool = {
            w._reload_menu_id: w._reload_id,
            w._ai_menu_id: w._ai_all_id,
            w._rename_menu_id: w._rename_id,
            w._clear_menu_id: w._clear_id,
            w._clear_ai_menu_id: w._clear_id,
        }
        tool_id = menu_to_tool.get(event.GetId())
        if tool_id is not None:
            enabled = w._toolbar.GetToolEnabled(tool_id)
            event.Enable(enabled)

            # Dynamic labels for scoped actions
            scoped_labels = {
                w._ai_menu_id: ("AI Analyze", "\tCtrl+Shift+I"),
                w._clear_ai_menu_id: ("Clear AI Results", ""),
            }
            if event.GetId() in scoped_labels:
                base, shortcut = scoped_labels[event.GetId()]
                if enabled and w._cards_by_hash:
                    cards, scope = w._get_target_cards()
                    n = len(cards)
                    scope_label = "Selected" if scope == "selected" else "Visible"
                    event.SetText(f"{base} {scope_label} ({n}){shortcut}")
                else:
                    event.SetText(f"{base}{shortcut}")

    def refresh_icons(self) -> None:
        """Re-render toolbar icons for the current appearance (dark/light mode)."""
        w = self._w
        icon_map = {
            w._browse_id: "folder.badge.plus",
            w._reload_id: "arrow.clockwise",
            w._ai_all_id: "sparkles",
            w._rename_id: "pencil",
            w._clear_id: "xmark.circle",
        }
        for tool_id, symbol in icon_map.items():
            bmp = load_sf_symbol(symbol, point_size=Layout.TOOLBAR_ICON_POINTS) or wx.NullBitmap
            w._toolbar.SetToolNormalBitmap(tool_id, wx.BitmapBundle(bmp))
        w._toolbar.Realize()
