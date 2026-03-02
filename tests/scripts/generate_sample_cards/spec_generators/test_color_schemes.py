"""Tests for scripts/generate_sample_cards/spec_generators/color_schemes.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.generate_sample_cards.spec_generators.color_schemes import (
    BATCH_SIZE,
    _generate_batch,
    generate_color_schemes_async,
)


def _make_mock_client(response: list[list[str]]) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(response))]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    return mock_client


def _make_cards(count: int) -> list[dict[str, Any]]:
    return [{"holiday": "Christmas", "visual_style": "minimalist"} for _ in range(count)]


class TestGenerateBatch:
    @pytest.mark.asyncio
    async def test_returns_schemes_list(self) -> None:
        schemes = [["#ff0000", "#00ff00"], ["#0000ff"]]
        client = _make_mock_client(schemes)
        pairs = [("Christmas", "minimalist"), ("Easter", "playful")]
        result = await _generate_batch(client, pairs, "test-model")
        assert result == schemes

    @pytest.mark.asyncio
    async def test_calls_api_once(self) -> None:
        client = _make_mock_client([["#ff0000"]])
        await _generate_batch(client, [("Christmas", "minimalist")], "test-model")
        client.messages.create.assert_called_once()


class TestGenerateColorSchemesAsync:
    @pytest.mark.asyncio
    async def test_returns_one_scheme_per_card(self) -> None:
        cards = _make_cards(3)
        schemes = [["#ff0000"], ["#00ff00"], ["#0000ff"]]
        client = _make_mock_client(schemes)
        result = await generate_color_schemes_async(client, cards, "test-model")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_pads_with_fallback_when_short(self) -> None:
        cards = _make_cards(5)
        # API returns only 3 schemes for 5 cards
        schemes = [["#ff0000"], ["#00ff00"], ["#0000ff"]]
        client = _make_mock_client(schemes)
        result = await generate_color_schemes_async(client, cards, "test-model")
        assert len(result) == 5
        # Padded entries should use fallback
        assert result[3] == ["#333333", "#666666", "#999999"]
        assert result[4] == ["#333333", "#666666", "#999999"]

    @pytest.mark.asyncio
    async def test_truncates_when_api_returns_extra(self) -> None:
        cards = _make_cards(2)
        schemes = [["#ff0000"], ["#00ff00"], ["#0000ff"], ["#ffff00"]]
        client = _make_mock_client(schemes)
        result = await generate_color_schemes_async(client, cards, "test-model")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_batching_with_many_cards(self) -> None:
        # More than BATCH_SIZE cards → multiple batches
        count = BATCH_SIZE + 5
        cards = _make_cards(count)

        call_count = [0]

        async def mock_create(**_kwargs: Any) -> MagicMock:
            call_count[0] += 1
            mock_msg = MagicMock()
            mock_msg.content = [MagicMock(text=json.dumps([["#ff0000"]] * count))]
            return mock_msg

        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=mock_create)

        result = await generate_color_schemes_async(client, cards, "test-model")
        # Should have made 2 batch calls (ceil(25/20) = 2)
        assert call_count[0] == 2
        assert len(result) == count
