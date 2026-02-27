"""Rename result filtering utilities shared across GUI and CLI paths."""

from pathlib import Path

from app.models.card import RenameResult

# Messages indicating a rename result is resolved (path moved or already correct)
RESOLVED_MESSAGES: frozenset[str] = frozenset({"Renamed", "Already named correctly"})


def filter_completed_renames(results: list[RenameResult]) -> set[Path]:
    """Return the new_paths for results that are fully resolved.

    A result is resolved when ``success`` is True and its message is one of
    the :data:`RESOLVED_MESSAGES` values (either "Renamed" or "Already named
    correctly").

    Args:
        results: Rename operation results to inspect.

    Returns:
        Set of ``new_path`` values for resolved results.
    """
    return {r.new_path for r in results if r.success and r.message in RESOLVED_MESSAGES}
