class Color:
    """Color palette for the application."""
    # Backgrounds
    BG_PRIMARY = "#FFFFFF"
    BG_SECONDARY = "#F5F5F7"
    BG_SELECTED = "#D4E4F7"

    # Text
    TEXT_PRIMARY = "#1D1D1F"
    TEXT_SECONDARY = "#6E6E73"

    # Semantic colors
    ACCENT = "#007AFF"
    SUCCESS = "#34C759"
    WARNING = "#FF9500"
    ERROR = "#FF3B30"
    MANUAL_BLUE = "#1E90FF"


class Font:
    """Font definitions for the application."""
    FAMILY = "Helvetica Neue"
    TITLE = (FAMILY, 16, "bold")
    HEADING = (FAMILY, 13, "bold")
    BODY = (FAMILY, 12)
    SMALL = (FAMILY, 11)
    MONO = ("Menlo", 11)


class Layout:
    """Layout dimensions for the application."""
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 750
    PREVIEW_WIDTH = 450
    ROW_HEIGHT = 36
    TOOLBAR_HEIGHT = 90
    PAD = 10
