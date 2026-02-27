"""Tests for scripts/generate_sample_cards/spec_generators/formatting.py."""

from __future__ import annotations

import random

import pytest
from scripts.generate_sample_cards.spec_generators.constants import HOLIDAYS, VISUAL_STYLES
from scripts.generate_sample_cards.spec_generators.formatting import (
    assign_deterministic_fields,
    build_family_members,
    fill_filename,
)


class TestAssignDeterministicFields:
    def test_returns_correct_count(self) -> None:
        cards = assign_deterministic_fields(10)
        assert len(cards) == 10

    def test_single_card(self) -> None:
        cards = assign_deterministic_fields(1)
        assert len(cards) == 1

    def test_all_holidays_present_across_cards(self) -> None:
        count = len(HOLIDAYS) * 3
        cards = assign_deterministic_fields(count)
        found_holidays = {c["holiday"] for c in cards}
        # All holidays should be present (round-robin)
        assert found_holidays == set(HOLIDAYS)

    def test_all_styles_present_across_cards(self) -> None:
        count = len(VISUAL_STYLES) * 3
        cards = assign_deterministic_fields(count)
        found_styles = {c["visual_style"] for c in cards}
        assert found_styles == set(VISUAL_STYLES)

    def test_page_count_is_1_or_2(self) -> None:
        cards = assign_deterministic_fields(50)
        for card in cards:
            assert card["page_count"] in (1, 2)

    def test_back_page_type_logic(self) -> None:
        cards = assign_deterministic_fields(100)
        for card in cards:
            if card["page_count"] == 1:
                assert card["back_page_type"] is None
                assert card["back_photo_mode"] is None
            else:
                assert card["back_page_type"] in ("blurb", "photo", None)

    def test_back_photo_mode_only_for_photo_type(self) -> None:
        cards = assign_deterministic_fields(100)
        for card in cards:
            if card.get("back_page_type") != "photo":
                assert card["back_photo_mode"] is None
            else:
                assert card["back_photo_mode"] in ("single", "collage")

    def test_required_keys_present(self) -> None:
        cards = assign_deterministic_fields(5)
        expected_keys = {
            "holiday",
            "visual_style",
            "filename_template",
            "page_count",
            "back_page_type",
            "back_photo_mode",
            "family_size_hint",
        }
        for card in cards:
            assert set(card.keys()) == expected_keys


class TestFillFilename:
    def _rng(self) -> random.Random:
        return random.Random(42)

    def test_img_template(self) -> None:
        result = fill_filename("IMG_{digits4}.pdf", "Smith", "Christmas", self._rng())
        assert result.startswith("IMG_")
        assert result.endswith(".pdf")
        parts = result[4:-4]  # strip "IMG_" and ".pdf"
        assert parts.isdigit()
        assert len(parts) == 4

    def test_family_name_substituted(self) -> None:
        result = fill_filename("{holiday} Card - {family_name} Family.pdf", "Johnson", "Easter", self._rng())
        assert "Johnson" in result
        assert "Easter" in result
        assert result.endswith(".pdf")

    def test_year_in_range(self) -> None:
        rng = random.Random(0)
        results = [fill_filename("holiday_card_{year}.pdf", "X", "Y", rng) for _ in range(20)]
        for r in results:
            year_str = r.replace("holiday_card_", "").replace(".pdf", "")
            assert 2022 <= int(year_str) <= 2025

    def test_all_templates_resolved(self) -> None:
        from scripts.generate_sample_cards.spec_generators.constants import FILENAME_TEMPLATES

        rng = random.Random(7)
        for tmpl in FILENAME_TEMPLATES:
            result = fill_filename(tmpl, "Jones", "Christmas", rng)
            assert "{" not in result, f"Unresolved placeholder in: {result!r} (template: {tmpl!r})"

    def test_holiday_lower_uses_underscore(self) -> None:
        result = fill_filename("{holiday_lower}.pdf", "X", "Chinese New Year", self._rng())
        assert "chinese_new_year" in result


class TestBuildFamilyMembers:
    def test_basic_conversion(self) -> None:
        raw = [{"first_name": "Alice", "role": "parent", "age": 40}]
        members = build_family_members(raw)
        assert len(members) == 1
        assert members[0].first_name == "Alice"
        assert members[0].role == "parent"
        assert members[0].age == 40

    def test_age_none_when_missing(self) -> None:
        raw = [{"first_name": "Fido", "role": "pet"}]
        members = build_family_members(raw)
        assert members[0].age is None

    def test_age_none_explicit(self) -> None:
        raw = [{"first_name": "Bob", "role": "child", "age": None}]
        members = build_family_members(raw)
        assert members[0].age is None

    def test_multiple_members(self) -> None:
        raw = [
            {"first_name": "A", "role": "parent", "age": 35},
            {"first_name": "B", "role": "child", "age": 8},
            {"first_name": "C", "role": "pet"},
        ]
        members = build_family_members(raw)
        assert len(members) == 3
        assert members[2].age is None

    def test_empty_list(self) -> None:
        assert build_family_members([]) == []
