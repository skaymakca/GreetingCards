"""Tests for CardService — card mutation + persistence operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.card_store import CardStore
from app.core.services.card_service import CardService
from app.models.card import CandidateInfo, CardResult, Confidence


def _make_card(
    card_id: int = 1,
    family_name: str = "Smith",
    confidence: Confidence = Confidence.HIGH,
    method: str = "ocr",
    file_hash: str = "abc123",
    candidates: list[CandidateInfo] | None = None,
    manual_override: str = "",
    original_confidence: Confidence | None = None,
    remove_family: bool = False,
    selected_candidate_id: int | None = None,
) -> CardResult:
    """Create a CardResult for testing with sensible defaults."""
    if candidates is None:
        candidates = [
            CandidateInfo(id=10, family_name="Smith", method="ocr", confidence="high"),
            CandidateInfo(id=20, family_name="Jones", method="ai", confidence="medium"),
        ]
    card = CardResult(
        id=card_id,
        file_paths=[Path("/tmp/card.pdf")],
        primary_path=Path("/tmp/card.pdf"),
        family_name=family_name,
        confidence=confidence,
        method=method,
        file_hash=file_hash,
        candidates=candidates,
        manual_override=manual_override,
        original_confidence=original_confidence,
        remove_family=remove_family,
        selected_candidate_id=selected_candidate_id,
    )
    return card


def _make_store_and_service(*cards: CardResult) -> tuple[CardStore, CardService]:
    """Create a CardStore populated with the given cards and a CardService wrapping it."""
    store = CardStore()
    for card in cards:
        if card.file_hash:
            store._cards_by_hash[card.file_hash] = card
        store._id_to_card[card.id] = card
    return store, CardService(store)


# ── set_name ──


class TestSetName:
    """Tests for CardService.set_name()."""

    @patch("app.core.services.card_service.set_manual_name")
    def test_set_name_updates_card_fields(self, mock_set_manual_name: object) -> None:
        """Setting a name updates confidence, method, family_name, and manual_override."""
        card = _make_card(confidence=Confidence.HIGH)
        _, service = _make_store_and_service(card)

        result = service.set_name(card.id, "Johnson")

        assert result is card
        assert card.confidence == Confidence.MANUAL
        assert card.method == "manual"
        assert card.family_name == "Johnson"
        assert card.manual_override == "Johnson"
        assert card.selected_candidate_id is None

    @patch("app.core.services.card_service.set_manual_name")
    def test_set_name_calls_db(self, mock_set_manual_name: object) -> None:
        """Setting a name persists to DB via set_manual_name."""
        card = _make_card(file_hash="hash1", remove_family=True)
        _, service = _make_store_and_service(card)

        service.set_name(card.id, "Johnson")

        mock_set_manual_name.assert_called_once_with("hash1", "Johnson", True)  # type: ignore[union-attr]

    @patch("app.core.services.card_service.set_manual_name")
    def test_set_name_preserves_original_confidence(self, mock_set_manual_name: object) -> None:
        """Setting a name saves the current confidence as original_confidence."""
        card = _make_card(confidence=Confidence.HIGH)
        _, service = _make_store_and_service(card)

        service.set_name(card.id, "Johnson")

        assert card.original_confidence == Confidence.HIGH

    @patch("app.core.services.card_service.set_manual_name")
    def test_set_name_does_not_overwrite_ui_original_when_already_manual(self, mock_set_manual_name: object) -> None:
        """If confidence is already MANUAL, original_confidence is not overwritten."""
        card = _make_card(
            confidence=Confidence.MANUAL,
            original_confidence=Confidence.LOW,
        )
        _, service = _make_store_and_service(card)

        service.set_name(card.id, "NewName")

        # Should NOT overwrite — stays as LOW
        assert card.original_confidence == Confidence.LOW

    @patch("app.core.services.card_service.load_card_state_from_db")
    @patch("app.core.services.card_service.set_manual_name")
    def test_clear_name_reverts_to_db_state(self, mock_set_manual_name: object, mock_load: object) -> None:
        """Clearing name (empty string) clears manual_override and reloads from DB."""
        card = _make_card(
            confidence=Confidence.MANUAL,
            manual_override="OldManual",
            file_hash="hash1",
        )
        _, service = _make_store_and_service(card)

        result = service.set_name(card.id, "")

        assert result is card
        assert card.manual_override == ""
        mock_set_manual_name.assert_called_once_with("hash1", "", False)  # type: ignore[union-attr]
        mock_load.assert_called_once_with(card)  # type: ignore[union-attr]

    @patch("app.core.services.card_service.set_manual_name")
    def test_set_name_unknown_card_returns_none(self, mock_set_manual_name: object) -> None:
        """Unknown card_id returns None and makes no DB call."""
        _, service = _make_store_and_service()

        result = service.set_name(999, "Johnson")

        assert result is None
        mock_set_manual_name.assert_not_called()  # type: ignore[union-attr]

    @patch("app.core.services.card_service.set_manual_name")
    def test_set_name_no_file_hash_skips_db(self, mock_set_manual_name: object) -> None:
        """Card with no file_hash does not call set_manual_name."""
        card = _make_card(file_hash="")
        _, service = _make_store_and_service(card)

        result = service.set_name(card.id, "Johnson")

        assert result is card
        assert card.family_name == "Johnson"
        mock_set_manual_name.assert_not_called()  # type: ignore[union-attr]


# ── select_candidate ──


class TestSelectCandidate:
    """Tests for CardService.select_candidate()."""

    @patch("app.core.services.card_service.select_candidate")
    def test_select_candidate_updates_card_fields(self, mock_select_candidate: object) -> None:
        """Selecting a candidate updates card fields from the candidate."""
        card = _make_card(confidence=Confidence.HIGH)
        _, service = _make_store_and_service(card)

        result = service.select_candidate(card.id, 20)

        assert result is card
        assert card.family_name == "Jones"
        assert card.manual_override == ""
        assert card.selected_candidate_id == 20
        assert card.method == "ai"
        assert card.confidence == Confidence.MEDIUM

    @patch("app.core.services.card_service.select_candidate")
    def test_select_candidate_calls_db(self, mock_select_candidate: object) -> None:
        """Selecting a candidate persists to DB."""
        card = _make_card(file_hash="hash1", remove_family=True)
        _, service = _make_store_and_service(card)

        service.select_candidate(card.id, 10)

        mock_select_candidate.assert_called_once_with("hash1", 10, True)  # type: ignore[union-attr]

    @patch("app.core.services.card_service.select_candidate")
    def test_select_candidate_always_uses_candidate_confidence(self, mock_select_candidate: object) -> None:
        """Selecting a candidate always uses the candidate's own confidence, even from MANUAL."""
        card = _make_card(
            confidence=Confidence.MANUAL,
            original_confidence=Confidence.HIGH,
        )
        _, service = _make_store_and_service(card)

        service.select_candidate(card.id, 20)

        # Candidate 20 has confidence "medium" — always wins over original_confidence
        assert card.confidence == Confidence.MEDIUM
        assert card.original_confidence is None

    @patch("app.core.services.card_service.select_candidate")
    def test_select_candidate_clears_original_confidence(self, mock_select_candidate: object) -> None:
        """Selecting a candidate clears stale original_confidence."""
        card = _make_card(
            confidence=Confidence.MANUAL,
            original_confidence=Confidence.LOW,
        )
        _, service = _make_store_and_service(card)

        service.select_candidate(card.id, 10)

        assert card.original_confidence is None

    @patch("app.core.services.card_service.select_candidate")
    def test_nonmatching_candidate_id_logs_warning(self, mock_select_candidate: object) -> None:
        """Non-matching candidate ID logs warning, skips DB call, returns card unchanged."""
        card = _make_card(confidence=Confidence.HIGH, family_name="Smith")
        _, service = _make_store_and_service(card)

        with patch("app.core.services.card_service.logger") as mock_logger:
            result = service.select_candidate(card.id, 9999)

        assert result is card
        assert card.family_name == "Smith"
        assert card.confidence == Confidence.HIGH
        mock_select_candidate.assert_not_called()  # type: ignore[union-attr]
        mock_logger.warning.assert_called_once()

    @patch("app.core.services.card_service.select_candidate")
    def test_select_candidate_unknown_card_returns_none(self, mock_select_candidate: object) -> None:
        """Unknown card_id returns None."""
        _, service = _make_store_and_service()

        result = service.select_candidate(999, 10)

        assert result is None
        mock_select_candidate.assert_not_called()  # type: ignore[union-attr]

    @patch("app.core.services.card_service.select_candidate")
    def test_select_candidate_no_file_hash_returns_none(self, mock_select_candidate: object) -> None:
        """Card with no file_hash returns None."""
        card = _make_card(file_hash="")
        _, service = _make_store_and_service(card)

        result = service.select_candidate(card.id, 10)

        assert result is None
        mock_select_candidate.assert_not_called()  # type: ignore[union-attr]


