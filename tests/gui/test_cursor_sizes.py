"""Interactive dialog to test different cursor sizes and pick the best one.

Run this to visually compare cursor sizes:
    .venv/bin/python tests/gui/test_cursor_sizes.py
"""

import wx
from app.gui import wx_styles
from app.gui.wx_icons import load_cursor_from_symbol


class CursorSizeTestDialog(wx.Dialog):
    """Dialog to test different cursor sizes and pick the best one."""

    # Test sizes from small to large
    SIZES = [6, 7, 8, 9, 10, 11, 12]

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="Cursor Size Picker",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        self.SetSize(900, 700)

        self._cursors = {}  # Cache loaded cursors
        self._build_ui()
        self.Centre()

    def _build_ui(self):
        """Build the dialog UI."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        instructions = wx.StaticText(
            self,
            label="Hover over each box to see the cursor at that size. "
                  "Click a size to see details in the console."
        )
        instructions.Wrap(850)
        main_sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, wx_styles.Layout.PAD)

        # Scrolled window for cursor samples
        scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 20)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        # Add a test panel for each size
        for size in self.SIZES:
            panel = self._create_cursor_panel(scroll, size)
            scroll_sizer.Add(panel, 0, wx.EXPAND | wx.ALL, 4)

        scroll.SetSizer(scroll_sizer)
        main_sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, wx_styles.Layout.PAD)

        # Close button
        close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        main_sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.ALL, wx_styles.Layout.PAD)

        self.SetSizer(main_sizer)

    def _create_cursor_panel(self, parent, size: int):
        """Create a panel to test a specific cursor size.

        Args:
            parent: Parent window
            size: Point size for the cursor

        Returns:
            wx.Panel with hover areas for both cursors
        """
        # Container panel with border
        container = wx.Panel(parent, style=wx.BORDER_SIMPLE)
        container.SetBackgroundColour(wx_styles.Color.BG_SECONDARY)
        sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Size label
        label = wx.StaticText(container, label=f"{size}pt", style=wx.ALIGN_CENTER)
        label.SetFont(wx.Font(wx.FontInfo(12).Bold()))
        label.SetMinSize((60, -1))
        sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)

        # Load cursors for this size
        zoom_in_cursor = load_cursor_from_symbol(
            "plus.magnifyingglass",
            point_size=size,
            color_hex="#000000"
        )
        zoom_out_cursor = load_cursor_from_symbol(
            "minus.magnifyingglass",
            point_size=size,
            color_hex="#000000"
        )

        # Fallback if loading failed
        if not zoom_in_cursor:
            zoom_in_cursor = wx.Cursor(wx.CURSOR_MAGNIFIER)
        if not zoom_out_cursor:
            zoom_out_cursor = wx.Cursor(wx.CURSOR_MAGNIFIER)

        # Cache cursors
        self._cursors[f"in_{size}"] = zoom_in_cursor
        self._cursors[f"out_{size}"] = zoom_out_cursor

        # Zoom in preview area
        zoom_in_area = wx.Panel(container, size=(180, 80))
        zoom_in_area.SetBackgroundColour("#E8F5E9")  # Light green
        zoom_in_sizer = wx.BoxSizer(wx.VERTICAL)

        zoom_in_title = wx.StaticText(zoom_in_area, label="Zoom In (Shift)")
        font = wx_styles.Font.SMALL()
        font.MakeBold()
        zoom_in_title.SetFont(font)
        zoom_in_sizer.Add(zoom_in_title, 0, wx.ALIGN_CENTER | wx.TOP, 8)

        zoom_in_desc = wx.StaticText(zoom_in_area, label="Hover to preview")
        zoom_in_desc.SetFont(wx_styles.Font.SMALL())
        zoom_in_desc.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        zoom_in_sizer.Add(zoom_in_desc, 0, wx.ALIGN_CENTER | wx.TOP, 4)

        zoom_in_area.SetSizer(zoom_in_sizer)
        zoom_in_area.Bind(wx.EVT_ENTER_WINDOW, lambda e, c=zoom_in_cursor, s=size: self._on_enter(e, c, s, "zoom in"))
        zoom_in_area.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self._on_leave(e))
        zoom_in_area.Bind(wx.EVT_LEFT_DOWN, lambda e, s=size: self._on_click(e, s, "zoom in"))

        sizer.Add(zoom_in_area, 0, wx.ALL, 8)

        # Spacer
        sizer.Add((20, -1), 0)

        # Zoom out preview area
        zoom_out_area = wx.Panel(container, size=(180, 80))
        zoom_out_area.SetBackgroundColour("#FFF3E0")  # Light orange
        zoom_out_sizer = wx.BoxSizer(wx.VERTICAL)

        zoom_out_title = wx.StaticText(zoom_out_area, label="Zoom Out (Option)")
        font = wx_styles.Font.SMALL()
        font.MakeBold()
        zoom_out_title.SetFont(font)
        zoom_out_sizer.Add(zoom_out_title, 0, wx.ALIGN_CENTER | wx.TOP, 8)

        zoom_out_desc = wx.StaticText(zoom_out_area, label="Hover to preview")
        zoom_out_desc.SetFont(wx_styles.Font.SMALL())
        zoom_out_desc.SetForegroundColour(wx_styles.Color.TEXT_SECONDARY)
        zoom_out_sizer.Add(zoom_out_desc, 0, wx.ALIGN_CENTER | wx.TOP, 4)

        zoom_out_area.SetSizer(zoom_out_sizer)
        zoom_out_area.Bind(wx.EVT_ENTER_WINDOW, lambda e, c=zoom_out_cursor, s=size: self._on_enter(e, c, s, "zoom out"))
        zoom_out_area.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self._on_leave(e))
        zoom_out_area.Bind(wx.EVT_LEFT_DOWN, lambda e, s=size: self._on_click(e, s, "zoom out"))

        sizer.Add(zoom_out_area, 0, wx.ALL, 8)

        # Status indicator (shows if this is the current size - 20pt was the original)
        # Marking nothing as current since we're showing smaller sizes

        container.SetSizer(sizer)
        return container

    def _on_enter(self, event, cursor: wx.Cursor, size: int, cursor_type: str):
        """Set cursor when entering hover area."""
        panel = event.GetEventObject()
        panel.SetCursor(cursor)

    def _on_leave(self, event):
        """Reset cursor when leaving hover area."""
        panel = event.GetEventObject()
        panel.SetCursor(wx.NullCursor)

    def _on_click(self, event, size: int, cursor_type: str):
        """Print cursor info when clicked."""
        print(f"✓ Selected: {size}pt for {cursor_type}")
        print(f"  To use this size, update wx_preview_panel.py:")
        print(f"  load_cursor_from_symbol(..., point_size={size}, ...)")
        print()


def main():
    """Run the cursor size picker dialog."""
    app = wx.App()
    dialog = CursorSizeTestDialog()
    dialog.ShowModal()
    dialog.Destroy()
    app.MainLoop()


if __name__ == "__main__":
    main()
