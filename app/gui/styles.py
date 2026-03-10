"""wxPython style definitions for the application.

Colors are wx.Colour objects, fonts are wx.Font objects.
"""

import wx


def parse_hex_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse a hex color string to (R, G, B) integer components (0–255).

    Args:
        hex_color: Hex color string like "#FFFFFF" or "FFFFFF"
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return r, g, b


class Color:
    """Color palette for the application (wx.Colour objects).

    Mode-dependent colors (BG_*, TEXT_*, BORDER) are updated by refresh().
    Semantic colors (ACCENT, SUCCESS, etc.) are fixed — they work in both modes.
    """

    # Backgrounds (light defaults — refresh() updates for dark mode)
    BG_PRIMARY = wx.Colour(255, 255, 255)  # #FFFFFF
    BG_SECONDARY = wx.Colour(245, 245, 247)  # #F5F5F7
    BG_SELECTED = wx.Colour(212, 228, 247)  # #D4E4F7

    # Text (light defaults)
    TEXT_PRIMARY = wx.Colour(29, 29, 31)  # #1D1D1F
    TEXT_SECONDARY = wx.Colour(110, 110, 115)  # #6E6E73

    # Borders (light default)
    BORDER = wx.Colour(0xDD, 0xDD, 0xDD)  # #DDDDDD

    # Semantic colors (unchanged across modes)
    ACCENT = wx.Colour(0, 122, 255)  # #007AFF
    SUCCESS = wx.Colour(52, 199, 89)  # #34C759
    WARNING = wx.Colour(255, 149, 0)  # #FF9500
    ERROR = wx.Colour(255, 59, 48)  # #FF3B30
    MANUAL_BLUE = wx.Colour(30, 144, 255)  # #1E90FF

    @classmethod
    def refresh(cls) -> None:
        """Reassign mode-dependent colors for current appearance.

        Call at startup and whenever the system appearance changes.
        Semantic colors are not affected.
        """
        from app.gui.appearance import is_dark_mode

        if is_dark_mode():
            cls.BG_PRIMARY = wx.Colour(30, 30, 30)  # #1E1E1E
            cls.BG_SECONDARY = wx.Colour(44, 44, 46)  # #2C2C2E
            cls.BG_SELECTED = wx.Colour(44, 62, 80)  # #2C3E50
            cls.TEXT_PRIMARY = wx.Colour(230, 230, 230)  # #E6E6E6
            cls.TEXT_SECONDARY = wx.Colour(152, 152, 157)  # #98989D
            cls.BORDER = wx.Colour(56, 56, 58)  # #38383A
        else:
            cls.BG_PRIMARY = wx.Colour(255, 255, 255)
            cls.BG_SECONDARY = wx.Colour(245, 245, 247)
            cls.BG_SELECTED = wx.Colour(212, 228, 247)
            cls.TEXT_PRIMARY = wx.Colour(29, 29, 31)
            cls.TEXT_SECONDARY = wx.Colour(110, 110, 115)
            cls.BORDER = wx.Colour(0xDD, 0xDD, 0xDD)

    @classmethod
    def icon_hex(cls) -> str:
        """Return the appropriate SF Symbol icon tint for current mode."""
        from app.gui.appearance import is_dark_mode

        return "#E6E6E6" if is_dark_mode() else "#1D1D1F"

    @staticmethod
    def from_hex(hex_color: str) -> wx.Colour:
        """Convert hex color string to wx.Colour.

        Args:
            hex_color: Hex color string like "#FFFFFF" or "FFFFFF"

        Returns:
            wx.Colour object
        """
        r, g, b = parse_hex_rgb(hex_color)
        return wx.Colour(r, g, b)


# noinspection PyPep8Naming
class Font:
    """Font definitions for the application (factory methods).

    Use class methods to create fonts on demand (avoids needing wx.App at import time).
    Uppercase method names (TITLE, HEADING, etc.) are used by convention for style factories.
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

    # Splitter sash position
    CONTENT_SASH_GRAVITY = 0.55  # Cards panel gets slightly more space

    # Drag highlight drawing
    HIGHLIGHT_WIDTH = 3
    HIGHLIGHT_RADIUS = 6
    HIGHLIGHT_INSET = 1.5

    # Drop overlay
    DROP_BG_SCALE = 0.5  # Background image area as fraction of overlay
    DROP_IMG_SHIFT = 0.06  # Upward shift of background image
    DROP_TEXT_GAP = 2  # Pixel gap between primary/secondary text

    # Preview panel
    PREVIEW_BUTTON_SIZE = (28, 28)
    PREVIEW_FIT_BUTTON_SIZE = (42, 28)
    PAGE_LABEL_MIN_WIDTH = 50
    ZOOM_LABEL_MIN_WIDTH = 40
    MIN_CANVAS_SIZE = 10
    ERROR_TEXT_MARGIN = 40

    # Review panel
    LEGEND_ROW_SPACING = 6
    LEGEND_ICON_GAP = 2
    LEGEND_POPUP_GAP = 2
    FILE_PATHS_MIN_HEIGHT = 100

    # Dialogs
    DIALOG_PADDING = 20
    DIALOG_SECTION_GAP = 10
    DIALOG_HEADER_GAP = 4
    DIALOG_CONTENT_GAP = 12
    DIALOG_BTN_GAP = 8
    DIALOG_SCROLLBAR_WIDTH = 20
    DIALOG_STATUS_COL_WIDTH = 100
    DIALOG_RESULT_COL_WIDTH = 140
    DIALOG_RENAME_WIDTH = 700
    DIALOG_ERROR_WIDTH = 650
    DIALOG_COMPLETION_WIDTH = 650
    PROGRESS_GAUGE_WIDTH = 350

    # Preview panel warnings
    PREVIEW_MODIFIER_POLL_MS = 50
    PREVIEW_WARNING_FONT_SIZE = 32
    PREVIEW_WARNING_LABEL_OFFSET = 30
    PREVIEW_WARNING_TEXT_OFFSET = 20
    PREVIEW_WARNING_LINE_SPACING = 4

    # HTML viewer toolbar
    HTML_VIEWER_TOOL_BITMAP_SIZE = wx.Size(24, 24)
    HTML_VIEWER_LABEL_WIDTH = 80
    HTML_VIEWER_SEARCH_MIN_WIDTH = 150
    HTML_VIEWER_TOOL_WIDTH_EST = 36
    HTML_VIEWER_TOOLBAR_MARGIN = 24
    HTML_VIEWER_NUM_TOOLS = 5
    HTML_VIEWER_MIN_SEARCH_LEN = 3
    HTML_VIEWER_DEBOUNCE_MS = 200

    # Progress strip
    PROGRESS_STRIP_V_PAD = 4
    PROGRESS_STRIP_LABEL_PAD = 12
    PROGRESS_STRIP_GAUGE_PAD = 8
    PROGRESS_STRIP_COUNT_PAD = 20

    # Timing (ms)
    DEBOUNCE_MS = 1000
    INFO_DISMISS_MS = 4000
