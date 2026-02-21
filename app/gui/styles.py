"""wxPython style definitions for the application.

Colors are wx.Colour objects, fonts are wx.Font objects.
"""

import wx


class Color:
    """Color palette for the application (wx.Colour objects)."""

    # Backgrounds
    BG_PRIMARY = wx.Colour(255, 255, 255)      # #FFFFFF
    BG_SECONDARY = wx.Colour(245, 245, 247)    # #F5F5F7
    BG_SELECTED = wx.Colour(212, 228, 247)     # #D4E4F7

    # Text
    TEXT_PRIMARY = wx.Colour(29, 29, 31)       # #1D1D1F
    TEXT_SECONDARY = wx.Colour(110, 110, 115)  # #6E6E73

    # Semantic colors
    ACCENT = wx.Colour(0, 122, 255)            # #007AFF
    SUCCESS = wx.Colour(52, 199, 89)           # #34C759
    WARNING = wx.Colour(255, 149, 0)           # #FF9500
    ERROR = wx.Colour(255, 59, 48)             # #FF3B30
    MANUAL_BLUE = wx.Colour(30, 144, 255)      # #1E90FF

    @staticmethod
    def from_hex(hex_color: str) -> wx.Colour:
        """Convert hex color string to wx.Colour.

        Args:
            hex_color: Hex color string like "#FFFFFF" or "FFFFFF"

        Returns:
            wx.Colour object
        """
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return wx.Colour(r, g, b)


class Font:
    """Font definitions for the application (factory methods).

    Use class methods to create fonts on demand (avoids needing wx.App at import time).
    """

    FAMILY = "Helvetica Neue"

    @staticmethod
    def TITLE() -> wx.Font:
        """Create title font (16pt, bold)."""
        return wx.Font(wx.FontInfo(16).FaceName(Font.FAMILY).Bold())

    @staticmethod
    def HEADING() -> wx.Font:
        """Create heading font (13pt, bold)."""
        return wx.Font(wx.FontInfo(13).FaceName(Font.FAMILY).Bold())

    @staticmethod
    def BODY() -> wx.Font:
        """Create body font (12pt, normal)."""
        return wx.Font(wx.FontInfo(12).FaceName(Font.FAMILY))

    @staticmethod
    def SECTION_HEADER() -> wx.Font:
        """Create section header font (11pt, bold)."""
        return wx.Font(wx.FontInfo(11).FaceName(Font.FAMILY).Bold())

    @staticmethod
    def SMALL() -> wx.Font:
        """Create small font (11pt, normal)."""
        return wx.Font(wx.FontInfo(11).FaceName(Font.FAMILY))

    @staticmethod
    def MONO() -> wx.Font:
        """Create monospace font (11pt, Menlo)."""
        return wx.Font(wx.FontInfo(11).FaceName("Menlo").Family(wx.FONTFAMILY_TELETYPE))

    @staticmethod
    def from_tuple(font_tuple: tuple) -> wx.Font:
        """Convert font tuple to wx.Font.

        Args:
            font_tuple: Tuple like ("Helvetica Neue", 12) or ("Helvetica Neue", 12, "bold")

        Returns:
            wx.Font object
        """
        family_name = font_tuple[0]
        size = font_tuple[1]
        is_bold = len(font_tuple) > 2 and font_tuple[2] == "bold"

        # Create font info
        font_info = wx.FontInfo(size).FaceName(family_name)

        # Determine font family
        if "Mono" in family_name or "Menlo" in family_name or "Courier" in family_name:
            font_info = font_info.Family(wx.FONTFAMILY_TELETYPE)

        if is_bold:
            font_info = font_info.Bold()

        return wx.Font(font_info)


class Layout:
    """Layout dimensions for the application."""

    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 750
    PREVIEW_WIDTH = 450
    ROW_HEIGHT = 36
    TOOLBAR_HEIGHT = 90
    PAD = 10

    # Review panel column widths
    DOT_COL_WIDTH = 30
    FILENAME_COL_WIDTH = 280
    FAMILY_NAME_COL_WIDTH = 200
    FILE_PATHS_COL_WIDTH = 400

    # Component sizes
    TOOLBAR_ICON_SIZE = 24
    TOOLBAR_ICON_POINTS = 16
    ACTION_ICON_SIZE = 9
    BUTTON_HEIGHT = 28
    MIN_PANE_SIZE = 100
    SIDEBAR_WIDTH = 175
    CONTENT_MIN_PANE = 200
    SEARCH_WIDTH = 200
    YEAR_WIDTH = 60
    MIN_FRAME_SIZE = (800, 500)

    # Drag highlight drawing
    HIGHLIGHT_WIDTH = 3
    HIGHLIGHT_RADIUS = 6
    HIGHLIGHT_INSET = 1.5

    # Timing (ms)
    DEBOUNCE_MS = 1000
    INFO_DISMISS_MS = 4000
