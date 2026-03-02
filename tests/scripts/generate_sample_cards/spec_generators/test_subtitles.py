"""Tests for scripts/generate_sample_cards/spec_generators/subtitles.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.generate_sample_cards.spec_generators.subtitles import (
    BATCH_SIZE,
    _generate_batch,
    generate_subtitles_async,
)


def _make_mock_client(response: list[str]) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(response))]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    return mock_client


def _make_cards(count: int) -> list[dict[str, Any]]:
    return [{"family_name": f"Family{i}", "family_size_hint": "couple", "holiday": "Christmas"} for i in range(count)]


class TestGenerateBatch:
    @pytest.mark.asyncio
    async def test_returns_subtitle_list(self) -> None:
        subtitles = ["The Smiths", "The Jones Family"]
        client = _make_mock_client(subtitles)
        families = [("Smith", "couple", "Christmas"), ("Jones", "small family", "Easter")]
        result = await _generate_batch(client, families, "test-model")
        assert result == subtitles


class TestGenerateSubtitlesAsync:
    @pytest.mark.asyncio
    async def test_returns_one_subtitle_per_card(self) -> None:
        cards = _make_cards(3)
        subtitles = ["Sub 1", "Sub 2", "Sub 3"]
        client = _make_mock_client(subtitles)
        result = await generate_subtitles_async(client, cards, "test-model")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_pads_with_fallback_when_short(self) -> None:
        cards = _make_cards(4)
        subtitles = ["Sub 1", "Sub 2"]  # Only 2 for 4 cards
        client = _make_mock_client(subtitles)
        result = await generate_subtitles_async(client, cards, "test-model")
        assert len(result) == 4
        # Padded entries should use "The {family_name} Family" format
        assert result[2] == "The Family2 Family"
        assert result[3] == "The Family3 Family"

    @pytest.mark.asyncio
    async def test_truncates_when_api_returns_extra(self) -> None:
        cards = _make_cards(2)
        subtitles = ["Sub 1", "Sub 2", "Sub 3", "Sub 4"]
        client = _make_mock_client(subtitles)
        result = await generate_subtitles_async(client, cards, "test-model")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_batching_with_many_cards(self) -> None:
        count = BATCH_SIZE + 3
        cards = _make_cards(count)
        call_count = [0]

        async def mock_create(**kwargs: Any) -> MagicMock:
            call_count[0] += 1
            mock_msg = MagicMock()
            mock_msg.content = [MagicMock(text=json.dumps([f"Sub{i}" for i in range(count)]))]
            return mock_msg

        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=mock_create)

        result = await generate_subtitles_async(client, cards, "test-model")
        assert call_count[0] == 2  # ceil((BATCH_SIZE+3)/BATCH_SIZE) = 2
        assert len(result) == count
