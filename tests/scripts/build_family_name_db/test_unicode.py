"""Tests for scripts/build_family_name_db/_unicode.py."""

from __future__ import annotations

from scripts.build_family_name_db._unicode import UNICODE_SPECIAL


class TestUnicodeSpecial:
    def test_all_keys_are_single_chars(self) -> None:
        for key in UNICODE_SPECIAL:
            assert len(key) == 1, f"Key {key!r} is not a single character"

    def test_all_values_are_ascii(self) -> None:
        for key, value in UNICODE_SPECIAL.items():
            assert value.isascii(), f"Value {value!r} for key {key!r} is not ASCII"

    def test_contains_german_sharp_s(self) -> None:
        assert "ß" in UNICODE_SPECIAL
        assert UNICODE_SPECIAL["ß"] == "ss"

    def test_contains_o_with_stroke(self) -> None:
        assert "ø" in UNICODE_SPECIAL
        assert UNICODE_SPECIAL["ø"] == "o"

    def test_contains_ae_ligature(self) -> None:
        assert "æ" in UNICODE_SPECIAL
        assert UNICODE_SPECIAL["æ"] == "ae"

    def test_non_empty(self) -> None:
        assert len(UNICODE_SPECIAL) > 0

    def test_no_empty_values(self) -> None:
        for key, value in UNICODE_SPECIAL.items():
            assert value, f"Empty value for key {key!r}"
