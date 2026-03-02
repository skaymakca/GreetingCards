"""AI batch analysis orchestration service.

Manages the async AI batch workflow.  Has zero wxPython dependency —
the caller wraps callbacks with ``wx.CallAfter``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.core.pipeline.ai_batch import run_ai_batch_async
from app.models.card import CardResult

logger = logging.getLogger(__name__)


class AIService:
    """AI batch analysis orchestration. Zero wxPython dependency."""

    @staticmethod
    def run_batch(
        cards: list[CardResult],
        on_progress: Callable[[int, int, str, int, CardResult | None], None],
        on_complete: Callable[[list[tuple[str, str]], bool], None],
    ) -> None:
        """Run AI batch synchronously in calling thread (caller handles threading).

        Mirrors ``ProcessingService.process_files()`` pattern.

        Args:
            cards: Cards to analyze with AI.
            on_progress: Called after each card with
                (completed, total, filename, card_id, card_or_none).
            on_complete: Called when batch finishes with
                (errors_list, auth_aborted).
        """
        asyncio.run(run_ai_batch_async(cards, on_progress=on_progress, on_complete=on_complete))
