"""Rename orchestration service.

Consolidates rename-plan execution and path-mapping updates that were
previously duplicated in main_window.py and apple_events_mixin.py.
"""

from __future__ import annotations

from app.core.card_store import CardStore
from app.core.naming.rename_filter import RESOLVED_MESSAGES
from app.core.naming.renamer import build_rename_plan, execute_rename_plan
from app.models.card import CardResult, RenameResult


class RenameService:
    """Execute rename plans and keep CardStore path mappings in sync."""

    def __init__(self, store: CardStore) -> None:
        self._store = store

    def execute(self, plan: list) -> list[RenameResult]:
        """Execute a rename plan and update store path mappings.

        Calls ``execute_rename_plan()`` then updates the store for every
        successfully resolved rename (message in RESOLVED_MESSAGES).
        """
        results = execute_rename_plan(plan)
        for result in results:
            if result.success and result.message in RESOLVED_MESSAGES:
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
