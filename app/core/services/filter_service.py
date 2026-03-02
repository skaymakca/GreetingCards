"""Stateless pure filter functions for card lists.

Extracted from FilterMixin to separate business logic from the view layer.
These are pure functions — no state, no UI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.models.card import CardResult, Confidence


class FilterCategory(Enum):
    """Confidence-based filter categories for the sidebar."""

    ALL = "all"
    HIGH = "high"
    MANUAL = "manual"
    NEEDS_REVIEW = "needs_review"
    ERRORS = "errors"


def count_by_category(cards: list[CardResult]) -> dict[str, int]:
    """Count cards per confidence category. Keys match FilterCategory values."""
    return {
        FilterCategory.ALL.value: len(cards),
        FilterCategory.MANUAL.value: sum(1 for c in cards if c.confidence == Confidence.MANUAL),
        FilterCategory.HIGH.value: sum(1 for c in cards if c.confidence == Confidence.HIGH),
        FilterCategory.NEEDS_REVIEW.value: sum(1 for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW)),
        FilterCategory.ERRORS.value: sum(1 for c in cards if c.error or c.confidence == Confidence.NONE),
    }


def count_by_folder(cards: list[CardResult], folder_keys: list[str]) -> dict[str, int]:
    """Count cards per folder. Keys are str(path.parent) matching apply_folder_filters."""
    counts: dict[str, int] = {"all_folders": len(cards)}
    for key in folder_keys:
        folder_path = Path(key)
        counts[key] = sum(1 for c in cards if any(p.parent == folder_path for p in c.file_paths))
    return counts


def search_filter(cards: list[CardResult], query: str) -> list[CardResult]:
    """Filter cards by search query (matches filename and family_name).

    Args:
        cards: List of cards to filter
        query: Search query string (case-insensitive)

    Returns:
        Filtered list of cards matching the query. Returns all cards if query is empty.
    """
    query = query.lower().strip()
    if not query:
        return cards
    return [c for c in cards if query in c.filename.lower() or query in c.family_name.lower()]


def apply_folder_filters(cards: list[CardResult], folder_keys: list[str]) -> list[CardResult]:
    """Filter cards by source folder.

    Args:
        cards: List of cards to filter
        folder_keys: Selected folder filter keys. "all_folders" means no filtering.

    Returns:
        Filtered list of cards from selected folders.
    """
    if "all_folders" in folder_keys:
        return cards
    folder_set = set(folder_keys)
    return [c for c in cards if any(str(p.parent) in folder_set for p in c.file_paths)]


def apply_category_filters(cards: list[CardResult], category_keys: list[str]) -> list[CardResult]:
    """Filter cards by confidence category.

    Args:
        cards: List of cards to filter
        category_keys: Selected category filter keys. "all" means no category filtering.

    Returns:
        Filtered list of cards (unsorted — caller decides display order).
    """
    if FilterCategory.ALL.value not in category_keys:
        filtered: list[CardResult] = []
        for filter_key in category_keys:
            if filter_key == FilterCategory.MANUAL.value:
                filtered.extend(c for c in cards if c.confidence == Confidence.MANUAL)
            elif filter_key == FilterCategory.HIGH.value:
                filtered.extend(c for c in cards if c.confidence == Confidence.HIGH)
            elif filter_key == FilterCategory.NEEDS_REVIEW.value:
                filtered.extend(c for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW))
            elif filter_key == FilterCategory.ERRORS.value:
                filtered.extend(c for c in cards if c.error or c.confidence == Confidence.NONE)
        cards = list({c.id: c for c in filtered}.values())
    return cards


@dataclass
class FilteredView:
    """Result of computing the filtered display state."""

    display_cards: list[CardResult]
    category_counts: dict[str, int]
    folder_counts: dict[str, int]
    filters_were_reset: bool


def compute_filtered_view(
    all_cards: list[CardResult],
    search_query: str,
    category_filters: list[str],
    folder_filters: list[str],
    folder_keys: list[str],
) -> FilteredView:
    """Compute the filtered view using the cross-filter pipeline.

    Implements the two-pass algorithm:
    1. Apply search filter
    2. Cross-compute counts (folder-filtered -> category counts,
       category-filtered -> folder counts)
    3. Apply both filters for display
    4. Auto-reset category filters if display is empty but search has results

    Args:
        all_cards: All loaded cards
        search_query: Current search text
        category_filters: Selected category filter keys
        folder_filters: Selected folder filter keys
        folder_keys: All available folder keys for count computation

    Returns:
        FilteredView with display cards, counts, and reset flag.
    """
    search_cards = search_filter(all_cards, search_query)

    # First pass: cross-filtered counts
    folder_filtered = apply_folder_filters(search_cards, folder_filters)
    category_filtered = apply_category_filters(search_cards, category_filters)
    category_counts = count_by_category(folder_filtered)
    folder_counts = count_by_folder(category_filtered, folder_keys)

    # Compute display
    display_cards = apply_category_filters(folder_filtered, category_filters)

    # Auto-reset: if display is empty but search has results, reset categories
    filters_were_reset = False
    if not display_cards and search_cards:
        category_filters = [FilterCategory.ALL.value]
        folder_filtered = apply_folder_filters(search_cards, folder_filters)
        display_cards = apply_category_filters(folder_filtered, category_filters)
        category_counts = count_by_category(folder_filtered)
        folder_counts = count_by_folder(display_cards, folder_keys)
        filters_were_reset = True

    # Sort display cards alphabetically by filename for stable display order
    display_cards = sorted(display_cards, key=lambda c: c.filename.lower())

    return FilteredView(
        display_cards=display_cards,
        category_counts=category_counts,
        folder_counts=folder_counts,
        filters_were_reset=filters_were_reset,
    )
