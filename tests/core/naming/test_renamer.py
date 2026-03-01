"""Tests for the renamer module — multi-path rename support."""

from pathlib import Path

import pytest

from app.core.naming.renamer import (
    _find_available_name,
    _read_directory_names,
    build_rename_plan,
    execute_rename_plan,
    validate_year,
)
from app.models.card import (
    STATUS_DUPLICATE,
    STATUS_OK,
    STATUS_SKIP_ERROR,
    STATUS_SKIP_NO_NAME,
    STATUS_SKIP_SAME,
    CardResult,
    Confidence,
    RenamePlanItem,
)


class TestValidateYear:
    """Tests for validate_year()."""

    def test_valid_four_digit_year(self):
        assert validate_year("2024") is True
        assert validate_year("1999") is True

    def test_empty_string(self):
        assert validate_year("") is False

    def test_non_digit(self):
        assert validate_year("abcd") is False
        assert validate_year("20ab") is False

    def test_wrong_length(self):
        assert validate_year("24") is False
        assert validate_year("20245") is False

    def test_whitespace(self):
        assert validate_year("    ") is False
        assert validate_year(" 2024") is False


def _make_card(
    card_id: int,
    file_paths: list[Path],
    family_name: str = "",
    confidence: Confidence = Confidence.HIGH,
    error: str = "",
    remove_family: bool = False,
) -> CardResult:
    """Helper to create a CardResult with given paths."""
    card = CardResult(
        id=card_id,
        file_paths=list(file_paths),
        primary_path=file_paths[0],
        family_name=family_name,
        confidence=confidence,
        error=error,
        remove_family=remove_family,
    )
    return card


