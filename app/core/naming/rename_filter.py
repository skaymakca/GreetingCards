"""Rename result filtering utilities shared across GUI and CLI paths."""

from pathlib import Path

from app.models.card import RenameOutcome, RenameResult

# Outcomes indicating a rename result is resolved (path moved or already correct)
RESOLVED_OUTCOMES: frozenset[RenameOutcome] = frozenset({RenameOutcome.RENAMED, RenameOutcome.ALREADY_CORRECT})


def filter_completed_renames(results: list[RenameResult]) -> set[Path]:
    """Return the new_paths for results that are fully resolved.

    A result is resolved when ``success`` is True and its outcome is one of
    the :data:`RESOLVED_OUTCOMES` values.

    Args:
        results: Rename operation results to inspect.

    Returns:
        Set of ``new_path`` values for resolved results.
    """
    return {r.new_path for r in results if r.success and r.outcome in RESOLVED_OUTCOMES}
