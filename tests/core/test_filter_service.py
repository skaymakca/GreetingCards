"""Tests for app.core.filter_service — pure filter functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.filter_service import apply_category_filters, apply_folder_filters, search_filter
from app.models.card import CardResult, Confidence


def _card(
    id: int,
    *,
    path: str = "/folder/file.pdf",
    family_name: str = "",
    confidence: Confidence = Confidence.HIGH,
    error: str = "",
) -> CardResult:
    """Helper to create a CardResult with minimal boilerplate."""
    p = Path(path)
    return CardResult(
        id=id,
        file_paths=[p],
        primary_path=p,
        family_name=family_name,
        confidence=confidence,
        error=error,
    )


# ---------------------------------------------------------------------------
# search_filter
# ---------------------------------------------------------------------------


class TestSearchFilter:
    def test_empty_query_returns_all(self) -> None:
        cards = [_card(1, path="/a/b.pdf"), _card(2, path="/a/c.pdf")]
        assert search_filter(cards, "") == cards

    def test_whitespace_only_query_returns_all(self) -> None:
        cards = [_card(1, path="/a/b.pdf"), _card(2, path="/a/c.pdf")]
        assert search_filter(cards, "   ") == cards

    def test_matches_filename_case_insensitive(self) -> None:
        cards = [
            _card(1, path="/folder/Alpha.pdf"),
            _card(2, path="/folder/Beta.pdf"),
        ]
        result = search_filter(cards, "alpha")
        assert len(result) == 1
        assert result[0].id == 1

    def test_matches_family_name_case_insensitive(self) -> None:
        cards = [
            _card(1, path="/folder/file1.pdf", family_name="Johnson"),
            _card(2, path="/folder/file2.pdf", family_name="Smith"),
        ]
        result = search_filter(cards, "JOHNSON")
        assert len(result) == 1
        assert result[0].id == 1

    def test_matches_partial_filename(self) -> None:
        cards = [_card(1, path="/folder/holiday_card_2025.pdf")]
        result = search_filter(cards, "holiday")
        assert len(result) == 1

    def test_matches_partial_family_name(self) -> None:
        cards = [_card(1, path="/folder/file.pdf", family_name="McPherson")]
        result = search_filter(cards, "pherson")
        assert len(result) == 1

    def test_no_matches_returns_empty(self) -> None:
        cards = [
            _card(1, path="/folder/Alpha.pdf", family_name="Jones"),
            _card(2, path="/folder/Beta.pdf", family_name="Smith"),
        ]
        result = search_filter(cards, "zzz_no_match")
        assert result == []

    def test_empty_cards_returns_empty(self) -> None:
        assert search_filter([], "anything") == []

    def test_query_stripped_of_whitespace(self) -> None:
        cards = [_card(1, path="/folder/Alpha.pdf")]
        result = search_filter(cards, "  alpha  ")
        assert len(result) == 1

    def test_matches_both_filename_and_family_name(self) -> None:
        """A card matching on either field should appear once."""
        cards = [_card(1, path="/folder/smith_card.pdf", family_name="Smith")]
        result = search_filter(cards, "smith")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# apply_folder_filters
# ---------------------------------------------------------------------------


class TestApplyFolderFilters:
    def test_all_folders_returns_all(self) -> None:
        cards = [_card(1, path="/a/file.pdf"), _card(2, path="/b/file.pdf")]
        result = apply_folder_filters(cards, ["all_folders"])
        assert result == cards

    def test_all_folders_with_other_keys_still_returns_all(self) -> None:
        """If 'all_folders' is present alongside other keys, it takes precedence."""
        cards = [_card(1, path="/a/file.pdf"), _card(2, path="/b/file.pdf")]
        result = apply_folder_filters(cards, ["all_folders", "/a"])
        assert result == cards

    def test_filters_by_specific_folder(self) -> None:
        cards = [
            _card(1, path="/folder_a/file1.pdf"),
            _card(2, path="/folder_b/file2.pdf"),
        ]
        result = apply_folder_filters(cards, ["/folder_a"])
        assert len(result) == 1
        assert result[0].id == 1

    def test_multiple_folders(self) -> None:
        cards = [
            _card(1, path="/folder_a/file1.pdf"),
            _card(2, path="/folder_b/file2.pdf"),
            _card(3, path="/folder_c/file3.pdf"),
        ]
        result = apply_folder_filters(cards, ["/folder_a", "/folder_c"])
        assert len(result) == 2
        assert {c.id for c in result} == {1, 3}

    def test_no_matching_folder_returns_empty(self) -> None:
        cards = [_card(1, path="/folder_a/file.pdf")]
        result = apply_folder_filters(cards, ["/nonexistent"])
        assert result == []

    def test_card_with_multiple_file_paths(self) -> None:
        """A card with file_paths in multiple folders matches if any path matches."""
        card = CardResult(
            id=1,
            file_paths=[Path("/folder_a/dup1.pdf"), Path("/folder_b/dup2.pdf")],
            primary_path=Path("/folder_a/dup1.pdf"),
            family_name="Test",
            confidence=Confidence.HIGH,
        )
        result = apply_folder_filters([card], ["/folder_b"])
        assert len(result) == 1

    def test_empty_cards_returns_empty(self) -> None:
        assert apply_folder_filters([], ["/folder"]) == []

    def test_empty_folder_keys_returns_empty(self) -> None:
        """With no folder keys selected (and no 'all_folders'), nothing matches."""
        cards = [_card(1, path="/folder/file.pdf")]
        result = apply_folder_filters(cards, [])
        assert result == []


# ---------------------------------------------------------------------------
# apply_category_filters
# ---------------------------------------------------------------------------


class TestApplyCategoryFilters:
    def test_all_returns_all_sorted(self) -> None:
        cards = [
            _card(1, path="/f/Zebra.pdf", family_name="Zebra"),
            _card(2, path="/f/Alpha.pdf", family_name="Alpha"),
        ]
        result = apply_category_filters(cards, ["all"])
        assert [c.id for c in result] == [2, 1]  # sorted by filename

    def test_high_filter(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.HIGH),
            _card(2, path="/f/b.pdf", confidence=Confidence.LOW),
        ]
        result = apply_category_filters(cards, ["high"])
        assert len(result) == 1
        assert result[0].id == 1

    def test_manual_filter(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.MANUAL),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["manual"])
        assert len(result) == 1
        assert result[0].id == 1

    def test_needs_review_includes_medium_and_low(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.MEDIUM),
            _card(2, path="/f/b.pdf", confidence=Confidence.LOW),
            _card(3, path="/f/c.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["needs_review"])
        assert len(result) == 2
        assert {c.id for c in result} == {1, 2}

    def test_errors_filter_with_error_string(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.HIGH, error="corrupt PDF"),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["errors"])
        assert len(result) == 1
        assert result[0].id == 1

    def test_errors_filter_with_none_confidence(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.NONE),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["errors"])
        assert len(result) == 1
        assert result[0].id == 1

    def test_errors_filter_matches_both_error_and_none(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.NONE),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH, error="bad file"),
            _card(3, path="/f/c.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["errors"])
        assert len(result) == 2
        assert {c.id for c in result} == {1, 2}

    def test_multiple_categories_no_duplicates(self) -> None:
        """A card matching multiple categories should appear only once."""
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.NONE, error="broken"),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH),
            _card(3, path="/f/c.pdf", confidence=Confidence.LOW),
        ]
        # Card 1 matches "errors" twice (error string + NONE confidence)
        # Card 3 matches "needs_review"
        result = apply_category_filters(cards, ["errors", "needs_review"])
        assert len(result) == 2
        assert {c.id for c in result} == {1, 3}

    def test_multiple_categories_high_and_manual(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.HIGH),
            _card(2, path="/f/b.pdf", confidence=Confidence.MANUAL),
            _card(3, path="/f/c.pdf", confidence=Confidence.LOW),
        ]
        result = apply_category_filters(cards, ["high", "manual"])
        assert len(result) == 2
        assert {c.id for c in result} == {1, 2}

    def test_output_always_sorted_by_filename(self) -> None:
        cards = [
            _card(1, path="/f/Zebra.pdf", confidence=Confidence.HIGH),
            _card(2, path="/f/Alpha.pdf", confidence=Confidence.HIGH),
            _card(3, path="/f/Middle.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["high"])
        filenames = [c.filename for c in result]
        assert filenames == ["Alpha.pdf", "Middle.pdf", "Zebra.pdf"]

    def test_sorting_is_case_insensitive(self) -> None:
        cards = [
            _card(1, path="/f/beta.pdf", confidence=Confidence.HIGH),
            _card(2, path="/f/Alpha.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["high"])
        filenames = [c.filename for c in result]
        assert filenames == ["Alpha.pdf", "beta.pdf"]

    def test_unknown_category_key_ignored(self) -> None:
        """Unknown filter keys should silently produce no matches for that key."""
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["unknown_key"])
        assert result == []

    def test_empty_cards_returns_empty(self) -> None:
        assert apply_category_filters([], ["all"]) == []
        assert apply_category_filters([], ["high"]) == []

    @pytest.mark.parametrize("category_keys", [["all"], ["high"], ["manual"]])
    def test_all_category_returns_sorted(self, category_keys: list[str]) -> None:
        """Regardless of category, output is always sorted."""
        cards = [
            _card(1, path="/f/Z.pdf", confidence=Confidence.HIGH, family_name="Z"),
            _card(2, path="/f/A.pdf", confidence=Confidence.HIGH, family_name="A"),
            _card(3, path="/f/M.pdf", confidence=Confidence.MANUAL, family_name="M"),
        ]
        result = apply_category_filters(cards, category_keys)
        filenames = [c.filename for c in result]
        assert filenames == sorted(filenames, key=str.lower)
