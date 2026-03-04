"""Tests for scripts/generate_sample_cards/image_generator.py."""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from scripts.generate_sample_cards.image_generator import (
    RateLimitGate,
    _parse_retry_after,
    _spell_out,
    build_full_card_prompt,
    generate_full_card_images_async,
    generate_image_openai_async,
)
from scripts.generate_sample_cards.models import CardJob, CardSpec, FamilyMember


def _make_job(status: str = "waiting") -> CardJob:
    return CardJob(
        index=1, family_name="Smith", holiday="Christmas", style="minimalist", back_page="none", status=status
    )


def _make_spec(back_page_type: str | None = None, back_photo_mode: str = "single") -> CardSpec:
    return CardSpec(
        family_name="Smith",
        family_members=[FamilyMember("Alice", "parent", 40)],
        name_format="The Smith Family",
        holiday="Christmas",
        greeting_text="Merry Christmas!",
        backstory_blurb="Great year!",
        visual_style="minimalist",
        color_scheme=["#ff0000", "#00ff00"],
        page_count=2 if back_page_type else 1,
        back_page_type=back_page_type,
        filename="card.pdf",
        image_prompt="Family in snow",
        back_greeting="Warm wishes!",
        back_photo_mode=back_photo_mode,
        back_image_prompt="Back scene",
    )


class TestRateLimitGate:
    def test_no_pause_initially(self) -> None:
        gate = RateLimitGate()
        assert gate._resume_at == 0

    def test_pause_sets_resume_time(self) -> None:
        gate = RateLimitGate()
        before = time.monotonic()
        gate.pause(10)
        assert gate._resume_at >= before + 9.9  # at least ~10 seconds from now

    def test_pause_takes_max(self) -> None:
        gate = RateLimitGate()
        gate.pause(5)
        first = gate._resume_at
        gate.pause(3)  # shorter — should not override
        assert gate._resume_at == first  # max preserved

    def test_pause_longer_overrides(self) -> None:
        gate = RateLimitGate()
        gate.pause(5)
        gate.pause(30)  # longer — should override
        assert gate._resume_at > time.monotonic() + 25

    @pytest.mark.asyncio
    async def test_wait_if_paused_does_not_sleep_when_not_paused(self) -> None:
        gate = RateLimitGate()
        job = _make_job()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await gate.wait_if_paused(job)
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_if_paused_sleeps_when_paused(self) -> None:
        gate = RateLimitGate()
        gate.pause(100)  # set 100s pause
        job = _make_job()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await gate.wait_if_paused(job)
            mock_sleep.assert_called_once()
            assert job.status == "rate_limited"


class TestParseRetryAfter:
    def _make_exc(self, headers: dict) -> openai.RateLimitError:
        mock_response = MagicMock()
        mock_response.headers = headers
        mock_response.status_code = 429
        return openai.RateLimitError(message="rate limit", response=mock_response, body={})

    def test_retry_after_ms_header(self) -> None:
        exc = self._make_exc({"retry-after-ms": "2500"})
        assert _parse_retry_after(exc) == 2.5

    def test_retry_after_seconds_header(self) -> None:
        exc = self._make_exc({"retry-after": "15"})
        assert _parse_retry_after(exc) == 15.0

    def test_fallback_when_no_headers(self) -> None:
        exc = self._make_exc({})
        assert _parse_retry_after(exc) == 10.0

    def test_retry_after_ms_takes_priority(self) -> None:
        exc = self._make_exc({"retry-after-ms": "1000", "retry-after": "30"})
        assert _parse_retry_after(exc) == 1.0

    def test_non_numeric_retry_after_ms(self) -> None:
        exc = self._make_exc({"retry-after-ms": "invalid"})
        assert _parse_retry_after(exc) == 10.0

    def test_non_numeric_retry_after(self) -> None:
        exc = self._make_exc({"retry-after": "invalid"})
        assert _parse_retry_after(exc) == 10.0


class TestSpellOut:
    def test_single_word(self) -> None:
        assert _spell_out("Smith") == "S-M-I-T-H"

    def test_single_letter(self) -> None:
        assert _spell_out("A") == "A"

    def test_lowercase_uppercased(self) -> None:
        result = _spell_out("jones")
        assert result == "J-O-N-E-S"


