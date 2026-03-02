"""Rename orchestration service.

Consolidates rename-plan execution and path-mapping updates that were
previously duplicated in main_window.py and apple_events_mixin.py.
"""

from __future__ import annotations

from pathlib import Path

from app.core.card_store import CardStore
from app.core.naming.filename_safety import INVALID_FILENAME_CHARS as _INVALID_FILENAME_CHARS
from app.core.naming.rename_filter import RESOLVED_OUTCOMES, filter_completed_renames
from app.core.naming.renamer import build_rename_plan, build_target_filename, execute_rename_plan, validate_year
from app.models.card import (
    CardResult,
    RenamePlanItem,
    RenameResult,
)


class RenameService:
    """Execute rename plans and keep CardStore path mappings in sync."""

    INVALID_FILENAME_CHARS: frozenset[str] = _INVALID_FILENAME_CHARS

    def __init__(self, store: CardStore) -> None:
        self._store = store

    @staticmethod
    def validate_year(year_str: str) -> bool:
        """Return True if year_str is a valid 4-digit year.

        Wraps ``validate_year()`` so callers don't import core
        naming internals directly.
        """
        return validate_year(year_str)

    @staticmethod
    def target_filename(card: CardResult, year: str) -> str:
        """Build the target filename for *card* given a *year*.

        Wraps ``build_target_filename()`` so callers don't import
        core naming internals directly.
        """
        return build_target_filename(card, year)

    @staticmethod
    def build_plan(cards: list[CardResult], year: str) -> list[RenamePlanItem]:
        """Build a rename plan from cards and year.

        Wraps ``build_rename_plan()`` so callers don't import core
        naming internals directly.
        """
        return build_rename_plan(cards, year)

    def execute(self, plan: list) -> list[RenameResult]:
        """Execute a rename plan and update store path mappings.

        Calls ``execute_rename_plan()`` then updates the store for every
        successfully resolved rename (outcome in RESOLVED_OUTCOMES).
        """
        results = execute_rename_plan(plan)
        for result in results:
            if result.success and result.outcome in RESOLVED_OUTCOMES:
                self._store.update_path_mapping(result.old_path, result.new_path)
        return results

    def rename_card(self, card: CardResult, new_name: str, year: str) -> list[RenameResult]:
        """Rename a single card on disk (used by Apple Events scripting).

        Temporarily sets the card's manual_override to *new_name*, builds a
        plan, executes it, and updates path mappings.  On total failure the
        card's name fields are rolled back to their previous values.
        """
        # Snapshot current state for rollback
        old_override = card.manual_override
        old_family = card.family_name
        old_method = card.method
        old_confidence = card.confidence

        card.manual_override = new_name

        plan = build_rename_plan([card], year)
        results = self.execute(plan)

        # Rollback on total failure
        if not any(r.success for r in results):
            card.manual_override = old_override
            card.family_name = old_family
            card.method = old_method
            card.confidence = old_confidence

        return results

    @staticmethod
    def get_completed_paths(results: list[RenameResult]) -> set[Path]:
        """Return paths for fully resolved rename results.

        Wraps ``filter_completed_renames()`` so callers don't import
        core naming internals directly.
        """
        return filter_completed_renames(results)
