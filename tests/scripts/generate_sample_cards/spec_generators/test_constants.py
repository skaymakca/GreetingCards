"""Tests for scripts/generate_sample_cards/spec_generators/constants.py."""

from __future__ import annotations

from scripts.generate_sample_cards.spec_generators.constants import (
    BACK_PAGE_TYPES,
    BACK_PHOTO_MODES,
    FAMILY_SIZE_HINTS,
    FILENAME_TEMPLATES,
    HOLIDAYS,
    VISUAL_STYLES,
)


class TestHolidays:
    def test_non_empty(self) -> None:
        assert len(HOLIDAYS) > 0

    def test_no_duplicates(self) -> None:
        assert len(HOLIDAYS) == len(set(HOLIDAYS))

    def test_all_strings(self) -> None:
        for h in HOLIDAYS:
            assert isinstance(h, str) and h


class TestVisualStyles:
    def test_non_empty(self) -> None:
        assert len(VISUAL_STYLES) > 0

    def test_no_duplicates(self) -> None:
        assert len(VISUAL_STYLES) == len(set(VISUAL_STYLES))

    def test_all_strings(self) -> None:
        for s in VISUAL_STYLES:
            assert isinstance(s, str) and s


class TestFilenameTemplates:
    def test_non_empty(self) -> None:
        assert len(FILENAME_TEMPLATES) > 0

    def test_no_duplicates(self) -> None:
        assert len(FILENAME_TEMPLATES) == len(set(FILENAME_TEMPLATES))

    def test_all_end_with_pdf(self) -> None:
        for tmpl in FILENAME_TEMPLATES:
            assert tmpl.endswith(".pdf"), f"Template does not end with .pdf: {tmpl!r}"


class TestFamilySizeHints:
    def test_non_empty(self) -> None:
        assert len(FAMILY_SIZE_HINTS) > 0

    def test_weights_sum_to_one(self) -> None:
        total = sum(w for _, w in FAMILY_SIZE_HINTS)
        assert abs(total - 1.0) < 1e-9

    def test_all_hints_non_empty(self) -> None:
        for hint, _ in FAMILY_SIZE_HINTS:
            assert isinstance(hint, str) and hint


class TestBackPageTypes:
    def test_non_empty(self) -> None:
        assert len(BACK_PAGE_TYPES) > 0

    def test_weights_sum_to_one(self) -> None:
        total = sum(w for _, w in BACK_PAGE_TYPES)
        assert abs(total - 1.0) < 1e-9

    def test_valid_types(self) -> None:
        valid = {"blurb", "photo"}
        for t, _ in BACK_PAGE_TYPES:
            assert t in valid


class TestBackPhotoModes:
    def test_non_empty(self) -> None:
        assert len(BACK_PHOTO_MODES) > 0

    def test_weights_sum_to_one(self) -> None:
        total = sum(w for _, w in BACK_PHOTO_MODES)
        assert abs(total - 1.0) < 1e-9

    def test_valid_modes(self) -> None:
        valid = {"single", "collage"}
        for m, _ in BACK_PHOTO_MODES:
            assert m in valid
