"""Tests for scripts/generate_sample_cards/spec_generators/family_names.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.generate_sample_cards.spec_generators.family_names import generate_family_names_async


def _make_mock_client(names: list[str]) -> MagicMock:
    """Build a mock AsyncAnthropic client that returns the given names as JSON."""
    import json

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(names))]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    return mock_client


class TestGenerateFamilyNamesAsync:
    @pytest.mark.asyncio
    async def test_returns_names_list(self) -> None:
        client = _make_mock_client(["Smith", "Jones", "Williams"])
        result = await generate_family_names_async(client, 3, "claude-haiku-4-5")
        assert result == ["Smith", "Jones", "Williams"]

    @pytest.mark.asyncio
    async def test_deduplicates_names(self) -> None:
        client = _make_mock_client(["Smith", "Smith", "Jones"])
        result = await generate_family_names_async(client, 3, "claude-haiku-4-5")
        assert result.count("Smith") == 1

    @pytest.mark.asyncio
    async def test_truncates_to_count(self) -> None:
        client = _make_mock_client(["A", "B", "C", "D", "E"])
        result = await generate_family_names_async(client, 3, "claude-haiku-4-5")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_returns_fewer_if_all_duplicates(self) -> None:
        client = _make_mock_client(["Smith", "Smith", "Smith"])
        result = await generate_family_names_async(client, 3, "claude-haiku-4-5")
        assert len(result) == 1  # only one unique name

    @pytest.mark.asyncio
    async def test_calls_api_with_correct_count(self) -> None:
        client = _make_mock_client(["A", "B", "C"])
        await generate_family_names_async(client, 5, "claude-haiku-4-5")
        call_args = client.messages.create.call_args
        content = call_args.kwargs.get("messages", [{}])[0].get("content", "")
        assert "5" in content

    @pytest.mark.asyncio
    async def test_uses_specified_model(self) -> None:
        client = _make_mock_client(["Smith"])
        await generate_family_names_async(client, 1, "claude-test-model")
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs.get("model") == "claude-test-model"
