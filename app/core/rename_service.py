"""Rename orchestration service.

Consolidates rename-plan execution and path-mapping updates that were
previously duplicated in main_window.py and apple_events_mixin.py.
"""

from __future__ import annotations

from pathlib import Path

from app.core.card_store import CardStore
from app.core.naming.rename_filter import RESOLVED_MESSAGES, filter_completed_renames
from app.core.naming.renamer import build_rename_plan, execute_rename_plan
from app.models.card import (
    STATUS_DUPLICATE,
    STATUS_OK,
    STATUS_SKIP_ERROR,
    STATUS_SKIP_NO_NAME,
    STATUS_SKIP_SAME,
    CardResult,
    RenamePlanItem,
    RenameResult,
)


class RenameService:
    """Execute rename plans and keep CardStore path mappings in sync."""

    def __init__(self, store: CardStore) -> None:
        self._store = store

    @staticmethod
    def build_plan(cards: list[CardResult], year: str) -> list[RenamePlanItem]:
        """Build a rename plan from cards and year.

        Wraps ``build_rename_plan()`` so GUI callers don't import core
        naming internals directly.
        """
        return build_rename_plan(cards, year)

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

    @staticmethod
    def summarize_plan(plan: list[RenamePlanItem]) -> dict[str, int]:
        """Summarize a rename plan by status counts.

        Returns dict with keys: ok, duplicate, error, skip, directory_count.
        """
        return {
            "ok": sum(1 for item in plan if item.status == STATUS_OK),
            "duplicate": sum(1 for item in plan if item.status == STATUS_DUPLICATE),
            "error": sum(1 for item in plan if item.status == STATUS_SKIP_ERROR),
            "skip": sum(1 for item in plan if item.status in {STATUS_SKIP_NO_NAME, STATUS_SKIP_SAME}),
            "directory_count": len({item.old_path.parent for item in plan}),
        }

    @staticmethod
    def summarize_results(results: list[RenameResult]) -> dict[str, int]:
        """Summarize rename results by outcome.

        Returns dict with keys: renamed, skipped, errors, directory_count.
        """
        return {
            "renamed": sum(1 for r in results if r.success and r.message == "Renamed"),
            "skipped": sum(1 for r in results if r.success and r.message != "Renamed"),
            "errors": sum(1 for r in results if not r.success),
            "directory_count": len({(r.new_path if r.success else r.old_path).parent for r in results}),
        }

    @staticmethod
    def format_plan_summary(plan: list[RenamePlanItem]) -> str:
        """Format a rename plan summary as a user-facing string."""
        counts = RenameService.summarize_plan(plan)
        parts = [f"{counts['ok']} rename(s)"]
        if counts["duplicate"]:
            parts.append(f"{counts['duplicate']} duplicate(s)")
        if counts["skip"]:
            parts.append(f"{counts['skip']} skipped")
        if counts["error"]:
            parts.append(f"{counts['error']} error(s)")
        summary = ", ".join(parts)
        if counts["directory_count"] > 1:
            summary += f" across {counts['directory_count']} directories"
        return summary

    @staticmethod
    def format_results_summary(results: list[RenameResult]) -> str:
        """Format rename results summary as a user-facing string."""
        counts = RenameService.summarize_results(results)
        summary = f"{counts['renamed']} renamed, {counts['skipped']} skipped"
        if counts["errors"]:
            summary += f", {counts['errors']} failed"
        return summary

    @staticmethod
    def get_completed_paths(results: list[RenameResult]) -> set[Path]:
        """Return paths for fully resolved rename results.

        Wraps ``filter_completed_renames()`` so GUI callers don't import
        core naming internals directly.
        """
        return filter_completed_renames(results)
