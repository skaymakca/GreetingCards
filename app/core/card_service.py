"""Card mutation + persistence operations.

Orchestrates card mutations with database persistence. Each method combines
in-memory CardResult field updates with database calls, ensuring the two
stay in sync. Runs exclusively on the main (UI) thread — no locking needed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.card_store import CardStore
from app.core.database import clear_ai_results, select_candidate, set_manual_name, update_remove_family
from app.core.pipeline.card_processor import load_card_state_from_db
from app.models.card import CardResult, Confidence

logger = logging.getLogger(__name__)


class CardService:
    """Orchestrates card mutations with database persistence."""

    def __init__(self, store: CardStore) -> None:
        self._store = store

    @staticmethod
    def is_ai_eligible(card: CardResult) -> bool:
        """True if card can be sent for AI analysis (no error, has images)."""
        if card.error:
            return False
        return bool(card.page_images or card.preview_image)

    def reset(self) -> None:
        """Reset database and clear in-memory state."""
        from app.core.database import reset_database

        reset_database()
        self._store.clear()

    def set_name(self, card_id: int, name: str) -> CardResult | None:
        """Set or clear a manual name override on a card.

        When name is non-empty: sets manual confidence, method, family_name,
        and persists to DB. When empty: clears the override and reloads
        state from DB (reverts to best candidate name).

        Returns the updated card, or None if card_id not found.
        """
        card = self._store.get_by_id(card_id)
        if card is None:
            return None

        if name:
            if card.confidence != Confidence.MANUAL:
                card.original_confidence = card.confidence
            card.confidence = Confidence.MANUAL
            card.method = "manual"
            card.family_name = name
            card.manual_override = name
            card.selected_candidate_id = None
            if card.file_hash:
                set_manual_name(card.file_hash, name, card.remove_family)
        else:
            card.manual_override = ""
            if card.file_hash:
                set_manual_name(card.file_hash, "", card.remove_family)
            load_card_state_from_db(card)

        return card

    def select_candidate(self, card_id: int, candidate_id: int) -> CardResult | None:
        """Select a candidate by its database ID.

        Updates the card's family_name, method, confidence from the
        candidate, clears manual_override, and persists to DB.

        Returns the updated card, or None if card_id not found.
        """
        card = self._store.get_by_id(card_id)
        if card is None or not card.file_hash:
            return None

        for cand in card.candidates:
            if cand.id == candidate_id:
                card.family_name = cand.family_name
                card.manual_override = ""
                card.selected_candidate_id = candidate_id
                card.method = cand.method

                if card.confidence == Confidence.MANUAL and card.original_confidence:
                    card.confidence = card.original_confidence
                else:
                    try:
                        card.confidence = Confidence(cand.confidence)
                    except ValueError:
                        logger.debug(
                            "Unknown confidence %r for candidate %d, defaulting to MEDIUM",
                            cand.confidence,
                            cand.id,
                        )
                        card.confidence = Confidence.MEDIUM
                break

        select_candidate(card.file_hash, candidate_id, card.remove_family)
        return card

    def select_candidate_by_rank(self, card_id: int, rank: int) -> CardResult | str | None:
        """Select a candidate by 1-based rank order.

        Returns:
            Updated CardResult on success, error string on validation failure,
            None if card not found.
        """
        card = self._store.get_by_id(card_id)
        if card is None:
            return None
        if rank < 1 or rank > len(card.candidates):
            return f"Invalid rank {rank}: card has {len(card.candidates)} candidates"

        cand = card.candidates[rank - 1]
        return self.select_candidate(card_id, cand.id)

    def set_remove_family(self, card_id: int, value: bool) -> CardResult | None:
        """Toggle the Remove Family flag on a card.

        Updates the card's remove_family field and persists to DB.

        Returns the updated card, or None if card_id not found.
        """
        card = self._store.get_by_id(card_id)
        if card is None:
            return None

        card.remove_family = value
        if card.file_hash:
            update_remove_family(card.file_hash, value)

        return card

    def clear_cards(self) -> None:
        """Clear all in-memory card state (no database reset)."""
        self._store.clear()

    def unlink_path(self, path: Path) -> None:
        """Remove a path from all tracking dicts and its associated card."""
        self._store.unlink_path(path)

    def clear_ai_results(self, cards: list[CardResult]) -> int:
        """Clear AI results for the given cards.

        Deletes AI candidates and raw AI data in DB, then reloads card
        state to pick up best remaining OCR candidate.

        Returns the number of cards whose selection changed in the DB.
        """
        file_hashes = [card.file_hash for card in cards if card.file_hash]
        changed = clear_ai_results(file_hashes)

        for card in cards:
            if card.file_hash:
                load_card_state_from_db(card)

        return changed
