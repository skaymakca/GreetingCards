"""Deterministic pools and configuration constants for spec generation."""

from __future__ import annotations

import math

HOLIDAYS: list[str] = [
    "Christmas",
    "Hanukkah",
    "New Year",
    "Thanksgiving",
    "Easter",
    "Diwali",
    "Eid",
    "Kwanzaa",
    "Chinese New Year",
    "Season's Greetings",
    "Valentine's Day",
    "Fourth of July",
]

VISUAL_STYLES: list[str] = [
    # Aesthetic
    "minimalist",
    "ornate",
    "playful",
    "vintage",
    "typography",
    "traditional",
    "rustic",
    "whimsical",
    "elegant",
    "bold_graphic",
    "watercolor",
    # Layout
    "photo_card",
    "collage",
    "modern_grid",
    "full_bleed",
    "polaroid",
    "border_frame",
]

FILENAME_TEMPLATES: list[str] = [
    "IMG_{digits4}.pdf",
    "Scan {date} at {time}.pdf",
    "{holiday} Card - {family_name} Family.pdf",
    "holiday_card_{year}.pdf",
    "Photo {month_day_year}, {time12}.pdf",
    "{family_name}_{holiday_lower}_{year}.pdf",
    "Document {digits2}.pdf",
    "card_{digits4}_{family_name_lower}.pdf",
]

# (hint_string, weight)
FAMILY_SIZE_HINTS: list[tuple[str, float]] = [
    ("couple (2 adults, no children)", 0.255),
    ("small family (2 adults, 1-2 children)", 0.357),
    ("single parent (1 adult, 2-3 children)", 0.114),
    ("large family (2 adults, 3-4 children)", 0.204),
    ("family with pet (2 adults, 1-2 children, 1 pet)", 0.07),
]
assert math.isclose(sum(w for _, w in FAMILY_SIZE_HINTS), 1.0)  # nosec B101

# (back_page_type, weight)
BACK_PAGE_TYPES: list[tuple[str, float]] = [
    ("blurb", 0.25),
    ("photo", 0.75),
]
assert math.isclose(sum(w for _, w in BACK_PAGE_TYPES), 1.0)  # nosec B101

# (back_photo_mode, weight) — only for photo-type back pages
BACK_PHOTO_MODES: list[tuple[str, float]] = [
    ("single", 0.40),
    ("collage", 0.60),
]
assert math.isclose(sum(w for _, w in BACK_PHOTO_MODES), 1.0)  # nosec B101

MAX_RETRIES = 3
