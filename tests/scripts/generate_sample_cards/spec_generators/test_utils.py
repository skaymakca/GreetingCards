"""Tests for scripts/generate_sample_cards/spec_generators/utils.py."""

from __future__ import annotations

import pytest
from scripts.generate_sample_cards.spec_generators.utils import extract_json


class TestExtractJson:
    def test_clean_array(self) -> None:
        result = extract_json('["Smith", "Jones"]')
        assert result == ["Smith", "Jones"]

    def test_clean_object(self) -> None:
        result = extract_json('{"name": "Smith", "count": 3}')
        assert result == {"name": "Smith", "count": 3}

    def test_code_fence_json(self) -> None:
        text = '```json\n["Smith", "Jones"]\n```'
        result = extract_json(text)
        assert result == ["Smith", "Jones"]

    def test_code_fence_no_language(self) -> None:
        text = '```\n{"key": "value"}\n```'
        result = extract_json(text)
        assert result == {"key": "value"}

    def test_leading_prose(self) -> None:
        text = 'Here are the names: ["Smith", "Jones", "Williams"]'
        result = extract_json(text)
        assert result == ["Smith", "Jones", "Williams"]

    def test_trailing_prose(self) -> None:
        text = '["Smith", "Jones"]\n\nHope that helps!'
        result = extract_json(text)
        assert result == ["Smith", "Jones"]

    def test_leading_and_trailing_prose(self) -> None:
        text = 'Sure! Here you go:\n["A", "B", "C"]\nLet me know if you need more.'
        result = extract_json(text)
        assert result == ["A", "B", "C"]

    def test_nested_object(self) -> None:
        text = '{"family": {"name": "Smith"}, "count": 2}'
        result = extract_json(text)
        assert result == {"family": {"name": "Smith"}, "count": 2}

    def test_nested_array_of_arrays(self) -> None:
        text = '[["#ff0000", "#00ff00"], ["#0000ff"]]'
        result = extract_json(text)
        assert result == [["#ff0000", "#00ff00"], ["#0000ff"]]

    def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            extract_json("this is not json at all")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            extract_json("")

    def test_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            extract_json("   \n\t  ")

    @pytest.mark.parametrize(
        "text,expected",
        [
            ('["A"]', ["A"]),
            ('```json\n["B"]\n```', ["B"]),
            ('Result: {"x": 1}', {"x": 1}),
        ],
    )
    def test_parametrized(self, text: str, expected: object) -> None:
        assert extract_json(text) == expected
