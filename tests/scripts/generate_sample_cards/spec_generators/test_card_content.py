"""Tests for scripts/generate_sample_cards/spec_generators/card_content.py."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest
from scripts.generate_sample_cards.image_generator import RateLimitGate
from scripts.generate_sample_cards.spec_generators.card_content import generate_card_content_async


def _make_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(10)


def _make_gate() -> RateLimitGate:
    return RateLimitGate()


def _make_mock_console() -> MagicMock:
    return MagicMock(spec=["print"])


def _make_constraints(back_page_type: str | None = None) -> dict[str, Any]:
    return {
        "holiday": "Christmas",
        "subtitle": "The Smith Family",
        "family_size_hint": "couple",
        "visual_style": "minimalist",
        "back_page_type": back_page_type,
        "back_photo_mode": "single",
    }


def _make_content() -> dict[str, Any]:
    return {
        "family_members": [{"first_name": "Alice", "role": "parent", "age": 40}],
        "greeting_text": "Merry Christmas!",
        "image_prompt": "A family in the snow",
        "backstory_blurb": "What a year!",
    }


def _make_mock_client(content: dict[str, Any]) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(content))]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    return mock_client


class TestGenerateCardContentAsync:
    @pytest.mark.asyncio
    async def test_single_card_template_selected(self) -> None:
        client = _make_mock_client(_make_content())
        constraints = _make_constraints(back_page_type=None)  # 1-page card

        result = await generate_card_content_async(
            client,
            _make_semaphore(),
            _make_gate(),
            "Smith",
            constraints,
            "test-model",
            _make_mock_console(),
            0,
        )

        assert result is not None
        assert "greeting_text" in result

    @pytest.mark.asyncio
    async def test_blurb_template_selected(self) -> None:
        content = {**_make_content(), "backstory_blurb": "This year was amazing!"}
        client = _make_mock_client(content)
        constraints = _make_constraints(back_page_type="blurb")

        result = await generate_card_content_async(
            client,
            _make_semaphore(),
            _make_gate(),
            "Smith",
            constraints,
            "test-model",
            _make_mock_console(),
            0,
        )

        assert result is not None
        assert "backstory_blurb" in result

    @pytest.mark.asyncio
    async def test_photo_template_selected(self) -> None:
        content = {
            **_make_content(),
            "back_greeting": "Warm wishes!",
            "back_image_prompt": "Cozy scene",
        }
        client = _make_mock_client(content)
        constraints = _make_constraints(back_page_type="photo")

        result = await generate_card_content_async(
            client,
            _make_semaphore(),
            _make_gate(),
            "Smith",
            constraints,
            "test-model",
            _make_mock_console(),
            0,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_retry(self) -> None:
        content = _make_content()
        good_msg = MagicMock()
        good_msg.content = [MagicMock(text=json.dumps(content))]

        # Build a fake RateLimitError
        mock_response = MagicMock()
        mock_response.headers = {"retry-after-ms": "100"}
        mock_response.status_code = 429
        rate_limit_exc = anthropic.RateLimitError(message="rate limit", response=mock_response, body={})

        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=[rate_limit_exc, good_msg])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await generate_card_content_async(
                client,
                _make_semaphore(),
                _make_gate(),
                "Smith",
                _make_constraints(),
                "test-model",
                _make_mock_console(),
                0,
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_none(self) -> None:
        client = MagicMock()
        client.messages.create = AsyncMock(side_effect=RuntimeError("persistent error"))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await generate_card_content_async(
                client,
                _make_semaphore(),
                _make_gate(),
                "Smith",
                _make_constraints(),
                "test-model",
                _make_mock_console(),
                0,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_parsed_dict(self) -> None:
        content = _make_content()
        client = _make_mock_client(content)

        result = await generate_card_content_async(
            client,
            _make_semaphore(),
            _make_gate(),
            "Smith",
            _make_constraints(),
            "test-model",
            _make_mock_console(),
            0,
        )

        assert isinstance(result, dict)
