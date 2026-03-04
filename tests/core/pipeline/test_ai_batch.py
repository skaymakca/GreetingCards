"""Tests for app.core.pipeline.ai_batch.run_ai_batch_async."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.models.card import CardResult


def _make_card(card_id: int = 0, *, with_image: bool = True, file_hash: str = "h1") -> CardResult:
    """Create a minimal CardResult for testing."""
    path = Path(f"/tmp/card_{card_id}.pdf")
    card = CardResult(id=card_id, file_paths=[path], primary_path=path)
    card.file_hash = file_hash
    if with_image:
        card.preview_image = Image.new("RGB", (10, 10))
    return card


class TestRunAiBatchAsync:
    """Tests for run_ai_batch_async()."""

    @pytest.mark.asyncio
    async def test_empty_card_list_calls_on_complete(self):
        """Empty card list calls on_complete with no errors."""
        from app.core.pipeline.ai_batch import run_ai_batch_async

        on_progress = MagicMock()
        on_complete = MagicMock()

        await run_ai_batch_async([], on_progress, on_complete)

        on_progress.assert_not_called()
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_card_without_images_is_skipped(self):
        """Card with no page_images and no preview_image is skipped (on_progress called with card=None)."""
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card(with_image=False)
        on_progress = MagicMock()
        on_complete = MagicMock()

        await run_ai_batch_async([card], on_progress, on_complete)

        on_progress.assert_called_once_with(1, 1, card.filename, card.id, None)
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_error_card_is_skipped(self):
        """Card with .error set is skipped without calling AI."""
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        card.error = "Processing failed"
        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async") as mock_ai:
            await run_ai_batch_async([card], on_progress, on_complete)

        mock_ai.assert_not_called()
        on_progress.assert_called_once_with(1, 1, card.filename, card.id, None)
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_successful_analysis_updates_card(self):
        """Successful AI analysis calls load_card_state_from_db and on_progress with card."""
        from app.core.pipeline.ai_analyzer import AIResult
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        on_progress = MagicMock()
        on_complete = MagicMock()

        mock_result = AIResult(best_name="Smith", alternates=["Smyth"])

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", AsyncMock(return_value=mock_result)),
            patch("app.core.pipeline.ai_batch.save_raw_ai") as mock_save,
            patch("app.core.pipeline.ai_batch.reprocess_candidates_from_raw") as mock_reprocess,
            patch("app.core.pipeline.ai_batch.load_card_state_from_db") as mock_load,
        ):
            await run_ai_batch_async([card], on_progress, on_complete)

        mock_save.assert_called_once_with("h1", "Smith", ["Smyth"])
        mock_reprocess.assert_called_once_with("h1")
        mock_load.assert_called_once_with(card)
        on_progress.assert_called_once_with(1, 1, card.filename, card.id, card)
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_skips_card_with_existing_ai_candidates(self):
        """Card that already has AI candidates skips AI analysis but still loads DB state."""
        from app.core.pipeline.ai_batch import run_ai_batch_async
        from app.models.card import CandidateInfo, CardState

        card = _make_card()
        existing_state = CardState(
            display_name="Smith",
            method="ai",
            confidence="high",
            candidates=[CandidateInfo(id=1, family_name="Smith", method="ai", confidence="high")],
            remove_family=False,
            selected_candidate_id=1,
        )

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=existing_state),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async") as mock_ai,
            patch("app.core.pipeline.ai_batch.load_card_state_from_db") as mock_load,
        ):
            await run_ai_batch_async([card], MagicMock(), MagicMock())

        mock_ai.assert_not_called()
        mock_load.assert_called_once_with(card)

    @pytest.mark.asyncio
    async def test_auth_error_aborts_remaining_cards(self):
        """AuthenticationError on first card aborts the second (auth_aborted=True)."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        card1 = _make_card(0, file_hash="h1")
        card2 = _make_card(1, file_hash="h2")
        on_progress = MagicMock()
        on_complete = MagicMock()

        auth_err = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body=None,
        )

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", AsyncMock(side_effect=auth_err)),
        ):
            await run_ai_batch_async([card1, card2], on_progress, on_complete)

        # on_complete called with auth_aborted=True and one error recorded
        args = on_complete.call_args
        errors, auth_aborted = args[0]
        assert auth_aborted is True
        assert len(errors) == 1
        assert errors[0].is_auth

    @pytest.mark.asyncio
    async def test_rate_limit_retries_and_succeeds(self):
        """RateLimitError on first attempt triggers gate pause and retries successfully."""
        import anthropic

        from app.core.pipeline.ai_analyzer import AIResult
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        rate_err = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={"retry-after-ms": "50"}),
            body=None,
        )
        mock_analyze = AsyncMock(side_effect=[rate_err, AIResult(best_name="Smith")])

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("app.core.pipeline.ai_batch.parse_retry_after", return_value=0.01),
            patch("app.core.pipeline.ai_batch.save_raw_ai"),
            patch("app.core.pipeline.ai_batch.reprocess_candidates_from_raw"),
            patch("app.core.pipeline.ai_batch.load_card_state_from_db"),
        ):
            await run_ai_batch_async([card], MagicMock(), MagicMock())

        assert mock_analyze.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_retries_once_and_succeeds(self):
        """APITimeoutError retries once with a short delay."""
        import anthropic

        from app.core.pipeline.ai_analyzer import AIResult
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        timeout_err = anthropic.APITimeoutError(request=MagicMock())
        mock_analyze = AsyncMock(side_effect=[timeout_err, AIResult(best_name="Jones")])

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("app.core.pipeline.ai_batch.save_raw_ai"),
            patch("app.core.pipeline.ai_batch.reprocess_candidates_from_raw"),
            patch("app.core.pipeline.ai_batch.load_card_state_from_db"),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await run_ai_batch_async([card], MagicMock(), MagicMock())

        assert mock_analyze.call_count == 2

    @pytest.mark.asyncio
    async def test_generic_error_recorded_no_retry(self):
        """Generic exception is recorded in errors, no retry attempted."""
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        mock_analyze = AsyncMock(side_effect=ValueError("unexpected"))
        on_complete = MagicMock()

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
        ):
            await run_ai_batch_async([card], MagicMock(), on_complete)

        assert mock_analyze.call_count == 1
        errors, _ = on_complete.call_args[0]
        assert len(errors) == 1
        assert errors[0].detail == "unexpected"

    @pytest.mark.asyncio
    async def test_progress_reported_for_multiple_cards(self):
        """on_progress is called once per card with incrementing completed count."""
        from app.core.pipeline.ai_analyzer import AIResult
        from app.core.pipeline.ai_batch import run_ai_batch_async

        cards = [_make_card(i, file_hash=f"h{i}") for i in range(3)]
        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch(
                "app.core.pipeline.ai_batch.analyze_card_with_ai_async", AsyncMock(return_value=AIResult(best_name="X"))
            ),
            patch("app.core.pipeline.ai_batch.save_raw_ai"),
            patch("app.core.pipeline.ai_batch.reprocess_candidates_from_raw"),
            patch("app.core.pipeline.ai_batch.load_card_state_from_db"),
        ):
            await run_ai_batch_async(cards, on_progress, on_complete)

        assert on_progress.call_count == 3
        completed_values = sorted(call.args[0] for call in on_progress.call_args_list)
        assert completed_values == [1, 2, 3]
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted_after_retry_records_error(self):
        """RateLimitError on both attempts records an error (no infinite retry)."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        rate_err = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={"retry-after-ms": "50"}),
            body=None,
        )
        mock_analyze = AsyncMock(side_effect=[rate_err, rate_err])
        on_complete = MagicMock()

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("app.core.pipeline.ai_batch.parse_retry_after", return_value=0.01),
        ):
            await run_ai_batch_async([card], MagicMock(), on_complete)

        assert mock_analyze.call_count == 2
        errors, _ = on_complete.call_args[0]
        assert len(errors) == 1
        assert "Rate limit" in errors[0].detail

    @pytest.mark.asyncio
    async def test_connection_error_exhausted_after_retry_records_error(self):
        """APIConnectionError on both attempts records an error."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        conn_err = anthropic.APIConnectionError(request=MagicMock())
        mock_analyze = AsyncMock(side_effect=[conn_err, conn_err])
        on_complete = MagicMock()

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await run_ai_batch_async([card], MagicMock(), on_complete)

        assert mock_analyze.call_count == 2
        errors, _ = on_complete.call_args[0]
        assert len(errors) == 1
        assert "connection" in errors[0].detail.lower()

    @pytest.mark.asyncio
    async def test_auth_failed_skips_card_after_semaphore(self):
        """Card that acquires semaphore after auth_failed is set should be skipped."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        cards = [_make_card(i, file_hash=f"h{i}") for i in range(3)]
        on_progress = MagicMock()
        on_complete = MagicMock()

        auth_err = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body=None,
        )
        # First card fails with auth error, remaining should be skipped
        mock_analyze = AsyncMock(side_effect=auth_err)

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("app.core.pipeline.ai_batch.AI_CONCURRENCY", 1),  # Force sequential processing
        ):
            await run_ai_batch_async(cards, on_progress, on_complete)

        # All 3 cards should have progress reported
        assert on_progress.call_count == 3
        # Only 1 error recorded (auth on first card), remaining skipped
        errors, auth_aborted = on_complete.call_args[0]
        assert auth_aborted is True
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_card_with_preview_image_only_uses_it(self):
        """Card with only preview_image (no page_images) should use preview_image for AI."""
        from app.core.pipeline.ai_analyzer import AIResult
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        card.page_images = []  # No page images
        # preview_image is already set by _make_card
        on_complete = MagicMock()

        mock_result = AIResult(best_name="TestName")

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch(
                "app.core.pipeline.ai_batch.analyze_card_with_ai_async", AsyncMock(return_value=mock_result)
            ) as mock_ai,
            patch("app.core.pipeline.ai_batch.save_raw_ai"),
            patch("app.core.pipeline.ai_batch.reprocess_candidates_from_raw"),
            patch("app.core.pipeline.ai_batch.load_card_state_from_db"),
        ):
            await run_ai_batch_async([card], MagicMock(), on_complete)

        # AI should have been called with the preview image
        mock_ai.assert_called_once()
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_rate_limit_error_on_second_attempt_records_error(self):
        """Rate limit error on second attempt records error (lines 64-66, 104)."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        on_progress = MagicMock()
        on_complete = MagicMock()

        rate_err = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429, headers={}),
            body=None,
        )
        # Fail on both attempts
        mock_analyze = AsyncMock(side_effect=rate_err)

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("app.core.pipeline.ai_batch.parse_retry_after", return_value=0.01),
        ):
            await run_ai_batch_async([card], on_progress, on_complete)

        errors, aborted = on_complete.call_args[0]
        assert len(errors) == 1
        assert not aborted

    @pytest.mark.asyncio
    async def test_transient_error_on_second_attempt_records_error(self):
        """Timeout/connection error on second attempt records error (lines 82-84)."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card()
        on_progress = MagicMock()
        on_complete = MagicMock()

        timeout_err = anthropic.APITimeoutError(request=MagicMock())
        mock_analyze = AsyncMock(side_effect=timeout_err)

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
        ):
            await run_ai_batch_async([card], on_progress, on_complete)

        # Should have called analyze twice (initial + 1 retry)
        assert mock_analyze.call_count == 2
        errors, aborted = on_complete.call_args[0]
        assert len(errors) == 1
        assert not aborted

    @pytest.mark.asyncio
    async def test_auth_recheck_after_semaphore_acquire(self):
        """After acquiring semaphore, re-checks auth_failed flag (lines 64-66)."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        cards = [_make_card(i, file_hash=f"h{i}") for i in range(2)]
        on_progress = MagicMock()
        on_complete = MagicMock()

        auth_err = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body=None,
        )
        mock_analyze = AsyncMock(side_effect=auth_err)

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", mock_analyze),
            patch("app.core.pipeline.ai_batch.AI_CONCURRENCY", 1),
        ):
            await run_ai_batch_async(cards, on_progress, on_complete)

        # Both cards should report progress
        assert on_progress.call_count == 2
        _errors, aborted = on_complete.call_args[0]
        assert aborted is True

    @pytest.mark.asyncio
    async def test_auth_fail_after_semaphore_no_images_processed(self):
        """Auth failure after semaphore acquire on the very first card with no prior success.

        Tests the boundary where auth_failed is set inside the semaphore block
        before any images have been successfully processed, and verifies the
        error is correctly propagated through on_complete.
        """
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card(0, file_hash="h0")
        on_progress = MagicMock()
        on_complete = MagicMock()

        auth_err = anthropic.AuthenticationError(
            message="invalid api key",
            response=MagicMock(status_code=401),
            body=None,
        )

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", AsyncMock(side_effect=auth_err)),
            patch("app.core.pipeline.ai_batch.save_raw_ai") as mock_save,
            patch("app.core.pipeline.ai_batch.load_card_state_from_db") as mock_load,
        ):
            await run_ai_batch_async([card], on_progress, on_complete)

        # AI save/load should NOT have been called (auth failed before success)
        mock_save.assert_not_called()
        mock_load.assert_not_called()
        # Progress reported for the card
        on_progress.assert_called_once_with(1, 1, card.filename, card.id, card)
        # on_complete reports auth abort with exactly one error
        errors, auth_aborted = on_complete.call_args[0]
        assert auth_aborted is True
        assert len(errors) == 1
        assert errors[0].is_auth
        assert errors[0].detail == "Invalid API key"

    @pytest.mark.asyncio
    async def test_no_images_after_filtering_skips_card(self):
        """Card with empty images after None-filtering skips analysis (lines 82-84)."""
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card(with_image=False)
        card.page_images = []
        card.preview_image = None
        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch("app.core.pipeline.ai_batch.get_card_state", return_value=None):
            await run_ai_batch_async([card], on_progress, on_complete)

        on_progress.assert_called_once()
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_no_images_after_none_filtering(self):
        """Card with page_images=[None, None] passes initial check but filtered list is empty."""
        from app.core.pipeline.ai_batch import run_ai_batch_async

        card = _make_card(with_image=False)
        card.page_images = [None, None]  # truthy list, but all None
        card.preview_image = None
        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async") as mock_ai,
        ):
            await run_ai_batch_async([card], on_progress, on_complete)

        mock_ai.assert_not_called()
        on_progress.assert_called_once_with(1, 1, card.filename, card.id, None)
        on_complete.assert_called_once_with([], False)

    @pytest.mark.asyncio
    async def test_auth_recheck_inside_semaphore(self):
        """Card 2 acquires semaphore after card 1 sets auth_failed inside semaphore."""
        import anthropic

        from app.core.pipeline.ai_batch import run_ai_batch_async

        cards = [_make_card(i, file_hash=f"h{i}") for i in range(2)]
        on_progress = MagicMock()
        on_complete = MagicMock()

        auth_err = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body=None,
        )
        call_count = 0

        async def delayed_auth_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Yield control so card 2 can start and block on semaphore
            await asyncio.sleep(0)
            raise auth_err

        with (
            patch("app.core.pipeline.ai_batch.get_card_state", return_value=None),
            patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", side_effect=delayed_auth_error),
            patch("app.core.pipeline.ai_batch.AI_CONCURRENCY", 1),
        ):
            await run_ai_batch_async(cards, on_progress, on_complete)

        # Card 1 fails with auth error; card 2 should be skipped at re-check
        assert on_progress.call_count == 2
        errors, aborted = on_complete.call_args[0]
        assert aborted is True
        # Only 1 auth error from card 1
        assert len(errors) == 1