# ── select_candidate_by_rank ──


class TestSelectCandidateByRank:
    """Tests for CardService.select_candidate_by_rank()."""

    @patch("app.core.services.card_service.select_candidate")
    def test_valid_rank_delegates_to_select_candidate(self, mock_select_candidate: object) -> None:
        """Valid rank delegates to select_candidate with the right candidate ID."""
        card = _make_card()
        _, service = _make_store_and_service(card)

        result = service.select_candidate_by_rank(card.id, 2)

        assert result is card
        # Rank 2 → candidates[1] → id=20
        mock_select_candidate.assert_called_once()  # type: ignore[union-attr]

    @patch("app.core.services.card_service.select_candidate")
    def test_rank_1_selects_first_candidate(self, mock_select_candidate: object) -> None:
        """Rank 1 selects the first candidate."""
        card = _make_card()
        _, service = _make_store_and_service(card)

        service.select_candidate_by_rank(card.id, 1)

        # Rank 1 → candidates[0] → id=10
        assert card.selected_candidate_id == 10

    @patch("app.core.services.card_service.select_candidate")
    def test_rank_zero_raises_value_error(self, mock_select_candidate: object) -> None:
        """Rank 0 is invalid and raises ValueError."""
        card = _make_card()
        _, service = _make_store_and_service(card)

        with pytest.raises(ValueError, match="Invalid rank 0"):
            service.select_candidate_by_rank(card.id, 0)

        mock_select_candidate.assert_not_called()  # type: ignore[union-attr]

    @patch("app.core.services.card_service.select_candidate")
    def test_rank_exceeds_candidates_raises_value_error(self, mock_select_candidate: object) -> None:
        """Rank greater than number of candidates raises ValueError."""
        card = _make_card()  # 2 candidates
        _, service = _make_store_and_service(card)

        with pytest.raises(ValueError, match=r"Invalid rank 3.*2 candidates"):
            service.select_candidate_by_rank(card.id, 3)

        mock_select_candidate.assert_not_called()  # type: ignore[union-attr]

    @patch("app.core.services.card_service.select_candidate")
    def test_unknown_card_returns_none(self, mock_select_candidate: object) -> None:
        """Unknown card_id returns None."""
        _, service = _make_store_and_service()

        result = service.select_candidate_by_rank(999, 1)

        assert result is None
        mock_select_candidate.assert_not_called()  # type: ignore[union-attr]


