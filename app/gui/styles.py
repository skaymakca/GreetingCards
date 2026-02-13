# Colors
BG_PRIMARY = "#FFFFFF"
BG_SECONDARY = "#F5F5F7"
BG_SELECTED = "#D4E4F7"
TEXT_PRIMARY = "#1D1D1F"
TEXT_SECONDARY = "#6E6E73"
ACCENT = "#007AFF"
SUCCESS = "#34C759"
WARNING = "#FF9500"
ERROR = "#FF3B30"
MANUAL_BLUE = "#1E90FF"  # Dodger Blue

# Confidence dot colors
CONFIDENCE_COLORS = {
    "high": SUCCESS,
    "medium": WARNING,
    "low": ERROR,
    "manual": MANUAL_BLUE,
    "none": TEXT_SECONDARY,
}

# Confidence tooltip descriptions
CONFIDENCE_TOOLTIPS = {
    "high": "High confidence — strong pattern match or AI result",
    "medium": "Medium confidence — partial pattern match",
    "low": "Low confidence — weak/fallback match",
    "manual": "Manually entered name",
    "none": "No name extracted",
}

# Fonts
FONT_FAMILY = "Helvetica Neue"
FONT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_HEADING = (FONT_FAMILY, 13, "bold")
FONT_BODY = (FONT_FAMILY, 12)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_MONO = ("Menlo", 11)

# Dimensions
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 750
PREVIEW_WIDTH = 450
ROW_HEIGHT = 36
TOOLBAR_HEIGHT = 90
PAD = 10