class TestBuildFullCardPrompt:
    def test_front_prompt_contains_name_format(self) -> None:
        spec = _make_spec()
        result = build_full_card_prompt(spec, "front")
        assert "The Smith Family" in result

    def test_front_prompt_contains_greeting(self) -> None:
        spec = _make_spec()
        result = build_full_card_prompt(spec, "front")
        assert "Merry Christmas!" in result

    def test_front_prompt_spells_name(self) -> None:
        spec = _make_spec()
        result = build_full_card_prompt(spec, "front")
        # "The" would be T-H-E but we spell the full name_format
        assert "T-H-E" in result

    def test_back_blurb_prompt(self) -> None:
        spec = _make_spec(back_page_type="blurb")
        result = build_full_card_prompt(spec, "back")
        assert "Great year!" in result  # backstory_blurb

    def test_back_photo_single_prompt(self) -> None:
        spec = _make_spec(back_page_type="photo", back_photo_mode="single")
        result = build_full_card_prompt(spec, "back")
        assert "Warm wishes!" in result  # back_greeting

    def test_back_photo_collage_prompt(self) -> None:
        spec = _make_spec(back_page_type="photo", back_photo_mode="collage")
        result = build_full_card_prompt(spec, "back")
        assert "Warm wishes!" in result


class TestGenerateImageOpenaiAsync:
    def _make_openai_client(self, b64_data: bytes) -> MagicMock:
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(b64_data).decode()
        mock_image.url = None
        mock_result = MagicMock()
        mock_result.data = [mock_image]
        mock_client = MagicMock()
        mock_client.images.generate = AsyncMock(return_value=mock_result)
        mock_client.images.edit = AsyncMock(return_value=mock_result)
        return mock_client

    @pytest.mark.asyncio
    async def test_success_saves_file(self, tmp_path: Path) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        client = self._make_openai_client(fake_png)
        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        result = await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        assert result is True
        assert output.exists()
        assert output.read_bytes() == fake_png

    @pytest.mark.asyncio
    async def test_rate_limit_retries_and_succeeds(self, tmp_path: Path) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        good_result = MagicMock()
        good_result.data = [MagicMock(b64_json=base64.b64encode(fake_png).decode(), url=None)]

        mock_response = MagicMock()
        mock_response.headers = {"retry-after-ms": "50"}
        mock_response.status_code = 429
        rate_limit_exc = openai.RateLimitError(message="rate limit", response=mock_response, body={})

        client = MagicMock()
        client.images.generate = AsyncMock(side_effect=[rate_limit_exc, good_result])

        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        assert result is True

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_returns_false(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.images.generate = AsyncMock(side_effect=RuntimeError("persistent failure"))
        client.images.edit = AsyncMock(side_effect=RuntimeError("persistent failure"))

        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        assert result is False

    @pytest.mark.asyncio
    async def test_reference_image_uses_edit_endpoint(self, tmp_path: Path) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        client = self._make_openai_client(fake_png)

        ref_image = tmp_path / "ref.png"
        ref_image.write_bytes(fake_png)
        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        await generate_image_openai_async(
            client,
            semaphore,
            gate,
            job,
            "test prompt",
            output,
            reference_image=ref_image,
        )

        client.images.edit.assert_called_once()
        client.images.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_reference_image_edit_flow(self, tmp_path: Path) -> None:
        """Edit endpoint is called with reference image path and prompt; file is saved."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        mock_image = MagicMock()
        mock_image.b64_json = base64.b64encode(fake_png).decode()
        mock_image.url = None
        mock_result = MagicMock()
        mock_result.data = [mock_image]

        client = MagicMock()
        client.images.edit = AsyncMock(return_value=mock_result)
        client.images.generate = AsyncMock()

        ref_image = tmp_path / "reference.png"
        ref_image.write_bytes(b"\x89PNG ref")
        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        result = await generate_image_openai_async(
            client,
            semaphore,
            gate,
            job,
            "test prompt",
            output,
            reference_image=ref_image,
        )

        assert result is True
        assert output.exists()
        assert output.read_bytes() == fake_png
        # Edit endpoint should have been called with the reference image path
        call_kwargs = client.images.edit.call_args
        assert ref_image in call_kwargs.kwargs.get("image", call_kwargs[1].get("image", []))
        client.images.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_url_response_variant(self, tmp_path: Path) -> None:
        """API returning a URL instead of b64_json downloads the image."""
        mock_image = MagicMock()
        mock_image.b64_json = None
        mock_image.url = "https://example.com/image.png"
        mock_result = MagicMock()
        mock_result.data = [mock_image]

        client = MagicMock()
        client.images.generate = AsyncMock(return_value=mock_result)

        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        with patch("scripts.generate_sample_cards.image_generator.urllib.request.urlretrieve") as mock_retrieve:
            result = await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        assert result is True
        mock_retrieve.assert_called_once_with("https://example.com/image.png", output)

    @pytest.mark.asyncio
    async def test_empty_result_data(self, tmp_path: Path) -> None:
        """API returns result.data = [] → returns False."""
        mock_result = MagicMock()
        mock_result.data = []
        client = MagicMock()
        client.images.generate = AsyncMock(return_value=mock_result)

        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        result = await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        assert result is False
        assert not output.exists()

    @pytest.mark.asyncio
    async def test_no_b64_or_url(self, tmp_path: Path) -> None:
        """Image has b64_json=None and url=None → returns False."""
        mock_image = MagicMock()
        mock_image.b64_json = None
        mock_image.url = None
        mock_result = MagicMock()
        mock_result.data = [mock_image]
        client = MagicMock()
        client.images.generate = AsyncMock(return_value=mock_result)

        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        result = await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        assert result is False

    @pytest.mark.asyncio
    async def test_no_reference_uses_generate_endpoint(self, tmp_path: Path) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        client = self._make_openai_client(fake_png)

        output = tmp_path / "out.png"
        job = _make_job()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        await generate_image_openai_async(client, semaphore, gate, job, "test prompt", output)

        client.images.generate.assert_called_once()
        client.images.edit.assert_not_called()


class TestGenerateFullCardImagesAsync:
    @pytest.mark.asyncio
    async def test_single_page_returns_one_image(self, tmp_path: Path) -> None:
        """Spec with page_count=1 generates only a front image."""
        spec = _make_spec(back_page_type=None)
        spec.page_count = 1
        job = _make_job()
        client = MagicMock()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        front_path = tmp_path / "card_000_front.png"

        async def fake_generate(cl, sem, gt, jb, prompt, output, **kwargs):
            output.write_bytes(b"fake png")
            return True

        with patch(
            "scripts.generate_sample_cards.image_generator.generate_image_openai_async",
            side_effect=fake_generate,
        ):
            paths = await generate_full_card_images_async(client, semaphore, gate, job, spec, tmp_path, 0)

        assert len(paths) == 1
        assert paths[0] == front_path

    @pytest.mark.asyncio
    async def test_two_pages_photo_passes_front_as_reference(self, tmp_path: Path) -> None:
        """Spec with page_count=2 and photo back passes front image as reference."""
        spec = _make_spec(back_page_type="photo", back_photo_mode="single")
        job = _make_job()
        client = MagicMock()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        front_path = tmp_path / "card_000_front.png"
        calls = []

        async def fake_generate(cl, sem, gt, jb, prompt, output, **kwargs):
            calls.append({"output": output, "reference_image": kwargs.get("reference_image")})
            output.write_bytes(b"fake png")
            return True

        with patch(
            "scripts.generate_sample_cards.image_generator.generate_image_openai_async",
            side_effect=fake_generate,
        ):
            paths = await generate_full_card_images_async(client, semaphore, gate, job, spec, tmp_path, 0)

        assert len(paths) == 2
        # Front call should have no reference image
        assert calls[0]["reference_image"] is None
        # Back call should have front image as reference
        assert calls[1]["reference_image"] == front_path

    @pytest.mark.asyncio
    async def test_front_fails_returns_empty(self, tmp_path: Path) -> None:
        """If front generation fails, returns empty list (back is not attempted)."""
        spec = _make_spec(back_page_type="blurb")
        job = _make_job()
        client = MagicMock()
        semaphore = asyncio.Semaphore(1)
        gate = RateLimitGate()

        async def fake_generate(cl, sem, gt, jb, prompt, output, **kwargs):
            return False

        with patch(
            "scripts.generate_sample_cards.image_generator.generate_image_openai_async",
            side_effect=fake_generate,
        ):
            paths = await generate_full_card_images_async(client, semaphore, gate, job, spec, tmp_path, 0)

        assert paths == []