# ── set_remove_family ──


class TestSetRemoveFamily:
    """Tests for CardService.set_remove_family()."""

    @patch("app.core.services.card_service.update_remove_family")
    def test_set_remove_family_true(self, mock_update: object) -> None:
        """Setting remove_family to True updates card and calls DB."""
        card = _make_card(remove_family=False, file_hash="hash1")
        _, service = _make_store_and_service(card)

        result = service.set_remove_family(card.id, True)

        assert result is card
        assert card.remove_family is True
        mock_update.assert_called_once_with("hash1", True)  # type: ignore[union-attr]

    @patch("app.core.services.card_service.update_remove_family")
    def test_set_remove_family_false(self, mock_update: object) -> None:
        """Setting remove_family to False updates card and calls DB."""
        card = _make_card(remove_family=True, file_hash="hash1")
        _, service = _make_store_and_service(card)

        result = service.set_remove_family(card.id, False)

        assert result is card
        assert card.remove_family is False
        mock_update.assert_called_once_with("hash1", False)  # type: ignore[union-attr]

    @patch("app.core.services.card_service.update_remove_family")
    def test_set_remove_family_unknown_card_returns_none(self, mock_update: object) -> None:
        """Unknown card_id returns None."""
        _, service = _make_store_and_service()

        result = service.set_remove_family(999, True)

        assert result is None
        mock_update.assert_not_called()  # type: ignore[union-attr]

    @patch("app.core.services.card_service.update_remove_family")
    def test_set_remove_family_no_file_hash_skips_db(self, mock_update: object) -> None:
        """Card with no file_hash does not call update_remove_family."""
        card = _make_card(file_hash="")
        _, service = _make_store_and_service(card)

        result = service.set_remove_family(card.id, True)

        assert result is card
        assert card.remove_family is True
        mock_update.assert_not_called()  # type: ignore[union-attr]


