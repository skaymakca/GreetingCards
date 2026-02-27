"""Tests for scripts/generate_sample_cards/spec_generator.py."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scripts.generate_sample_cards.models import CardSpec
from scripts.generate_sample_cards.spec_generator import generate_card_specs_async


def _make_msg(data: Any) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(data))]
    return msg


def _make_content_dict() -> dict[str, Any]:
    return {
        "family_members": [{"first_name": "Alice", "role": "parent", "age": 40}],
        "greeting_text": "Merry Christmas!",
        "image_prompt": "Family in snow",
        "backstory_blurb": "What a year!",
        "back_greeting": "Warm wishes!",
        "back_image_prompt": "Back scene",
    }


def _build_client_for_count(count: int) -> MagicMock:
    """Build a mock client with sequential responses for a full pipeline run."""
    names = [f"Family{i}" for i in range(count)]

    responses: list[MagicMock] = []
    # Phase 1a: family names (one call)
    responses.append(_make_msg(names))
    # Phase 1b: color schemes (one batch call for count <= 20)
    responses.append(_make_msg([["#ff0000"] for _ in range(count)]))
    # Phase 1c: subtitles (one batch call)
    responses.append(_make_msg([f"The Family{i} Family" for i in range(count)]))
    # Phase 2: card content (count calls)
    for _ in range(count):
        responses.append(_make_msg(_make_content_dict()))

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=responses)
    mock_client.close = AsyncMock()
    return mock_client


class TestGenerateCardSpecsAsync:
    @pytest.mark.asyncio
    async def test_returns_card_specs(self) -> None:
        count = 2
        mock_client = _build_client_for_count(count)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            specs = await generate_card_specs_async(count, "test-model")

        assert len(specs) == count
        assert all(isinstance(s, CardSpec) for s in specs)

    @pytest.mark.asyncio
    async def test_card_spec_has_correct_family_name(self) -> None:
        count = 1
        mock_client = _build_client_for_count(count)

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            specs = await generate_card_specs_async(count, "test-model")

        assert specs[0].family_name == "Family0"

    @pytest.mark.asyncio
    async def test_fixed_names_skips_ai_name_gen(self) -> None:
        fixed_names = ["Smith", "Jones"]
        count = len(fixed_names)

        responses: list[MagicMock] = []
        # With fixed_names: skip phase 1a (names), skip phase 1c (subtitles)
        # Phase 1b: color schemes
        responses.append(_make_msg([["#ff0000"] for _ in range(count)]))
        # Phase 2: card content (count calls)
        for _ in range(count):
            responses.append(_make_msg(_make_content_dict()))

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=responses)
        mock_client.close = AsyncMock()

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            specs = await generate_card_specs_async(count, "test-model", fixed_names=fixed_names)

        assert len(specs) == count
        # Family names should be from fixed_names
        assert {s.family_name for s in specs} == set(fixed_names)

    @pytest.mark.asyncio
    async def test_failed_card_content_skipped(self) -> None:
        count = 2

        responses: list[MagicMock] = []
        # Phase 1a: family names
        responses.append(_make_msg([f"Family{i}" for i in range(count)]))
        # Phase 1b: color schemes
        responses.append(_make_msg([["#ff0000"] for _ in range(count)]))
        # Phase 1c: subtitles
        responses.append(_make_msg([f"The Family{i} Family" for i in range(count)]))
        # Phase 2: both content calls fail
        for _ in range(count):
            for _ in range(3):  # MAX_RETRIES = 3
                responses.append(MagicMock(side_effect=RuntimeError("AI failure")))

        mock_client = MagicMock()
        # For failures, use exceptions directly
        call_count = [0]
        phase_1_responses = responses[:3]

        async def mock_create(**_kwargs: Any) -> MagicMock:
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(phase_1_responses):
                return phase_1_responses[idx]
            raise RuntimeError("AI failure")

        mock_client.messages.create = AsyncMock(side_effect=mock_create)
        mock_client.close = AsyncMock()

        with (
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            specs = await generate_card_specs_async(count, "test-model")

        assert specs == []

    @pytest.mark.asyncio
    async def test_fixed_names_override_count(self) -> None:
        fixed_names = ["Smith", "Jones", "Williams"]

        responses: list[MagicMock] = []
        # Phase 1b: color schemes (3 items, not 1)
        responses.append(_make_msg([["#ff0000"] for _ in range(len(fixed_names))]))
        # Phase 2: card content
        for _ in range(len(fixed_names)):
            responses.append(_make_msg(_make_content_dict()))

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=responses)
        mock_client.close = AsyncMock()

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            specs = await generate_card_specs_async(
                1,  # count=1 but fixed_names overrides to 3
                "test-model",
                fixed_names=fixed_names,
            )

        assert len(specs) == 3