class TestRunAiBatchWithDB:
    """DB-backed tests for run_ai_batch_async using real in-memory SQLite."""

    @pytest.fixture(autouse=True)
    def _use_db(self, in_memory_db):
        return in_memory_db

    @pytest.mark.asyncio
    async def test_ai_batch_saves_results_and_creates_candidates(self):
        """Successful AI batch saves raw AI result and creates AI candidates in DB."""
        from app.core.database import create_or_update_card, get_candidates, get_card_state, get_raw_ai, save_raw_ocr
        from app.core.pipeline.ai_analyzer import AIResult
        from app.core.pipeline.ai_batch import run_ai_batch_async

        create_or_update_card("h1")
        save_raw_ocr("h1", "The OcrName Family")

        card = _make_card(file_hash="h1")
        mock_result = AIResult(best_name="AiName", alternates=["AltName"])

        with patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async", AsyncMock(return_value=mock_result)):
            await run_ai_batch_async([card], MagicMock(), MagicMock())

        raw = get_raw_ai("h1")
        assert raw is not None
        assert raw[0] == "AiName"
        assert "AltName" in raw[1]

        candidates = get_candidates("h1")
        assert any(c.method == "ai" for c in candidates)
        assert any(c.method == "ocr" for c in candidates)

        state = get_card_state("h1")
        assert state.method == "ai"

    @pytest.mark.asyncio
    async def test_ai_batch_skips_card_with_existing_ai(self):
        """Card that already has AI candidates skips AI analysis and leaves raw data unchanged."""
        from app.core.database import (
            create_or_update_card,
            get_raw_ai,
            reprocess_candidates_from_raw,
            save_raw_ai,
            save_raw_ocr,
        )
        from app.core.pipeline.ai_batch import run_ai_batch_async

        create_or_update_card("h1")
        save_raw_ocr("h1", "The OcrName Family")
        save_raw_ai("h1", "ExistingAi", [])
        reprocess_candidates_from_raw("h1")

        card = _make_card(file_hash="h1")

        with patch("app.core.pipeline.ai_batch.analyze_card_with_ai_async") as mock_ai:
            await run_ai_batch_async([card], MagicMock(), MagicMock())

        mock_ai.assert_not_called()
        raw = get_raw_ai("h1")
        assert raw is not None
        assert raw[0] == "ExistingAi"
