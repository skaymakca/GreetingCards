"""Generated field assignment and filename formatting helpers."""

from __future__ import annotations

import random
from typing import Any

from scripts.generate_sample_cards.models import FamilyMember
from scripts.generate_sample_cards.spec_generators.constants import (
    BACK_PAGE_TYPES,
    BACK_PHOTO_MODES,
    FAMILY_SIZE_HINTS,
    FILENAME_TEMPLATES,
    HOLIDAYS,
    VISUAL_STYLES,
)


def assign_generated_fields(count: int) -> list[dict[str, Any]]:
    """Build a list of dicts with all Python-determined fields."""
    rng = random.Random()  # nosec B311

    # Round-robin + shuffle for holidays and styles
    holidays = (HOLIDAYS * ((count // len(HOLIDAYS)) + 1))[:count]
    rng.shuffle(holidays)

    styles = (VISUAL_STYLES * ((count // len(VISUAL_STYLES)) + 1))[:count]
    rng.shuffle(styles)

    # Weighted random picks
    fn_templates = FILENAME_TEMPLATES
    fs_hints, fs_weights = zip(*FAMILY_SIZE_HINTS, strict=True)
    bp_types, bp_weights = zip(*BACK_PAGE_TYPES, strict=True)
    bpm_modes, bpm_weights = zip(*BACK_PHOTO_MODES, strict=True)

    cards: list[dict[str, Any]] = []
    for i in range(count):
        page_count = 2 if rng.random() < 0.80 else 1
        back_page_type: str | None = None
        back_photo_mode: str | None = None
        if page_count == 2:
            back_page_type = rng.choices(bp_types, weights=bp_weights)[0]
            if back_page_type == "photo":
                back_photo_mode = rng.choices(bpm_modes, weights=bpm_weights)[0]

        cards.append(
            {
                "holiday": holidays[i],
                "visual_style": styles[i],
                "filename_template": rng.choice(fn_templates),
                "page_count": page_count,
                "back_page_type": back_page_type,
                "back_photo_mode": back_photo_mode,
                "family_size_hint": rng.choices(fs_hints, weights=fs_weights)[0],
            }
        )
    return cards


def fill_filename(template: str, family_name: str, holiday: str, rng: random.Random) -> str:
    """Resolve a filename template with actual values."""
    year = str(rng.randint(2022, 2025))
    digits4 = str(rng.randint(1000, 9999))
    digits2 = str(rng.randint(10, 99))
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    hour = rng.randint(8, 20)
    minute = rng.randint(0, 59)
    date = f"{year}-{month:02d}-{day:02d}"
    time_24 = f"{hour}.{minute:02d} {'AM' if hour < 12 else 'PM'}"
    time_12 = f"{hour if hour <= 12 else hour - 12} {minute:02d} {'AM' if hour < 12 else 'PM'}"
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_day_year = f"{months[month - 1]} {day} {year}"

    return (
        template.replace("{digits4}", digits4)
        .replace("{digits2}", digits2)
        .replace("{date}", date)
        .replace("{time}", time_24)
        .replace("{time12}", time_12)
        .replace("{month_day_year}", month_day_year)
        .replace("{holiday}", holiday)
        .replace("{holiday_lower}", holiday.lower().replace(" ", "_").replace("'", ""))
        .replace("{family_name}", family_name)
        .replace("{family_name_lower}", family_name.lower())
        .replace("{year}", year)
    )


def build_family_members(raw_members: list[dict[str, Any]]) -> list[FamilyMember]:
    """Convert raw dicts from Claude into FamilyMember dataclasses."""
    return [
        FamilyMember(
            first_name=str(m.get("first_name", "")),
            role=str(m.get("role", "")),
            age=int(m["age"]) if m.get("age") is not None else None,
        )
        for m in raw_members
    ]
