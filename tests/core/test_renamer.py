"""Tests for the renamer module — multi-path rename support."""

import pytest
from pathlib import Path
from app.models.card import CardResult, Confidence, RenamePlanItem
from app.core.renamer import (
    build_rename_plan,
    execute_rename_plan,
    _read_directory_names,
    _find_available_name,
)


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
        assert plan[0].status == "ok"
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
        assert plan[0].status == "ok"

        assert plan[1].old_path == Path("/dir_b/card.pdf")
        assert plan[1].new_path == Path("/dir_b/Holiday Cards 2024 - Jones Family.pdf")
        assert plan[1].status == "ok"

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
        assert plan[0].status == "ok"

        assert plan[1].new_path == Path("/dir/Holiday Cards 2024 - Smith Family (2).pdf")
        assert plan[1].status == "duplicate"

    def test_two_cards_same_name_different_directories(self):
        """Two different cards with the same target name in DIFFERENT directories → no dedup."""
        card_a = _make_card(1, [Path("/dir_a/a.pdf")], family_name="Smith")
        card_b = _make_card(2, [Path("/dir_b/b.pdf")], family_name="Smith")
        plan = build_rename_plan([card_a, card_b], "2024")

        assert len(plan) == 2
        # Both get the clean name (different directories, no conflict)
        assert plan[0].new_path == Path("/dir_a/Holiday Cards 2024 - Smith Family.pdf")
        assert plan[0].status == "ok"

        assert plan[1].new_path == Path("/dir_b/Holiday Cards 2024 - Smith Family.pdf")
        assert plan[1].status == "ok"

    def test_error_card_with_multiple_paths(self):
        """Error card with multiple paths → skip_error for each path."""
        card = _make_card(
            1,
            [Path("/dir_a/card.pdf"), Path("/dir_b/card.pdf")],
            error="Corrupt PDF",
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 2
        assert all(item.status == "skip_error" for item in plan)
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
        assert all(item.status == "skip_no_name" for item in plan)

    def test_skip_same_detection(self):
        """Card already named correctly → skip_same."""
        card = _make_card(
            1,
            [Path("/dir/Holiday Cards 2024 - Smith Family.pdf")],
            family_name="Smith",
        )
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].status == "skip_same"

    def test_target_exists_on_disk(self, tmp_path):
        """Target file already exists on disk → duplicate with (2) suffix."""
        # Create existing file at target path
        existing = tmp_path / "Holiday Cards 2024 - Smith Family.pdf"
        existing.touch()

        card = _make_card(1, [tmp_path / "card.pdf"], family_name="Smith")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].status == "duplicate"
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
        assert plan[0].status == "ok"


    def test_disk_has_base_and_numbered_files(self, tmp_path):
        """Disk has base + (2) + (3), new card should get (4)."""
        (tmp_path / "Holiday Cards 2024 - Walsh Family.pdf").touch()
        (tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf").touch()
        (tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf").touch()

        card = _make_card(1, [tmp_path / "new_card.pdf"], family_name="Walsh")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (4).pdf"
        assert plan[0].status == "duplicate"

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
        assert plan[0].status == "duplicate"
        assert plan[1].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (5).pdf"
        assert plan[1].status == "duplicate"

    def test_only_base_file_exists_on_disk(self, tmp_path):
        """Only base file on disk → new card gets (2)."""
        (tmp_path / "Holiday Cards 2024 - Smith Family.pdf").touch()

        card = _make_card(1, [tmp_path / "card.pdf"], family_name="Smith")
        plan = build_rename_plan([card], "2024")

        assert len(plan) == 1
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Smith Family (2).pdf"
        assert plan[0].status == "duplicate"

    def test_disk_has_gap_two_new_cards(self, tmp_path):
        """Disk has (2), two new cards → first gets (3), second gets (4)."""
        (tmp_path / "Holiday Cards 2024 - Walsh Family (2).pdf").touch()

        card_a = _make_card(1, [tmp_path / "a.pdf"], family_name="Walsh")
        card_b = _make_card(2, [tmp_path / "b.pdf"], family_name="Walsh")
        plan = build_rename_plan([card_a, card_b], "2024")

        assert len(plan) == 2
        # Base name not taken on disk, first card gets it
        assert plan[0].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family.pdf"
        assert plan[0].status == "ok"
        # Second card clashes with first planned + (2) on disk → gets (3)
        assert plan[1].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf"
        assert plan[1].status == "duplicate"

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
        assert plan[0].status == "skip_same"
        assert plan[1].status == "skip_same"
        assert plan[2].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf"
        assert plan[2].status == "duplicate"

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
        assert plan[0].status == "ok"
        # card_b: already named correctly
        assert plan[1].status == "skip_same"
        # card_c: (2) still visible in set → gets (3)
        assert plan[2].new_path == tmp_path / "Holiday Cards 2024 - Walsh Family (3).pdf"
        assert plan[2].status == "duplicate"


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
            RenamePlanItem(Path("/a.pdf"), Path("/a.pdf"), "skip_no_name"),
            RenamePlanItem(Path("/b.pdf"), Path("/b.pdf"), "skip_error"),
            RenamePlanItem(Path("/c.pdf"), Path("/c.pdf"), "skip_same"),
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

        plan = [RenamePlanItem(old_file, new_path, "ok")]

        results = execute_rename_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert new_path.exists()
