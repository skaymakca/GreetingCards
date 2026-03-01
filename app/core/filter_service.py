"""Stateless pure filter functions for card lists.

Extracted from FilterMixin to separate business logic from the view layer.
These are pure functions — no state, no UI dependencies.
"""

from __future__ import annotations

from pathlib import Path

from app.models.card import CardResult, Confidence


def count_by_category(cards: list[CardResult]) -> dict[str, int]:
    """Count cards per confidence category. Keys match apply_category_filters."""
    return {
        "all": len(cards),
        "manual": sum(1 for c in cards if c.confidence == Confidence.MANUAL),
        "high": sum(1 for c in cards if c.confidence == Confidence.HIGH),
        "needs_review": sum(1 for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW)),
        "errors": sum(1 for c in cards if c.error or c.confidence == Confidence.NONE),
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
    """Filter cards by confidence category and sort by filename.

    Args:
        cards: List of cards to filter
        category_keys: Selected category filter keys. "all" means no category filtering.

    Returns:
        Filtered and sorted list of cards. Always sorted by filename (case-insensitive).
    """
    if "all" not in category_keys:
        filtered: list[CardResult] = []
        for filter_key in category_keys:
            if filter_key == "manual":
                filtered.extend(c for c in cards if c.confidence == Confidence.MANUAL)
            elif filter_key == "high":
                filtered.extend(c for c in cards if c.confidence == Confidence.HIGH)
            elif filter_key == "needs_review":
                filtered.extend(c for c in cards if c.confidence in (Confidence.MEDIUM, Confidence.LOW))
            elif filter_key == "errors":
                filtered.extend(c for c in cards if c.error or c.confidence == Confidence.NONE)
        cards = list({c.id: c for c in filtered}.values())
    return sorted(cards, key=lambda c: c.filename.lower())