# ── clear_ai_results ──


class TestClearAiResults:
    """Tests for CardService.clear_ai_results()."""

    @patch("app.core.services.card_service.load_card_state_from_db")
    @patch("app.core.services.card_service.clear_ai_results")
    def test_clear_ai_results_calls_db_with_hashes(self, mock_clear: object, mock_load: object) -> None:
        """Passes file hashes to DB clear function and reloads each card."""
        card1 = _make_card(card_id=1, file_hash="hash1")
        card2 = _make_card(card_id=2, file_hash="hash2")
        _, service = _make_store_and_service(card1, card2)
        mock_clear.return_value = 2  # type: ignore[union-attr]

        result = service.clear_ai_results([card1, card2])

        assert result == 2
        mock_clear.assert_called_once_with(["hash1", "hash2"])  # type: ignore[union-attr]
        assert mock_load.call_count == 2  # type: ignore[union-attr]

    @patch("app.core.services.card_service.load_card_state_from_db")
    @patch("app.core.services.card_service.clear_ai_results")
    def test_clear_ai_results_skips_cards_without_hash(self, mock_clear: object, mock_load: object) -> None:
        """Cards without file_hash are excluded from hash list but still reloaded if they have a hash."""
        card_with_hash = _make_card(card_id=1, file_hash="hash1")
        card_no_hash = _make_card(card_id=2, file_hash="")
        _, service = _make_store_and_service(card_with_hash, card_no_hash)
        mock_clear.return_value = 1  # type: ignore[union-attr]

        result = service.clear_ai_results([card_with_hash, card_no_hash])

        assert result == 1
        # Only hash1 in the list
        mock_clear.assert_called_once_with(["hash1"])  # type: ignore[union-attr]
        # Only card_with_hash gets reloaded (card_no_hash has no file_hash)
        mock_load.assert_called_once_with(card_with_hash)  # type: ignore[union-attr]

    @patch("app.core.services.card_service.load_card_state_from_db")
    @patch("app.core.services.card_service.clear_ai_results")
    def test_clear_ai_results_empty_list(self, mock_clear: object, mock_load: object) -> None:
        """Empty card list returns 0 and still calls DB with empty list."""
        _, service = _make_store_and_service()
        mock_clear.return_value = 0  # type: ignore[union-attr]

        result = service.clear_ai_results([])

        assert result == 0
        mock_clear.assert_called_once_with([])  # type: ignore[union-attr]
        mock_load.assert_not_called()  # type: ignore[union-attr]