class TestBuildRenamePlan:
    """Tests for build_rename_plan()."""

    def test_single_card_single_path(self):
        """Baseline: one card, one path → one plan item."""
        card = _make_card(1, [Path("/dir/card.pdf")], family_name="Smith")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].old_path == Path("/dir/card.pdf")
        assert plan[0].new_path == Path("/dir/Holiday Cards 2024 - Smith Family.pdf")
        assert plan[0].status == STATUS_OK
        assert plan[0].card is card

    def test_single_card_multiple_paths_different_dirs(self):
        """Same card with copies in two directories → two plan items, each in its own dir."""
        card = _make_card(
            1,
            [Path("/dir_a/card.pdf"), Path("/dir_b/card.pdf")],
            family_name="Jones",
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 2
        assert plan[0].old_path == Path("/dir_a/card.pdf")
        assert plan[0].new_path == Path("/dir_a/Holiday Cards 2024 - Jones Family.pdf")
        assert plan[0].status == STATUS_OK

        assert plan[1].old_path == Path("/dir_b/card.pdf")
        assert plan[1].new_path == Path("/dir_b/Holiday Cards 2024 - Jones Family.pdf")
        assert plan[1].status == STATUS_OK

        # Both reference the same card
        assert plan[0].card is card
        assert plan[1].card is card

    def test_two_cards_same_name_same_directory(self):
        """Two different cards with the same target name in the SAME directory → second gets (2)."""
        card_a = _make_card(1, [Path("/dir/a.pdf")], family_name="Smith")
        card_b = _make_card(2, [Path("/dir/b.pdf")], family_name="Smith")
        plan = build_rename_plan([card_a, card_b], "2024")

        assert len(plan) == 2
        assert plan[0].new_path == Path("/dir/Holiday Cards 2024 - Smith Family.pdf")
        assert plan[0].status == STATUS_OK

        assert plan[1].new_path == Path("/dir/Holiday Cards 2024 - Smith Family (2).pdf")
        assert plan[1].status == STATUS_DUPLICATE

    def test_two_cards_same_name_different_directories(self):
        """Two different cards with the same target name in DIFFERENT directories → no dedup."""
        card_a = _make_card(1, [Path("/dir_a/a.pdf")], family_name="Smith")
        card_b = _make_card(2, [Path("/dir_b/b.pdf")], family_name="Smith")
        plan = build_rename_plan([card_a, card_b], "2024")

        assert len(plan) == 2
        # Both get the clean name (different directories, no conflict)
        assert plan[0].new_path == Path("/dir_a/Holiday Cards 2024 - Smith Family.pdf")
        assert plan[0].status == STATUS_OK

        assert plan[1].new_path == Path("/dir_b/Holiday Cards 2024 - Smith Family.pdf")
        assert plan[1].status == STATUS_OK

    def test_error_card_with_multiple_paths(self):
        """Error card with multiple paths → skip_error for each path."""
        card = _make_card(
            1,
            [Path("/dir_a/card.pdf"), Path("/dir_b/card.pdf")],
            error="Corrupt PDF",
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 2
        assert all(item.status == STATUS_SKIP_ERROR for item in plan)
        assert plan[0].old_path == Path("/dir_a/card.pdf")
        assert plan[1].old_path == Path("/dir_b/card.pdf")

    def test_no_name_card_with_multiple_paths(self):
        """Card with no name and multiple paths → skip_no_name for each path."""
        card = _make_card(
            1,
            [Path("/dir_a/card.pdf"), Path("/dir_b/card.pdf")],
            family_name="",
            confidence=Confidence.NONE,
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 2
        assert all(item.status == STATUS_SKIP_NO_NAME for item in plan)

    def test_skip_same_detection(self):
        """Card already named correctly → skip_same."""
        card = _make_card(
            1,
            [Path("/dir/Holiday Cards 2024 - Smith Family.pdf")],
            family_name="Smith",
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].status == STATUS_SKIP_SAME

    def test_target_exists_on_disk(self, tmp_path):
        """Target file already exists on disk → duplicate with (2) suffix."""
        # Create existing file at target path
        existing = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"
        existing.touch()

        card = _make_card(1, [tmp_path / "card.pdf"], family_name="Smith")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].status == STATUS_DUPLICATE
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Smith Family (2).pdf"

    def test_card_back_reference(self):
        """Each plan item carries a reference to its source card."""
        card = _make_card(1, [Path("/dir/card.pdf")], family_name="Smith")
        plan = build_rename_plan([card], "2024")

        assert plan[0].card is card

    def test_remove_family_flag(self):
        """Card with remove_family=True omits 'Family' from target name."""
        card = _make_card(
            1,
            [Path("/dir/card.pdf")],
            family_name="The Smiths",
            remove_family=True,
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].new_path == Path("/dir/Holiday Cards 2024 - The Smiths.pdf")
        assert plan[0].status == STATUS_OK

    def test_disk_has_base_and_numbered_files(self, tmp_path):
        """Disk has base + (2) + (3), new card should get (4)."""
        (tmp_path / "Holiday Cards 2024 - Walsh Family.pdf").touch()
        (tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf").touch()
        (tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf").touch()

        card = _make_card(1, [tmp_path / "new_card.pdf"], family_name="Walsh")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (4).pdf"
        assert plan[0].status == STATUS_DUPLICATE

    def test_disk_has_numbered_two_new_cards(self, tmp_path):
        """Disk has base + (2) + (3), two new Walsh cards → get (4) and (5)."""
        (tmp_path / "Holiday Cards 2024 - Walsh Family.pdf").touch()
        (tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf").touch()
        (tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf").touch()

        card_a = _make_card(1, [tmp_path / "a.pdf"], family_name="Walsh")
        card_b = _make_card(2, [tmp_path / "b.pdf"], family_name="Walsh")
        plan = build_rename_plan([card_a, card_b], "2024")

        assert len(plan) == 2
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (4).pdf"
        assert plan[0].status == STATUS_DUPLICATE
        assert plan[1].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (5).pdf"
        assert plan[1].status == STATUS_DUPLICATE

    def test_only_base_file_exists_on_disk(self, tmp_path):
        """Only base file on disk → new card gets (2)."""
        (tmp_path / "Holiday Cards 2024 - Smith Family.pdf").touch()

        card = _make_card(1, [tmp_path / "card.pdf"], family_name="Smith")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Smith Family (2).pdf"
        assert plan[0].status == STATUS_DUPLICATE

    def test_disk_has_gap_two_new_cards(self, tmp_path):
        """Disk has (2), two new cards → first gets (3), second gets (4)."""
        (tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf").touch()

        card_a = _make_card(1, [tmp_path / "a.pdf"], family_name="Walsh")
        card_b = _make_card(2, [tmp_path / "b.pdf"], family_name="Walsh")
        plan = build_rename_plan([card_a, card_b], "2024")

        assert len(plan) == 2
        # Base name not taken on disk, first card gets it
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family.pdf"
        assert plan[0].status == STATUS_OK
        # Second card clashes with first planned + (2) on disk → gets (3)
        assert plan[1].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf"
        assert plan[1].status == STATUS_DUPLICATE

    def test_source_file_already_correctly_numbered(self, tmp_path):
        """Card sees through its own slot: card_b keeps (2), card_c gets (3)."""
        # card_a already named correctly (skip_same)
        # card_b already named with (2) (skip_same)
        # card_c is new, all three target "Walsh Family"
        base = tmp_path / "Holiday Cards 2024 - Walsh Family.pdf"
        num2 = tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf"
        src_c = tmp_path / "card_c.pdf"
        base.touch()
        num2.touch()
        src_c.touch()

        card_a = _make_card(1, [base], family_name="Walsh")
        card_b = _make_card(2, [num2], family_name="Walsh")
        card_c = _make_card(3, [src_c], family_name="Walsh")
        plan = build_rename_plan([card_a, card_b, card_c], "2024")

        assert len(plan) == 3
        assert plan[0].status == STATUS_SKIP_SAME
        assert plan[1].status == STATUS_SKIP_SAME
        assert plan[2].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf"
        assert plan[2].status == STATUS_DUPLICATE

    def test_cross_card_slot_not_freed(self, tmp_path):
        """Other cards' source slots stay visible — conservative but safe for execution."""
        # card_a's source is "Walsh Family (2).pdf" but it targets "Jones Family"
        # card_c targets "Walsh Family" — (2) is still visible in the set (card_a
        # hasn't been executed yet), so card_c conservatively skips to (3).
        walsh2 = tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf"
        walsh_base = tmp_path / "Holiday Cards 2024 - Walsh Family.pdf"
        walsh2.touch()
        walsh_base.touch()

        card_a = _make_card(1, [walsh2], family_name="Jones")
        card_b = _make_card(2, [walsh_base], family_name="Walsh")
        card_c = _make_card(3, [tmp_path / "new.pdf"], family_name="Walsh")
        (tmp_path / "new.pdf").touch()
        plan = build_rename_plan([card_a, card_b, card_c], "2024")

        assert len(plan) == 3
        # card_a: renamed to Jones
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Jones Family.pdf"
        assert plan[0].status == STATUS_OK
        # card_b: already named correctly
        assert plan[1].status == STATUS_SKIP_SAME
        # card_c: (2) still visible in set → gets (3)
        assert plan[2].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf"
        assert plan[2].status == STATUS_DUPLICATE


class TestReadDirectoryNames:
    """Tests for _read_directory_names()."""

    def test_empty_directory(self, tmp_path):
        """Empty directory → empty set."""
        assert _read_directory_names(tmp_path) == set()

    def test_directory_with_files(self, tmp_path):
        """Directory with files → lowercase set of names."""
        (tmp_path / "File_A.pdf").touch()
        (tmp_path / "file_b.TXT").touch()
        (tmp_path / "subdir").mkdir()

        result = _read_directory_names(tmp_path)
        assert result == {"file_a.pdf", "file_b.txt"}


class TestFindAvailableName:
    """Tests for _find_available_name()."""

    def test_no_conflicts(self):
        """No conflicts → returns (2)."""
        existing: set[str] = set()
        result = _find_available_name(Path("/dir"), "Smith", ".pdf", existing)
        assert result == Path("/dir/Smith (2).pdf")

    def test_two_taken(self):
        """(2) already taken → returns (3)."""
        existing = {"smith (2).pdf"}
        result = _find_available_name(Path("/dir"), "Smith", ".pdf", existing)
        assert result == Path("/dir/Smith (3).pdf")

    def test_gap_in_sequence(self):
        """(2) and (3) taken → returns (4)."""
        existing = {"smith (2).pdf", "smith (3).pdf"}
        result = _find_available_name(Path("/dir"), "Smith", ".pdf", existing)
        assert result == Path("/dir/Smith (4).pdf")


class TestExecuteRenamePlan:
    """Tests for execute_rename_plan()."""

    def test_successful_rename(self, tmp_path):
        """Basic rename succeeds and updates card paths."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"

        card = _make_card(1, [old_file], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, "ok", card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].message == "Renamed"
        assert new_path.exists()
        assert not old_file.exists()

        # Card's file_paths and primary_path updated
        assert card.file_paths[0] == new_path
        assert card.primary_path == new_path

    def test_skip_items_pass_through(self):
        """Skipped items are reported as success with descriptive messages."""
        plan = [
            RenamePlanItem(Path("/a.pdf"), Path("/a.pdf"), STATUS_SKIP_NO_NAME),
            RenamePlanItem(Path("/b.pdf"), Path("/b.pdf"), STATUS_SKIP_ERROR),
            RenamePlanItem(Path("/c.pdf"), Path("/c.pdf"), STATUS_SKIP_SAME),
        ]

        results = execute_rename_plan(plan)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].message == "No name extracted"
        assert results[1].message == "Processing error"
        assert results[2].message == "Already named correctly"

    def test_race_condition_target_exists(self, tmp_path):
        """Target created between plan and execute → fails with descriptive error."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"
        # Simulate race condition: target appears between plan and execute
        new_path.touch()

        card = _make_card(1, [old_file], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, "ok", card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is False
        assert "Target already exists" in results[0].message
        # Original file should still exist (not renamed)
        assert old_file.exists()

    def test_card_file_paths_updated_after_rename(self, tmp_path):
        """After rename, card.file_paths and primary_path reflect the new paths."""
        file_a = tmp_path / "dir_a" / "card.pdf"
        file_b = tmp_path / "dir_b" / "card.pdf"
        file_a.parent.mkdir()
        file_b.parent.mkdir()
        file_a.touch()
        file_b.touch()

        card = _make_card(1, [file_a, file_b], family_name="Smith")

        new_a = tmp_path / "dir_a" / "Holiday Cards 2024 - Smith Family.pdf"
        new_b = tmp_path / "dir_b" / "Holiday Cards 2024 - Smith Family.pdf"

        plan = [
            RenamePlanItem(file_a, new_a, "ok", card=card),
            RenamePlanItem(file_b, new_b, "ok", card=card),
        ]

        results = execute_rename_plan(plan)

        assert all(r.success for r in results)
        assert card.file_paths == [new_a, new_b]
        assert card.primary_path == new_a

    def test_os_error_handling(self, tmp_path):
        """OSError during rename → failure with error message."""
        # File doesn't exist → rename will fail
        old_file = tmp_path / "nonexistent.pdf"
        new_path = tmp_path / "new.pdf"

        card = _make_card(1, [old_file], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, "ok", card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is False

    def test_card_file_paths_out_of_sync(self, tmp_path):
        """Rename succeeds even when card.file_paths doesn't contain old_path."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"

        # Card's file_paths contains a different path (out of sync)
        card = _make_card(1, [Path("/other/path.pdf")], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, "ok", card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert new_path.exists()
        # file_paths unchanged since old_path wasn't in the list
        assert card.file_paths == [Path("/other/path.pdf")]

    def test_no_card_reference_still_works(self, tmp_path):
        """Plan items without card reference (backward compat) still rename fine."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "new.pdf"

        plan = [RenamePlanItem(old_file, new_path, STATUS_OK)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert new_path.exists()

    def test_result_carries_card_reference(self, tmp_path):
        """RenameResult.card is populated from the plan item."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"

        card = _make_card(1, [old_file], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, STATUS_OK, card=card)]

        results = execute_rename_plan(plan)
        assert results[0].card is card

    def test_skip_result_carries_card_reference(self):
        """Skipped results also carry card back-reference."""
        card = _make_card(1, [Path("/a.pdf")], family_name="Smith")
        plan = [RenamePlanItem(Path("/a.pdf"), Path("/a.pdf"), STATUS_SKIP_SAME, card=card)]

        results = execute_rename_plan(plan)
        assert results[0].card is card


class TestBuildRenamePlanEdgeCases:
    """Additional edge case tests for build_rename_plan."""

    def test_card_with_empty_file_paths(self):
        """Card with no file paths produces no plan items."""
        card = CardResult(id=1, file_paths=[], family_name="Smith")
        card.confidence = Confidence.HIGH
        plan = build_rename_plan([card], "2024")
        assert len(plan) == 0

    def test_readonly_file_rename_fails(self, tmp_path):
        """Rename of a read-only directory file fails gracefully."""
        import os

        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        old_file = readonly_dir / "card.pdf"
        old_file.touch()
        new_path = readonly_dir / "Holiday Cards 2024 - Smith Family.pdf"

        # Make directory read-only
        os.chmod(readonly_dir, 0o555)
        try:
            card = _make_card(1, [old_file], family_name="Smith")
            plan = [RenamePlanItem(old_file, new_path, STATUS_OK, card=card)]
            results = execute_rename_plan(plan)

            assert len(results) == 1
            assert results[0].success is False
            assert results[0].card is card
        finally:
            os.chmod(readonly_dir, 0o755)


class TestFindAvailableNameSafetyLimit:
    """Test that _find_available_name has a safety limit."""

    def test_safety_limit(self):
        """When all numbered slots are taken, raises RuntimeError."""
        from app.core.naming.renamer import _MAX_DUPLICATE_NUMBER, _find_available_name

        # Create a set with all numbered slots taken
        existing = {f"smith ({n}).pdf" for n in range(2, _MAX_DUPLICATE_NUMBER + 1)}
        with pytest.raises(RuntimeError, match="Cannot find available filename"):
            _find_available_name(Path("/dir"), "Smith", ".pdf", existing)


class TestExecuteRenamePlanErrorPaths:
    """Tests for execute_rename_plan error and edge case paths."""

    def test_special_chars_in_filename(self, tmp_path):
        """Filenames with special characters (spaces, hyphens, parens) rename correctly."""
        old_file = tmp_path / "card (copy).pdf"
        old_file.touch()
        new_path = tmp_path / "Holiday Cards 2024 - O'Brien Family.pdf"

        card = _make_card(1, [old_file], family_name="O'Brien")
        plan = [RenamePlanItem(old_file, new_path, STATUS_OK, card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert new_path.exists()

    def test_target_dir_missing(self, tmp_path):
        """Rename to a nonexistent directory fails with OSError."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "nonexistent_dir" / "new.pdf"

        card = _make_card(1, [old_file], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, STATUS_OK, card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is False

    def test_duplicate_status_renames_successfully(self, tmp_path):
        """Items with STATUS_DUPLICATE are renamed (not skipped)."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "Holiday Cards 2024 - Smith Family (2).pdf"

        card = _make_card(1, [old_file], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, STATUS_DUPLICATE, card=card)]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].message == "Renamed"
        assert new_path.exists()
        assert not old_file.exists()

    def test_partial_failure(self, tmp_path):
        """When one rename fails, others still succeed."""
        good_file = tmp_path / "good.pdf"
        good_file.touch()
        bad_file = tmp_path / "nonexistent.pdf"  # doesn't exist

        good_new = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"
        bad_new = tmp_path / "Holiday Cards 2024 - Jones Family.pdf"

        card_good = _make_card(1, [good_file], family_name="Smith")
        card_bad = _make_card(2, [bad_file], family_name="Jones")

        plan = [
            RenamePlanItem(good_file, good_new, STATUS_OK, card=card_good),
            RenamePlanItem(bad_file, bad_new, STATUS_OK, card=card_bad),
        ]

        results = execute_rename_plan(plan)

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert good_new.exists()

    def test_card_path_mismatch(self, tmp_path):
        """Rename succeeds when card.file_paths doesn't contain old_path (logs debug)."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        new_path = tmp_path / "renamed.pdf"

        # Card has different paths than the plan item
        card = _make_card(1, [Path("/some/other/path.pdf")], family_name="Smith")
        plan = [RenamePlanItem(old_file, new_path, STATUS_OK, card=card)]

        results = execute_rename_plan(plan)

        assert results[0].success is True
        assert new_path.exists()
        # Card's file_paths unchanged since old_path wasn't found
        assert card.file_paths == [Path("/some/other/path.pdf")]
        # primary_path unchanged since it didn't match
        assert card.primary_path == Path("/some/other/path.pdf")

    def test_os_error_message_preserved(self, tmp_path):
        """OSError message is preserved in the result."""
        old_file = tmp_path / "card.pdf"
        old_file.touch()
        # Target in read-only directory
        import os

        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(readonly_dir, 0o555)
        new_path = readonly_dir / "new.pdf"

        try:
            card = _make_card(1, [old_file], family_name="Smith")
            plan = [RenamePlanItem(old_file, new_path, STATUS_OK, card=card)]

            results = execute_rename_plan(plan)

            assert len(results) == 1
            assert results[0].success is False
            # Error message should be non-empty
            assert len(results[0].message) > 0
        finally:
            os.chmod(readonly_dir, 0o755)
