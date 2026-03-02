"""Tests for AIService — AI batch orchestration."""

from __future__ import annotations

from unittest.mock import patch

from app.core.ai_service import AIService
from app.models.card import CardResult, Confidence


def _make_card(card_id: int = 0) -> CardResult:
    """Create a minimal CardResult for testing."""
    from pathlib import Path

    return CardResult(
        id=card_id,
        file_paths=[Path("/tmp/card.pdf")],
        primary_path=Path("/tmp/card.pdf"),
        family_name="Smith",
        confidence=Confidence.HIGH,
        method="ocr",
        file_hash="hash1",
    )


class TestRunBatch:
    """Tests for AIService.run_batch()."""

    def test_delegates_to_run_ai_batch_async(self) -> None:
        """run_batch should call run_ai_batch_async via asyncio.run."""
        cards = [_make_card()]
        progress_calls: list[tuple] = []
        complete_calls: list[tuple] = []

        def on_progress(c: int, t: int, f: str, i: int, card: CardResult | None) -> None:
            progress_calls.append((c, t, f, i, card))

        def on_complete(errors: list[tuple[str, str]], aborted: bool) -> None:
            complete_calls.append((errors, aborted))

        with patch("app.core.ai_service.run_ai_batch_async") as mock_batch:
            # Make the coroutine return immediately
            async def _noop(cards, on_progress, on_complete):
                # Simulate calling on_complete
                on_complete([], False)

            mock_batch.side_effect = _noop

            AIService.run_batch(cards, on_progress=on_progress, on_complete=on_complete)

        mock_batch.assert_called_once()
        assert len(complete_calls) == 1
        assert complete_calls[0] == ([], False)
