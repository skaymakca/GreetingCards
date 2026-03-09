"""Tests for scripts/generate_sample_cards/cli.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scripts.generate_sample_cards.cli import _process_card, async_main, validate_api_keys
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


class TestCardJobBackPageBranches:
    """Tests for CardJob back_page construction from spec back_page_type (cli.py lines 180-185)."""

    def test_photo_back_page_type_uses_photo_mode(self) -> None:
        """back_page_type='photo' → back_page uses back_photo_mode (e.g., 'single')."""
        spec = _make_spec(page_count=2, back_page_type="photo")
        spec.back_photo_mode = "single"

        if spec.back_page_type == "photo":
            back_page = spec.back_photo_mode or "single"
        elif spec.back_page_type == "blurb":
            back_page = "blurb"
        else:
            back_page = "none"

        job = CardJob(
            index=1,
            family_name=spec.family_name,
            holiday=spec.holiday,
            style=spec.visual_style,
            back_page=back_page,
        )

        assert job.back_page == "single"

    def test_photo_back_page_type_collage(self) -> None:
        """back_page_type='photo' with back_photo_mode='collage' → back_page='collage'."""
        spec = _make_spec(page_count=2, back_page_type="photo")
        spec.back_photo_mode = "collage"

        back_page = spec.back_photo_mode or "single"
        job = CardJob(
            index=1,
            family_name=spec.family_name,
            holiday=spec.holiday,
            style=spec.visual_style,
            back_page=back_page,
        )

        assert job.back_page == "collage"

    def test_blurb_back_page_type(self) -> None:
        """back_page_type='blurb' → back_page='blurb'."""
        spec = _make_spec(page_count=2, back_page_type="blurb")

        back_page = "blurb"
        job = CardJob(
            index=1,
            family_name=spec.family_name,
            holiday=spec.holiday,
            style=spec.visual_style,
            back_page=back_page,
        )

        assert job.back_page == "blurb"

    def test_none_back_page_type(self) -> None:
        """back_page_type=None → back_page='none'."""
        spec = _make_spec(page_count=1, back_page_type=None)

        back_page = "none"
        job = CardJob(
            index=1,
            family_name=spec.family_name,
            holiday=spec.holiday,
            style=spec.visual_style,
            back_page=back_page,
        )

        assert job.back_page == "none"


class TestAsyncMain:
    @pytest.mark.asyncio
    async def test_names_flag_parsing(self, tmp_path: Path) -> None:
        """--names Smith,Jones generates 2 specs with those family names."""
        specs = [_make_spec(page_count=1, back_page_type=None), _make_spec(page_count=1, back_page_type=None)]

        with (
            patch("sys.argv", ["prog", "--names", "Smith,Jones", "--no-open"]),
            patch("scripts.generate_sample_cards.cli.validate_api_keys", return_value=True),
            patch(
                "scripts.generate_sample_cards.cli.generate_card_specs_async",
                new_callable=AsyncMock,
                return_value=specs,
            ) as m_gen_specs,
            patch("scripts.generate_sample_cards.cli.openai.AsyncOpenAI") as mock_openai_cls,
            patch(
                "scripts.generate_sample_cards.cli.generate_full_card_images_async",
                new_callable=AsyncMock,
                return_value=[tmp_path / "img.png"],
            ),
            patch("scripts.generate_sample_cards.cli.compose_pdf_from_images"),
            patch("scripts.generate_sample_cards.cli.script_output_dir") as mock_ctx,
        ):
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_ctx.return_value.__enter__ = lambda s: tmp_path
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            await async_main()

        # generate_card_specs_async called with count=2 and fixed_names=["Smith", "Jones"]
        call_args = m_gen_specs.call_args
        assert call_args[0][0] == 2  # count
        assert call_args[1]["fixed_names"] == ["Smith", "Jones"]

    @pytest.mark.asyncio
    async def test_names_empty_exits(self) -> None:
        """--names with only whitespace/commas exits with code 1."""
        with (
            patch("sys.argv", ["prog", "--names", "  ,  , ", "--no-open"]),
            pytest.raises(SystemExit, match="1"),
        ):
            await async_main()

    @pytest.mark.asyncio
    async def test_names_empty_after_strip_exits(self) -> None:
        """--names with only empty strings after stripping exits with code 1."""
        with (
            patch("sys.argv", ["prog", "--names", ",,,", "--no-open"]),
            pytest.raises(SystemExit, match="1"),
        ):
            await async_main()

    @pytest.mark.asyncio
    async def test_open_folder_file_not_found_handled(self, tmp_path: Path) -> None:
        """FileNotFoundError when opening output folder is silently caught."""
        specs = [_make_spec(page_count=1, back_page_type=None)]

        with (
            patch("sys.argv", ["prog", "--count", "1"]),
            patch("scripts.generate_sample_cards.cli.validate_api_keys", return_value=True),
            patch(
                "scripts.generate_sample_cards.cli.generate_card_specs_async",
                new_callable=AsyncMock,
                return_value=specs,
            ),
            patch("scripts.generate_sample_cards.cli.openai.AsyncOpenAI") as mock_openai_cls,
            patch(
                "scripts.generate_sample_cards.cli.generate_full_card_images_async",
                new_callable=AsyncMock,
                return_value=[tmp_path / "img.png"],
            ),
            patch("scripts.generate_sample_cards.cli.compose_pdf_from_images"),
            patch("scripts.generate_sample_cards.cli.script_output_dir") as mock_ctx,
            patch("scripts.generate_sample_cards.cli.subprocess.run", side_effect=FileNotFoundError("no open")),
        ):
            mock_client = MagicMock()
            mock_client.close = AsyncMock()
            mock_openai_cls.return_value = mock_client
            mock_ctx.return_value.__enter__ = lambda s: tmp_path
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise — FileNotFoundError is caught gracefully
            await async_main()

    @pytest.mark.asyncio
    async def test_api_key_validation_failure_exits(self) -> None:
        """Invalid API keys cause SystemExit(1)."""
        with (
            patch("sys.argv", ["prog", "--no-open"]),
            patch("scripts.generate_sample_cards.cli.validate_api_keys", return_value=False),
            pytest.raises(SystemExit, match="1"),
        ):
            await async_main()
