"""Async batch AI processing for greeting card analysis.

Pure function with no GUI dependencies — can be called from the main
thread or a CLI tool by providing progress/completion callbacks.
"""

import asyncio
import logging
from collections.abc import Callable

from app.core.constants import AI_CONCURRENCY
from app.core.database import get_card_state, reprocess_candidates_from_raw, save_raw_ai
from app.core.pipeline.ai_analyzer import AIError, analyze_card_with_ai_async, classify_ai_error, parse_retry_after
from app.core.pipeline.card_processor import load_card_state_from_db
from app.core.pipeline.rate_limit import RateLimitGate
from app.models.card import CardResult

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2  # 1 initial + 1 app-level retry
_TRANSIENT_RETRY_DELAY_S = 2


async def run_ai_batch_async(
    target_cards: list[CardResult],
    on_progress: Callable[[int, int, str, int, CardResult | None], None],
    on_complete: Callable[[list[AIError], bool], None],
) -> None:
    """Async batch AI processing with concurrency limit and retry.

    Args:
        target_cards: Cards to process with AI.
        on_progress: Called after each card with (completed, total, filename, card_id, card).
            ``card`` is None when the card was skipped (no images, already done, or auth aborted).
        on_complete: Called when all cards finish with (errors, auth_aborted).
            Each error is an ``AIError`` with kind and detail.
    """
    import anthropic

    semaphore = asyncio.Semaphore(AI_CONCURRENCY)
    gate = RateLimitGate()
    completed = 0
    total = len(target_cards)
    auth_failed = asyncio.Event()
    errors: list[AIError] = []

    async def process_card(card_id: int, card: CardResult) -> None:
        nonlocal completed

        if card.error or (not card.page_images and not card.preview_image):
            completed += 1
            on_progress(completed, total, card.filename, card_id, None)
            return

        # Skip remaining cards if auth already failed
        if auth_failed.is_set():
            completed += 1
            on_progress(completed, total, card.filename, card_id, None)
            return

        for attempt in range(_MAX_ATTEMPTS):
            await gate.wait_if_paused()

            async with semaphore:
                # Re-check after acquiring semaphore
                if auth_failed.is_set():
                    completed += 1
                    on_progress(completed, total, card.filename, card_id, None)
                    return

                try:
                    # Check if we already have AI candidates
                    card_state = get_card_state(card.file_hash) if card.file_hash else None
                    has_ai_candidates = False
                    if card_state:
                        has_ai_candidates = any(c.method == "ai" for c in card_state.candidates)

                    if not has_ai_candidates:
                        # Run AI analysis
                        source = card.page_images or []
                        if not source and card.preview_image is not None:
                            source = [card.preview_image]
                        ai_images = [img for img in source if img is not None]
                        if not ai_images:
                            completed += 1
                            on_progress(completed, total, card.filename, card_id, None)
                            return
                        result = await analyze_card_with_ai_async(ai_images)

                        if card.file_hash and result.best_name:
                            save_raw_ai(card.file_hash, result.best_name, result.alternates)
                            reprocess_candidates_from_raw(card.file_hash)

                    load_card_state_from_db(card)
                    break  # success

                except anthropic.AuthenticationError as e:
                    auth_failed.set()
                    errors.append(classify_ai_error(e))
                    break  # no retry
                except anthropic.RateLimitError as e:
                    if attempt == 0:
                        delay = parse_retry_after(e)
                        gate.pause(delay)
                        logger.warning("Rate limited on %s, pausing %.0fs", card.filename, delay)
                        continue  # retry after gate pause
                    errors.append(classify_ai_error(e))
                except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                    if attempt == 0:
                        logger.warning("Transient error on %s, retrying: %s", card.filename, e)
                        await asyncio.sleep(_TRANSIENT_RETRY_DELAY_S)
                        continue  # retry once
                    errors.append(classify_ai_error(e))
                except Exception as e:
                    errors.append(classify_ai_error(e))
                    break  # non-retryable

        completed += 1
        on_progress(completed, total, card.filename, card_id, card)

    # Process all cards concurrently with semaphore limiting concurrency
    await asyncio.gather(*[process_card(card.id, card) for card in target_cards])

    aborted = auth_failed.is_set()
    on_complete(errors, aborted)
