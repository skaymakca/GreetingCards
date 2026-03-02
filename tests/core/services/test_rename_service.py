"""Tests for RenameService — rename orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.card_store import CardStore
from app.core.services.rename_service import RenameService
from app.gui.rename_display import (
    filter_visible_results,
    format_plan_summary,
    format_result_status,
    format_results_summary,
    get_plan_item_display,
    is_skip_status,
    summarize_plan,
    summarize_results,
)
from app.models.card import (
    CardResult,
    Confidence,
    RenameOutcome,
    RenamePlanItem,
    RenameResult,
    RenameStatus,
)


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

        plan = [RenamePlanItem(old_path, new_path, RenameStatus.OK, card=card)]

        with patch("app.core.services.rename_service.execute_rename_plan") as mock_exec:
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

        plan = [RenamePlanItem(old_path, new_path, RenameStatus.OK, card=card)]

        with patch("app.core.services.rename_service.execute_rename_plan") as mock_exec:
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
        """Skip-same results (success=True, outcome=ALREADY_CORRECT)
        should update path mappings since they are in RESOLVED_OUTCOMES."""
        card = _make_card()
        store = _make_store(card)
        service = RenameService(store)

        old_path = Path("/tmp/card.pdf")
        new_path = Path("/tmp/card.pdf")  # Same path

        plan = [RenamePlanItem(old_path, new_path, RenameStatus.SKIP_SAME, card=card)]

        with patch("app.core.services.rename_service.execute_rename_plan") as mock_exec:
            mock_exec.return_value = [
                RenameResult(
                    old_path,
                    new_path,
                    True,
                    "Already named correctly",
                    outcome=RenameOutcome.ALREADY_CORRECT,
                    card=card,
                ),
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
            patch("app.core.services.rename_service.build_rename_plan") as mock_build,
            patch("app.core.services.rename_service.execute_rename_plan") as mock_exec,
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
            patch("app.core.services.rename_service.build_rename_plan") as mock_build,
            patch("app.core.services.rename_service.execute_rename_plan") as mock_exec,
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
            patch("app.core.services.rename_service.build_rename_plan") as mock_build,
            patch("app.core.services.rename_service.execute_rename_plan") as mock_exec,
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
    """Tests for summarize_plan()."""

    def test_counts_all_statuses(self) -> None:
        plan = [
            RenamePlanItem(Path("/a/f1.pdf"), Path("/a/new1.pdf"), RenameStatus.OK),
            RenamePlanItem(Path("/a/f2.pdf"), Path("/a/new2.pdf"), RenameStatus.OK),
            RenamePlanItem(Path("/a/f3.pdf"), Path("/a/f3.pdf"), RenameStatus.DUPLICATE),
            RenamePlanItem(Path("/b/f4.pdf"), Path("/b/f4.pdf"), RenameStatus.SKIP_ERROR),
            RenamePlanItem(Path("/b/f5.pdf"), Path("/b/f5.pdf"), RenameStatus.SKIP_NO_NAME),
            RenamePlanItem(Path("/b/f6.pdf"), Path("/b/f6.pdf"), RenameStatus.SKIP_SAME),
        ]
        result = summarize_plan(plan)
        assert result["ok"] == 2
        assert result["duplicate"] == 1
        assert result["error"] == 1
        assert result["skip"] == 2
        assert result["directory_count"] == 2

    def test_empty_plan(self) -> None:
        result = summarize_plan([])
        assert result == {"ok": 0, "duplicate": 0, "error": 0, "skip": 0, "directory_count": 0}


# ── summarize_results ──


class TestSummarizeResults:
    """Tests for summarize_results()."""

    def test_counts_all_outcomes(self) -> None:
        results = [
            RenameResult(Path("/a/f1.pdf"), Path("/a/new1.pdf"), True, "Renamed", outcome=RenameOutcome.RENAMED),
            RenameResult(Path("/a/f2.pdf"), Path("/a/new2.pdf"), True, "Renamed", outcome=RenameOutcome.RENAMED),
            RenameResult(
                Path("/a/f3.pdf"),
                Path("/a/f3.pdf"),
                True,
                "Already named correctly",
                outcome=RenameOutcome.ALREADY_CORRECT,
            ),
            RenameResult(
                Path("/b/f4.pdf"),
                Path("/b/f4.pdf"),
                False,
                "Permission denied",
                outcome=RenameOutcome.ERROR_OS,
            ),
        ]
        result = summarize_results(results)
        assert result["renamed"] == 2
        assert result["skipped"] == 1
        assert result["errors"] == 1
        assert result["directory_count"] == 2

    def test_empty_results(self) -> None:
        result = summarize_results([])
        assert result == {"renamed": 0, "skipped": 0, "errors": 0, "directory_count": 0}

    def test_directory_count_uses_new_path_for_success(self) -> None:
        """directory_count should use new_path for successful results."""
        results = [
            RenameResult(Path("/old/f1.pdf"), Path("/new/f1.pdf"), True, "Renamed"),
        ]
        result = summarize_results(results)
        assert result["directory_count"] == 1

    def test_directory_count_uses_old_path_for_failure(self) -> None:
        """directory_count should use old_path for failed results."""
        results = [
            RenameResult(Path("/old/f1.pdf"), Path("/new/f1.pdf"), False, "Error"),
        ]
        result = summarize_results(results)
        assert result["directory_count"] == 1


# ── build_plan ──


class TestBuildPlan:
    """Tests for RenameService.build_plan()."""

    def test_delegates_to_build_rename_plan(self) -> None:
        """build_plan should wrap build_rename_plan."""
        card = _make_card()
        with patch("app.core.services.rename_service.build_rename_plan") as mock_build:
            mock_build.return_value = [
                RenamePlanItem(Path("/tmp/card.pdf"), Path("/tmp/new.pdf"), RenameStatus.OK, card=card),
            ]
            plan = RenameService.build_plan([card], "2025")

        mock_build.assert_called_once_with([card], "2025")
        assert len(plan) == 1
        assert plan[0].status == RenameStatus.OK


# ── format_plan_summary ──


class TestFormatPlanSummary:
    """Tests for format_plan_summary()."""

    def test_renames_only(self) -> None:
        plan = [
            RenamePlanItem(Path("/a/f1.pdf"), Path("/a/new1.pdf"), RenameStatus.OK),
            RenamePlanItem(Path("/a/f2.pdf"), Path("/a/new2.pdf"), RenameStatus.OK),
        ]
        assert format_plan_summary(plan) == "2 rename(s)"

    def test_all_statuses_multi_dir(self) -> None:
        plan = [
            RenamePlanItem(Path("/a/f1.pdf"), Path("/a/new1.pdf"), RenameStatus.OK),
            RenamePlanItem(Path("/a/f2.pdf"), Path("/a/f2.pdf"), RenameStatus.DUPLICATE),
            RenamePlanItem(Path("/b/f3.pdf"), Path("/b/f3.pdf"), RenameStatus.SKIP_SAME),
            RenamePlanItem(Path("/b/f4.pdf"), Path("/b/f4.pdf"), RenameStatus.SKIP_ERROR),
        ]
        result = format_plan_summary(plan)
        assert "1 rename(s)" in result
        assert "1 duplicate(s)" in result
        assert "1 skipped" in result
        assert "1 error(s)" in result
        assert "across 2 directories" in result

    def test_empty_plan(self) -> None:
        assert format_plan_summary([]) == "0 rename(s)"


# ── format_results_summary ──


class TestFormatResultsSummary:
    """Tests for format_results_summary()."""

    def test_no_errors(self) -> None:
        results = [
            RenameResult(Path("/a/f1.pdf"), Path("/a/new1.pdf"), True, "Renamed", outcome=RenameOutcome.RENAMED),
            RenameResult(
                Path("/a/f2.pdf"),
                Path("/a/f2.pdf"),
                True,
                "Already named correctly",
                outcome=RenameOutcome.ALREADY_CORRECT,
            ),
        ]
        assert format_results_summary(results) == "1 renamed, 1 skipped"

    def test_with_errors(self) -> None:
        results = [
            RenameResult(Path("/a/f1.pdf"), Path("/a/new1.pdf"), True, "Renamed", outcome=RenameOutcome.RENAMED),
            RenameResult(Path("/a/f2.pdf"), Path("/a/f2.pdf"), False, "Error", outcome=RenameOutcome.ERROR_OS),
        ]
        assert format_results_summary(results) == "1 renamed, 0 skipped, 1 failed"

    def test_empty_results(self) -> None:
        assert format_results_summary([]) == "0 renamed, 0 skipped"


# ── get_completed_paths ──


class TestGetCompletedPaths:
    """Tests for RenameService.get_completed_paths()."""

    def test_returns_resolved_paths(self) -> None:
        results = [
            RenameResult(Path("/a/f1.pdf"), Path("/a/new1.pdf"), True, "Renamed", outcome=RenameOutcome.RENAMED),
            RenameResult(
                Path("/a/f2.pdf"),
                Path("/a/f2.pdf"),
                True,
                "Already named correctly",
                outcome=RenameOutcome.ALREADY_CORRECT,
            ),
            RenameResult(Path("/a/f3.pdf"), Path("/a/f3.pdf"), False, "Error", outcome=RenameOutcome.ERROR_OS),
            RenameResult(
                Path("/a/f4.pdf"),
                Path("/a/f4.pdf"),
                True,
                "Skipped: no name",
                outcome=RenameOutcome.SKIP_NO_NAME,
            ),
        ]
        paths = RenameService.get_completed_paths(results)
        assert paths == {Path("/a/new1.pdf"), Path("/a/f2.pdf")}

    def test_empty_results(self) -> None:
        assert RenameService.get_completed_paths([]) == set()


# ── validate_year ──


class TestValidateYear:
    """Tests for RenameService.validate_year()."""

    def test_valid_year(self) -> None:
        assert RenameService.validate_year("2025") is True

    def test_short_year(self) -> None:
        assert RenameService.validate_year("25") is False

    def test_empty_string(self) -> None:
        assert RenameService.validate_year("") is False

    def test_non_digit(self) -> None:
        assert RenameService.validate_year("abcd") is False


# ── INVALID_FILENAME_CHARS ──


class TestInvalidFilenameChars:
    """Tests for RenameService.INVALID_FILENAME_CHARS."""

    def test_is_frozenset(self) -> None:
        assert isinstance(RenameService.INVALID_FILENAME_CHARS, frozenset)

    def test_contains_expected_chars(self) -> None:
        for char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
            assert char in RenameService.INVALID_FILENAME_CHARS


# ── filter_visible_results ──


class TestFilterVisibleResults:
    """Tests for filter_visible_results()."""

    def test_keeps_renamed_and_errors(self) -> None:
        results = [
            RenameResult(Path("/a/f1.pdf"), Path("/a/new1.pdf"), True, "", outcome=RenameOutcome.RENAMED),
            RenameResult(
                Path("/a/f2.pdf"),
                Path("/a/f2.pdf"),
                True,
                "",
                outcome=RenameOutcome.ALREADY_CORRECT,
            ),
            RenameResult(
                Path("/a/f3.pdf"),
                Path("/a/f3.pdf"),
                False,
                "Permission denied",
                outcome=RenameOutcome.ERROR_OS,
            ),
        ]
        visible = filter_visible_results(results)
        assert len(visible) == 2
        assert visible[0].outcome == RenameOutcome.RENAMED
        assert visible[1].outcome == RenameOutcome.ERROR_OS

    def test_empty_results(self) -> None:
        assert filter_visible_results([]) == []


# ── get_plan_item_display ──


class TestGetPlanItemDisplay:
    """Tests for get_plan_item_display()."""

    def test_ok_status(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/new.pdf"), RenameStatus.OK)
        label, category = get_plan_item_display(item)
        assert label == "OK"
        assert category == "ok"

    def test_duplicate_status(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.DUPLICATE)
        label, category = get_plan_item_display(item)
        assert label == "DUP"
        assert category == "duplicate"

    def test_skip_no_name(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.SKIP_NO_NAME)
        label, category = get_plan_item_display(item)
        assert label == "SKIP"
        assert category == "skip"

    def test_skip_same(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.SKIP_SAME)
        label, category = get_plan_item_display(item)
        assert label == "SAME"
        assert category == "skip"

    def test_skip_error(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.SKIP_ERROR)
        label, category = get_plan_item_display(item)
        assert label == "ERROR"
        assert category == "error"


# ── is_skip_status ──


class TestIsSkipStatus:
    """Tests for is_skip_status()."""

    def test_ok_is_not_skip(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/new.pdf"), RenameStatus.OK)
        assert is_skip_status(item) is False

    def test_skip_no_name(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.SKIP_NO_NAME)
        assert is_skip_status(item) is True

    def test_skip_same(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.SKIP_SAME)
        assert is_skip_status(item) is True

    def test_skip_error(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.SKIP_ERROR)
        assert is_skip_status(item) is True

    def test_duplicate_is_not_skip(self) -> None:
        item = RenamePlanItem(Path("/a/f.pdf"), Path("/a/f.pdf"), RenameStatus.DUPLICATE)
        assert is_skip_status(item) is False


# ── format_result_status ──


class TestFormatResultStatus:
    """Tests for format_result_status() — outcome→display mapping."""

    def test_renamed(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/b.pdf"), True, "", outcome=RenameOutcome.RENAMED)
        assert format_result_status(r) == "OK"

    def test_already_correct(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/a.pdf"), True, "", outcome=RenameOutcome.ALREADY_CORRECT)
        assert format_result_status(r) == "Already correct"

    def test_skip_no_name(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/a.pdf"), True, "", outcome=RenameOutcome.SKIP_NO_NAME)
        assert format_result_status(r) == "Skipped (no name)"

    def test_skip_error(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/a.pdf"), True, "", outcome=RenameOutcome.SKIP_ERROR)
        assert format_result_status(r) == "Skipped (error)"

    def test_error_target_exists_no_message(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/b.pdf"), False, "", outcome=RenameOutcome.ERROR_TARGET_EXISTS)
        assert format_result_status(r) == "ERROR: Target exists"

    def test_error_os_with_message(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/b.pdf"), False, "Permission denied", outcome=RenameOutcome.ERROR_OS)
        assert format_result_status(r) == "ERROR: Permission denied"

    def test_error_os_no_message(self) -> None:
        r = RenameResult(Path("/a.pdf"), Path("/b.pdf"), False, "", outcome=RenameOutcome.ERROR_OS)
        assert format_result_status(r) == "ERROR"

    def test_error_target_exists_with_message(self) -> None:
        r = RenameResult(
            Path("/a.pdf"), Path("/b.pdf"), False, "File exists", outcome=RenameOutcome.ERROR_TARGET_EXISTS
        )
        assert format_result_status(r) == "ERROR: File exists"
