"""Tests for app.core.services.filter_service — pure filter functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.services.filter_service import (
    apply_category_filters,
    apply_folder_filters,
    compute_filtered_view,
    count_by_category,
    count_by_folder,
    search_filter,
)
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
    def test_all_returns_all_unsorted(self) -> None:
        cards = [
            _card(1, path="/f/Zebra.pdf", family_name="Zebra"),
            _card(2, path="/f/Alpha.pdf", family_name="Alpha"),
        ]
        result = apply_category_filters(cards, ["all"])
        assert [c.id for c in result] == [1, 2]  # unsorted — caller decides display order

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

    def test_output_preserves_input_order(self) -> None:
        cards = [
            _card(1, path="/f/Zebra.pdf", confidence=Confidence.HIGH),
            _card(2, path="/f/Alpha.pdf", confidence=Confidence.HIGH),
            _card(3, path="/f/Middle.pdf", confidence=Confidence.HIGH),
        ]
        result = apply_category_filters(cards, ["high"])
        assert [c.id for c in result] == [1, 2, 3]  # unsorted — caller sorts for display

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
    def test_preserves_input_order(self, category_keys: list[str]) -> None:
        """Output order matches input order — sorting is caller's responsibility."""
        cards = [
            _card(1, path="/f/Z.pdf", confidence=Confidence.HIGH, family_name="Z"),
            _card(2, path="/f/A.pdf", confidence=Confidence.HIGH, family_name="A"),
            _card(3, path="/f/M.pdf", confidence=Confidence.MANUAL, family_name="M"),
        ]
        result = apply_category_filters(cards, category_keys)
        result_ids = [c.id for c in result]
        # Each category filters a subset but preserves original ordering
        for i in range(len(result_ids) - 1):
            assert result_ids[i] < result_ids[i + 1]


# ---------------------------------------------------------------------------
# count_by_category
# ---------------------------------------------------------------------------


class TestCountByCategory:
    def test_counts_all_categories(self) -> None:
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.MANUAL),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH),
            _card(3, path="/f/c.pdf", confidence=Confidence.MEDIUM),
            _card(4, path="/f/d.pdf", confidence=Confidence.LOW),
            _card(5, path="/f/e.pdf", confidence=Confidence.NONE),
            _card(6, path="/f/f.pdf", confidence=Confidence.HIGH, error="bad"),
        ]
        counts = count_by_category(cards)
        assert counts["all"] == 6
        assert counts["manual"] == 1
        assert counts["high"] == 2  # cards 2 and 6 (error card is also HIGH)
        assert counts["needs_review"] == 2  # MEDIUM + LOW
        assert counts["errors"] == 2  # NONE + error string

    def test_empty_cards(self) -> None:
        counts = count_by_category([])
        assert counts == {"all": 0, "manual": 0, "high": 0, "needs_review": 0, "errors": 0}

    def test_consistency_with_apply_category_filters(self) -> None:
        """count_by_category counts should match apply_category_filters results."""
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.MANUAL),
            _card(2, path="/f/b.pdf", confidence=Confidence.HIGH),
            _card(3, path="/f/c.pdf", confidence=Confidence.MEDIUM),
            _card(4, path="/f/d.pdf", confidence=Confidence.NONE),
        ]
        counts = count_by_category(cards)
        for key in ("manual", "high", "needs_review", "errors"):
            filtered = apply_category_filters(cards, [key])
            assert counts[key] == len(filtered), f"Mismatch for {key}"


# ---------------------------------------------------------------------------
# count_by_folder
# ---------------------------------------------------------------------------


class TestCountByFolder:
    def test_counts_per_folder(self) -> None:
        cards = [
            _card(1, path="/folder_a/file1.pdf"),
            _card(2, path="/folder_a/file2.pdf"),
            _card(3, path="/folder_b/file3.pdf"),
        ]
        counts = count_by_folder(cards, ["/folder_a", "/folder_b"])
        assert counts["all_folders"] == 3
        assert counts["/folder_a"] == 2
        assert counts["/folder_b"] == 1

    def test_empty_cards(self) -> None:
        counts = count_by_folder([], ["/folder_a"])
        assert counts["all_folders"] == 0
        assert counts["/folder_a"] == 0

    def test_card_with_multiple_paths(self) -> None:
        """Card with paths in multiple folders should be counted in each."""
        card = CardResult(
            id=1,
            file_paths=[Path("/folder_a/dup1.pdf"), Path("/folder_b/dup2.pdf")],
            primary_path=Path("/folder_a/dup1.pdf"),
            family_name="Test",
            confidence=Confidence.HIGH,
        )
        counts = count_by_folder([card], ["/folder_a", "/folder_b"])
        assert counts["/folder_a"] == 1
        assert counts["/folder_b"] == 1

    def test_no_folder_keys(self) -> None:
        cards = [_card(1, path="/folder/file.pdf")]
        counts = count_by_folder(cards, [])
        assert counts == {"all_folders": 1}


# ---------------------------------------------------------------------------
# compute_filtered_view
# ---------------------------------------------------------------------------


class TestComputeFilteredView:
    """Tests for the full filtered view pipeline."""

    def test_auto_reset_when_display_empty(self) -> None:
        """Category filters auto-reset when they produce empty results but search has matches."""
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.HIGH, family_name="Smith"),
            _card(2, path="/f/b.pdf", confidence=Confidence.LOW, family_name="Jones"),
        ]
        # Filter for "manual" which has 0 cards → should auto-reset
        view = compute_filtered_view(cards, "", ["manual"], ["all_folders"], ["/f"])
        assert view.filters_were_reset is True
        assert len(view.display_cards) == 2  # all cards shown after reset

    def test_cross_filter_counts(self) -> None:
        """Category counts reflect folder-filtered cards, not all cards."""
        cards = [
            _card(1, path="/a/x.pdf", confidence=Confidence.HIGH),
            _card(2, path="/b/y.pdf", confidence=Confidence.LOW),
        ]
        view = compute_filtered_view(cards, "", ["all"], ["/a"], ["/a", "/b"])
        # Only card 1 is in folder /a, so display should have 1
        assert len(view.display_cards) == 1
        # Category counts should reflect folder-filtered (only /a cards)
        assert view.category_counts["all"] == 1

    def test_alphabetical_sort(self) -> None:
        """Display cards are sorted alphabetically by filename."""
        cards = [
            _card(1, path="/f/Zebra.pdf", confidence=Confidence.HIGH),
            _card(2, path="/f/Alpha.pdf", confidence=Confidence.HIGH),
            _card(3, path="/f/Middle.pdf", confidence=Confidence.HIGH),
        ]
        view = compute_filtered_view(cards, "", ["all"], ["all_folders"], ["/f"])
        filenames = [c.filename for c in view.display_cards]
        assert filenames == ["Alpha.pdf", "Middle.pdf", "Zebra.pdf"]

    def test_no_reset_when_display_has_results(self) -> None:
        """No reset when category filters produce results."""
        cards = [
            _card(1, path="/f/a.pdf", confidence=Confidence.HIGH),
        ]
        view = compute_filtered_view(cards, "", ["high"], ["all_folders"], ["/f"])
        assert view.filters_were_reset is False
        assert len(view.display_cards) == 1
