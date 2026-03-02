"""Tests for scripts/generate_sample_cards/cli.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scripts.generate_sample_cards.cli import _process_card, validate_api_keys
from scripts.generate_sample_cards.image_generator import RateLimitGate
from scripts.generate_sample_cards.models import CardJob, CardSpec, FamilyMember


def _make_job() -> CardJob:
    return CardJob(index=1, family_name="Smith", holiday="Christmas", style="minimalist", back_page="none")


def _make_spec(page_count: int = 2, back_page_type: str | None = "blurb") -> CardSpec:
    return CardSpec(
        family_name="Smith",
        family_members=[FamilyMember("Alice", "parent", 40)],
        name_format="The Smith Family",
        holiday="Christmas",
        greeting_text="Merry Christmas!",
        backstory_blurb="Great year!",
        visual_style="minimalist",
        color_scheme=["#ff0000"],
        page_count=page_count,
        back_page_type=back_page_type,
        filename="smith.pdf",
        image_prompt="Family photo",
        back_greeting="Warm wishes!",
        back_photo_mode="single",
        back_image_prompt="Back scene",
    )


class TestValidateApiKeys:
    def test_returns_true_when_both_keys_set(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant", "OPENAI_API_KEY": "sk-oai"}):
            assert validate_api_keys() is True

    def test_returns_false_when_anthropic_key_missing(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-oai"}, clear=False):
            env = {"OPENAI_API_KEY": "sk-oai"}
            with patch.dict("os.environ", env):
                # Ensure ANTHROPIC_API_KEY is not set
                import os

                os.environ.pop("ANTHROPIC_API_KEY", None)
                result = validate_api_keys()
        assert result is False

    def test_returns_false_when_openai_key_missing(self) -> None:
        import os

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant"}):
            os.environ.pop("OPENAI_API_KEY", None)
            result = validate_api_keys()
        assert result is False

    def test_both_missing_returns_false(self) -> None:
        import os

        with patch.dict("os.environ", {}):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            result = validate_api_keys()
        assert result is False


class TestProcessCard:
    @pytest.mark.asyncio
    async def test_success_composes_pdf(self, tmp_path: Path) -> None:
        spec = _make_spec(page_count=1, back_page_type=None)
        job = _make_job()
        client = MagicMock()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        fake_images = [tmp_path / "front.png"]
        fake_images[0].write_bytes(b"fake png")

        with (
            patch(
                "scripts.generate_sample_cards.cli.generate_full_card_images_async",
                new_callable=AsyncMock,
                return_value=fake_images,
            ),
            patch("scripts.generate_sample_cards.cli.compose_pdf_from_images") as mock_compose,
        ):
            result = await _process_card(client, semaphore, gate, job, spec, 0, tmp_path, tmp_path, "gpt-image-1", 75)

        assert result is True
        mock_compose.assert_called_once()
        assert job.status == "done"

    @pytest.mark.asyncio
    async def test_no_images_returns_false(self, tmp_path: Path) -> None:
        spec = _make_spec()
        job = _make_job()
        client = MagicMock()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        with patch(
            "scripts.generate_sample_cards.cli.generate_full_card_images_async",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _process_card(client, semaphore, gate, job, spec, 0, tmp_path, tmp_path, "gpt-image-1", 75)

        assert result is False
        assert job.status == "error"

    @pytest.mark.asyncio
    async def test_compose_error_returns_false(self, tmp_path: Path) -> None:
        spec = _make_spec(page_count=1, back_page_type=None)
        job = _make_job()
        client = MagicMock()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        fake_images = [tmp_path / "front.png"]
        fake_images[0].write_bytes(b"fake")

        with (
            patch(
                "scripts.generate_sample_cards.cli.generate_full_card_images_async",
                new_callable=AsyncMock,
                return_value=fake_images,
            ),
            patch(
                "scripts.generate_sample_cards.cli.compose_pdf_from_images",
                side_effect=RuntimeError("write error"),
            ),
        ):
            result = await _process_card(client, semaphore, gate, job, spec, 0, tmp_path, tmp_path, "gpt-image-1", 75)

        assert result is False
        assert job.status == "error"
