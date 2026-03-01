"""Stateless pure filter functions for card lists.

Extracted from FilterMixin to separate business logic from the view layer.
These are pure functions — no state, no UI dependencies.
"""

from __future__ import annotations

from app.models.card import CardResult, Confidence


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