# ── reset ──


class TestIsAiEligible:
    """Tests for CardService.is_ai_eligible()."""

    def test_card_with_error_is_not_eligible(self) -> None:
        card = _make_card()
        card.error = "corrupt PDF"
        assert CardService.is_ai_eligible(card) is False

    def test_card_with_page_images_is_eligible(self) -> None:
        from PIL import Image

        card = _make_card()
        card.page_images = [Image.new("RGB", (10, 10))]
        assert CardService.is_ai_eligible(card) is True

    def test_card_with_preview_image_is_eligible(self) -> None:
        from PIL import Image

        card = _make_card()
        card.preview_image = Image.new("RGB", (10, 10))
        assert CardService.is_ai_eligible(card) is True

    def test_card_with_no_images_is_not_eligible(self) -> None:
        card = _make_card()
        card.page_images = []
        card.preview_image = None
        assert CardService.is_ai_eligible(card) is False


# ── clear_cards ──


class TestClearCards:
    """Tests for CardService.clear_cards()."""

    def test_clear_cards_empties_store(self) -> None:
        """clear_cards() should clear all in-memory state."""
        card = _make_card()
        store, service = _make_store_and_service(card)
        assert store.count == 1

        service.clear_cards()

        assert store.count == 0
        assert store.is_empty


# ── unlink_path ──


class TestUnlinkPath:
    """Tests for CardService.unlink_path()."""

    def test_unlink_path_removes_card(self) -> None:
        """unlink_path() removes a path and its associated card."""
        card = _make_card()
        store, service = _make_store_and_service(card)
        path = Path("/tmp/card.pdf")
        store._hash_by_path[path] = card.file_hash

        service.unlink_path(path)

        assert store.get_hash_for_path(path) is None

    def test_unlink_path_nonexistent_is_noop(self) -> None:
        """unlink_path() with unknown path is a no-op."""
        _, service = _make_store_and_service()

        service.unlink_path(Path("/nonexistent.pdf"))  # Should not raise


# ── reset ──


class TestReset:
    """Tests for CardService.reset()."""

    @patch("app.core.services.card_service.reset_database")
    def test_reset_clears_store_and_db(self, mock_reset_db: object) -> None:
        """reset() should call reset_database() and clear the store."""
        card = _make_card()
        store, service = _make_store_and_service(card)
        assert store.count == 1

        service.reset()

        mock_reset_db.assert_called_once()  # type: ignore[union-attr]
        assert store.count == 0
        assert store.is_empty


class TestSelectCandidateInvalidConfidence:
    """Tests for candidate selection with invalid confidence (lines 105-111)."""

    @patch("app.core.services.card_service.select_candidate")
    def test_invalid_confidence_falls_back_to_medium(self, mock_db_select: object) -> None:
        """Unknown confidence value defaults to MEDIUM."""
        card = _make_card(
            candidates=[
                CandidateInfo(id=10, family_name="Smith", method="ocr", confidence="UNKNOWN_VALUE"),
            ],
        )
        _, service = _make_store_and_service(card)

        result = service.select_candidate(card.id, 10)

        assert result is not None
        assert result.confidence == Confidence.MEDIUM
        assert result.family_name == "Smith"

    @patch("app.core.services.card_service.select_candidate")
    def test_valid_confidence_set_from_candidate(self, mock_db_select: object) -> None:
        """Valid confidence string is converted to Confidence enum."""
        card = _make_card(
            candidates=[
                CandidateInfo(id=10, family_name="Smith", method="ocr", confidence="low"),
            ],
        )
        _, service = _make_store_and_service(card)

        result = service.select_candidate(card.id, 10)

        assert result is not None
        assert result.confidence == Confidence.LOW
