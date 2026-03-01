"""Tests for RenameService — rename orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.card_store import CardStore
from app.core.rename_service import RenameService
from app.models.card import CardResult, Confidence, RenamePlanItem, RenameResult


def _make_card(
    card_id: int = 0,
    family_name: str = "Smith",
    file_path: str = "/tmp/card.pdf",
    file_hash: str = "hash1",
) -> CardResult:
    """Create a minimal CardResult for testing."""
    return CardResult(
        id=card_id,
        file_paths=[Path(file_path)],
        primary_path=Path(file_path),
        family_name=family_name,
        confidence=Confidence.HIGH,
        method="ocr",
        file_hash=file_hash,
    )


def _make_store(*cards: CardResult) -> CardStore:
    """Create a CardStore populated with the given cards."""
    store = CardStore()
    for card in cards:
        if card.file_hash:
            store._cards_by_hash[card.file_hash] = card
        store._id_to_card[card.id] = card
        for p in card.file_paths:
            store._hash_by_path[p] = card.file_hash
    return store


class TestExecute:
    """Tests for RenameService.execute()."""

    def test_execute_updates_path_mappings_for_renamed(self) -> None:
        """Successful renames should update store path mappings."""
        card = _make_card()
        store = _make_store(card)
        service = RenameService(store)

        old_path = Path("/tmp/card.pdf")
        new_path = Path("/tmp/Holiday Cards 2025 - Smith Family.pdf")

        plan = [RenamePlanItem(old_path, new_path, "ok", card=card)]

        with patch("app.core.rename_service.execute_rename_plan") as mock_exec:
            mock_exec.return_value = [
                RenameResult(old_path, new_path, True, "Renamed", card=card),
            ]
            results = service.execute(plan)

        assert len(results) == 1
        assert results[0].success
        # Path mapping should have been updated
        assert store.get_hash_for_path(new_path) == "hash1"
        assert store.get_hash_for_path(old_path) is None

    def test_execute_skips_path_mapping_for_failures(self) -> None:
        """Failed renames should not update path mappings."""
        card = _make_card()
        store = _make_store(card)
        service = RenameService(store)

        old_path = Path("/tmp/card.pdf")
        new_path = Path("/tmp/Holiday Cards 2025 - Smith Family.pdf")

        plan = [RenamePlanItem(old_path, new_path, "ok", card=card)]

        with patch("app.core.rename_service.execute_rename_plan") as mock_exec:
            mock_exec.return_value = [
                RenameResult(old_path, new_path, False, "Permission denied", card=card),
            ]
            results = service.execute(plan)

        assert len(results) == 1
        assert not results[0].success
        # Original path mapping should remain
        assert store.get_hash_for_path(old_path) == "hash1"
        assert store.get_hash_for_path(new_path) is None

    def test_execute_skips_path_mapping_for_skip_same(self) -> None:
        """Skip-same results (success=True, message='Already named correctly')
        should update path mappings since they are in RESOLVED_MESSAGES."""
        card = _make_card()
        store = _make_store(card)
        service = RenameService(store)

        old_path = Path("/tmp/card.pdf")
        new_path = Path("/tmp/card.pdf")  # Same path

        plan = [RenamePlanItem(old_path, new_path, "skip_same", card=card)]

        with patch("app.core.rename_service.execute_rename_plan") as mock_exec:
            mock_exec.return_value = [
                RenameResult(old_path, new_path, True, "Already named correctly", card=card),
            ]
            results = service.execute(plan)

        assert len(results) == 1
        assert results[0].success


class TestRenameCard:
    """Tests for RenameService.rename_card()."""

    def test_rename_card_sets_override_and_executes(self) -> None:
        """rename_card should set manual_override and execute the plan."""
        card = _make_card(family_name="Smith")
        store = _make_store(card)
        service = RenameService(store)

        with (
            patch("app.core.rename_service.build_rename_plan") as mock_build,
            patch("app.core.rename_service.execute_rename_plan") as mock_exec,
        ):
            mock_build.return_value = []
            mock_exec.return_value = [
                RenameResult(
                    Path("/tmp/card.pdf"),
                    Path("/tmp/Holiday Cards 2025 - Jones Family.pdf"),
                    True,
                    "Renamed",
                    card=card,
                ),
            ]
            results = service.rename_card(card, "Jones", "2025")

        assert len(results) == 1
        assert results[0].success
        # manual_override should be set to new_name
        assert card.manual_override == "Jones"

    def test_rename_card_rollback_on_total_failure(self) -> None:
        """When all results fail, card fields should be rolled back."""
        card = _make_card(family_name="Smith")
        card.manual_override = "Original"
        card.method = "ocr"
        card.confidence = Confidence.HIGH
        store = _make_store(card)
        service = RenameService(store)

        with (
            patch("app.core.rename_service.build_rename_plan") as mock_build,
            patch("app.core.rename_service.execute_rename_plan") as mock_exec,
        ):
            mock_build.return_value = []
            mock_exec.return_value = [
                RenameResult(
                    Path("/tmp/card.pdf"),
                    Path("/tmp/new.pdf"),
                    False,
                    "Permission denied",
                    card=card,
                ),
            ]
            results = service.rename_card(card, "NewName", "2025")

        assert len(results) == 1
        assert not results[0].success
        # Card should be rolled back
        assert card.manual_override == "Original"
        assert card.family_name == "Smith"
        assert card.method == "ocr"
        assert card.confidence == Confidence.HIGH

    def test_rename_card_no_rollback_on_partial_success(self) -> None:
        """When at least one result succeeds, no rollback happens."""
        card = _make_card(family_name="Smith")
        card.file_paths = [Path("/tmp/card1.pdf"), Path("/tmp/card2.pdf")]
        store = _make_store(card)
        service = RenameService(store)

        with (
            patch("app.core.rename_service.build_rename_plan") as mock_build,
            patch("app.core.rename_service.execute_rename_plan") as mock_exec,
        ):
            mock_build.return_value = []
            mock_exec.return_value = [
                RenameResult(Path("/tmp/card1.pdf"), Path("/tmp/new1.pdf"), True, "Renamed", card=card),
                RenameResult(Path("/tmp/card2.pdf"), Path("/tmp/new2.pdf"), False, "Error", card=card),
            ]
            results = service.rename_card(card, "NewName", "2025")

        assert len(results) == 2
        # No rollback — at least one succeeded
        assert card.manual_override == "NewName"


# ── summarize_plan ──


class TestSummarizePlan:
    """Tests for RenameService.summarize_plan()."""

    def test_counts_all_statuses(self) -> None:
        plan = [
            RenamePlanItem(Path("/a/f1.pdf"), Path("/a/new1.pdf"), "ok"),
            RenamePlanItem(Path("/a/f2.pdf"), Path("/a/new2.pdf"), "ok"),
            RenamePlanItem(Path("/a/f3.pdf"), Path("/a/f3.pdf"), "duplicate"),
            RenamePlanItem(Path("/b/f4.pdf"), Path("/b/f4.pdf"), "skip_error"),
            RenamePlanItem(Path("/b/f5.pdf"), Path("/b/f5.pdf"), "skip_no_name"),
            RenamePlanItem(Path("/b/f6.pdf"), Path("/b/f6.pdf"), "skip_same"),
        ]
        result = RenameService.summarize_plan(plan)
        assert result["ok"] == 2
        assert result["duplicate"] == 1
        assert result["error"] == 1
        assert result["skip"] == 2
        assert result["directory_count"] == 2

    def test_empty_plan(self) -> None:
        result = RenameService.summarize_plan([])
        assert result == {"ok": 0, "duplicate": 0, "error": 0, "skip": 0, "directory_count": 0}


# ── summarize_results ──


class TestSummarizeResults:
    """Tests for RenameService.summarize_results()."""

    def test_counts_all_outcomes(self) -> None:
        results = [
            RenameResult(Path("/a/f1.pdf"), Path("/a/new1.pdf"), True, "Renamed"),
            RenameResult(Path("/a/f2.pdf"), Path("/a/new2.pdf"), True, "Renamed"),
            RenameResult(Path("/a/f3.pdf"), Path("/a/f3.pdf"), True, "Already named correctly"),
            RenameResult(Path("/a/f4.pdf"), Path("/a/f4.pdf"), False, "Permission denied"),
        ]
        result = RenameService.summarize_results(results)
        assert result["renamed"] == 2
        assert result["skipped"] == 1
        assert result["errors"] == 1

    def test_empty_results(self) -> None:
        result = RenameService.summarize_results([])
        assert result == {"renamed": 0, "skipped": 0, "errors": 0}
