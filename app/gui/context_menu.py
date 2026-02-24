"""Context menu helper for wxPython text entry widgets."""

import wx

from app.gui.icons import load_menu_icon


# noinspection PyUnusedLocal,PyTypeChecker
def add_entry_context_menu(text_ctrl: wx.TextCtrl) -> None:
    """Add a native-style context menu to a TextCtrl widget with Cut, Copy, Paste, Title Case, Clear.

    Uses native wx IDs for Cut/Copy/Paste so they render with native macOS styling.
    Adds custom Title Case and Clear items with SF Symbol icons.

    Args:
        text_ctrl: The wx.TextCtrl widget to attach the context menu to
    """
    # Load SF Symbol icons for custom menu items (dict comprehension with walrus operator)
    icon_specs = {
        "title_case": "textformat.abc",
        "clear": "xmark.circle",
    }
    icons = {key: icon for key, symbol in icon_specs.items() if (icon := load_menu_icon(symbol))}

    # noinspection PyUnusedLocal,PyTypeChecker
    def on_context_menu(event: wx.Event) -> None:
        """Show context menu on right-click."""
        menu = wx.Menu()

        # Use native wx IDs for Cut/Copy/Paste - these should render natively on macOS
        menu.Append(wx.ID_CUT, "Cut")
        menu.Append(wx.ID_COPY, "Copy")
        menu.Append(wx.ID_PASTE, "Paste")

        menu.AppendSeparator()

        # Add our custom items with icons
        title_item = menu.Append(wx.ID_ANY, "Title Case")
        if icons.get("title_case"):
            title_item.SetBitmap(icons["title_case"])
        menu.Bind(wx.EVT_MENU, lambda evt: _title_case(text_ctrl), title_item)

        clear_item = menu.Append(wx.ID_ANY, "Clear")
        if icons.get("clear"):
            clear_item.SetBitmap(icons["clear"])
        menu.Bind(wx.EVT_MENU, lambda evt: _clear(text_ctrl), clear_item)

        # Show the menu
        text_ctrl.PopupMenu(menu)
        menu.Destroy()

    # Store icons reference to prevent garbage collection
    text_ctrl._context_menu_icons = icons  # pyright: ignore[reportAttributeAccessIssue]  # prevent GC

    # Bind right-click event
    text_ctrl.Bind(wx.EVT_CONTEXT_MENU, on_context_menu)


def _title_case(text_ctrl: wx.TextCtrl) -> None:
    """Convert text to Title Case."""
    current_text = text_ctrl.GetValue()
    if current_text:
        title_cased = current_text.title()
        text_ctrl.SetValue(title_cased)


def _clear(text_ctrl: wx.TextCtrl) -> None:
    """Clear all text."""
    text_ctrl.Clear()
