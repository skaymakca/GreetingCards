"""Selection icon picker - shows various SF Symbols for the selection indicator."""

import wx
from app.gui.icons import load_sf_symbol


def create_selection_icon_picker():
    """Create a dialog to pick selection indicator icons."""
    app = wx.App()

    dialog = wx.Dialog(None, title="Selection Icon Picker", size=(600, 700))
    sizer = wx.BoxSizer(wx.VERTICAL)

    # Title
    title = wx.StaticText(dialog, label="Choose Selection Indicator Icon")
    title_font = wx.Font(18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
    title.SetFont(title_font)
    sizer.Add(title, 0, wx.ALL | wx.CENTER, 15)

    # Instructions
    instructions = wx.StaticText(
        dialog,
        label="Click an icon to see its SF Symbol name. Colors shown: Black, Blue, Accent Orange"
    )
    instructions_font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
    instructions.SetFont(instructions_font)
    sizer.Add(instructions, 0, wx.ALL | wx.CENTER, 5)

    sizer.AddSpacer(10)

    # Scroll panel for icons
    scroll = wx.ScrolledWindow(dialog)
    scroll.SetScrollRate(0, 20)
    scroll_sizer = wx.BoxSizer(wx.VERTICAL)

    # Icon candidates with different styles
    icon_configs = [
        # Arrows
        ("arrow.right", "Arrow Right"),
        ("arrow.right.circle", "Arrow Right Circle"),
        ("arrow.right.circle.fill", "Arrow Right Circle Fill"),
        ("arrow.forward", "Arrow Forward"),
        ("arrow.forward.circle", "Arrow Forward Circle"),
        ("arrow.forward.circle.fill", "Arrow Forward Circle Fill"),

        # Chevrons
        ("chevron.right", "Chevron Right (current)"),
        ("chevron.right.circle", "Chevron Right Circle"),
        ("chevron.right.circle.fill", "Chevron Right Circle Fill"),
        ("chevron.forward", "Chevron Forward"),
        ("chevron.forward.circle", "Chevron Forward Circle"),
        ("chevron.forward.circle.fill", "Chevron Forward Circle Fill"),

        # Triangles
        ("arrowtriangle.right", "Arrow Triangle Right"),
        ("arrowtriangle.right.fill", "Arrow Triangle Right Fill"),
        ("arrowtriangle.right.circle", "Arrow Triangle Right Circle"),
        ("arrowtriangle.right.circle.fill", "Arrow Triangle Right Circle Fill"),
        ("play.fill", "Play Fill"),
        ("play.circle", "Play Circle"),
        ("play.circle.fill", "Play Circle Fill"),

        # Shapes
        ("circle.fill", "Circle Fill"),
        ("smallcircle.filled.circle", "Small Circle in Circle"),
        ("largecircle.fill.circle", "Large Circle Fill"),
        ("record.circle", "Record Circle"),
        ("record.circle.fill", "Record Circle Fill"),
        ("diamond.fill", "Diamond Fill"),
        ("star.fill", "Star Fill"),

        # Other indicators
        ("checkmark", "Checkmark"),
        ("checkmark.circle", "Checkmark Circle"),
        ("checkmark.circle.fill", "Checkmark Circle Fill"),
        ("location.fill", "Location Fill"),
        ("scope", "Scope"),
    ]

    # Colors to test
    colors = [
        ("#000000", "Black"),
        ("#007AFF", "Blue"),
        ("#FF9500", "Orange"),
    ]

    for symbol_name, label in icon_configs:
        row = wx.Panel(scroll)
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Label
        text = wx.StaticText(row, label=f"{label}", size=(220, -1))
        text.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        row_sizer.Add(text, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        # Show icon in different colors
        for color_hex, color_name in colors:
            bitmap = load_sf_symbol(symbol_name, 10, color_hex)
            if bitmap:
                icon_panel = wx.Panel(row, size=(40, 20))
                icon_panel.SetBackgroundColour("#E0E0E0")  # Gray background like review panel
                icon_sizer = wx.BoxSizer(wx.HORIZONTAL)
                icon_bitmap = wx.StaticBitmap(icon_panel, bitmap=bitmap)
                icon_sizer.Add(icon_bitmap, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
                icon_panel.SetSizer(icon_sizer)
                row_sizer.Add(icon_panel, 0, wx.RIGHT, 5)
            else:
                placeholder = wx.StaticText(row, label="[?]", size=(40, -1))
                placeholder.SetBackgroundColour("#E0E0E0")
                row_sizer.Add(placeholder, 0, wx.RIGHT, 5)

        # SF Symbol name (for copying)
        sf_name = wx.StaticText(row, label=f'"{symbol_name}"', size=(250, -1))
        sf_name.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        sf_name.SetForegroundColour("#666666")
        row_sizer.Add(sf_name, 0, wx.ALIGN_CENTER_VERTICAL)

        row.SetSizer(row_sizer)
        scroll_sizer.Add(row, 0, wx.ALL, 3)

    scroll.SetSizer(scroll_sizer)
    sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 10)

    # Close button
    close_btn = wx.Button(dialog, wx.ID_OK, "Close")
    close_btn.Bind(wx.EVT_BUTTON, lambda e: dialog.EndModal(wx.ID_OK))
    sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)

    dialog.SetSizer(sizer)
    dialog.CenterOnScreen()
    dialog.ShowModal()
    dialog.Destroy()
    app.MainLoop()


if __name__ == "__main__":
    create_selection_icon_picker()
