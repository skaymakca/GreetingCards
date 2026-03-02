"""Tests for MainWindow Apple Events bridge methods."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.card import CandidateInfo, CardResult, Confidence


@pytest.fixture
def window(wx_app):
    """Create a MainWindow for testing, destroy afterward."""
    from app.gui.main_window import MainWindow

    w = MainWindow()
    yield w
    w._frame.Destroy()


def _make_card(
    card_id: int = 1,
    filename: str = "test.pdf",
    family_name: str = "Smith",
    file_hash: str = "abc123",
    **kwargs,
) -> CardResult:
    """Create a CardResult with sensible defaults."""
    path = Path(f"/tmp/{filename}")
    defaults = {
        "id": card_id,
        "file_paths": [path],
        "primary_path": path,
        "family_name": family_name,
        "confidence": Confidence.HIGH,
        "method": "ocr",
        "file_hash": file_hash,
    }
    defaults.update(kwargs)
    return CardResult(**defaults)


def _inject_card(window, card: CardResult) -> None:
    """Inject a card into the window's card store."""
    store = window._card_store
    store._cards_by_hash[card.file_hash] = card
    store._id_to_card[card.id] = card
    for p in card.file_paths:
        store._hash_by_path[p] = card.file_hash


# ── _find_card_by_filename ──────────────────────────────────────────────


class TestFindCardByFilename:
    def test_exact_match(self, window):
        card = _make_card()
        _inject_card(window, card)
        assert window._find_card_by_filename("test.pdf") is card

    def test_case_insensitive(self, window):
        card = _make_card()
        _inject_card(window, card)
        assert window._find_card_by_filename("TEST.PDF") is card

    def test_match_secondary_path(self, window):
        card = _make_card()
        card.file_paths.append(Path("/other/dir/test.pdf"))
        _inject_card(window, card)
        assert window._find_card_by_filename("test.pdf") is card

    def test_no_match(self, window):
        card = _make_card()
        _inject_card(window, card)
        assert window._find_card_by_filename("nonexistent.pdf") is None


# ── get_status_for_script ────────────────────────────────────────────────


class TestGetStatusForScript:
    def test_idle_status(self, window):
        status = window.get_status_for_script()
        assert status["is_processing"] is False
        assert status["is_analyzing"] is False
        assert status["loaded_count"] == 0
        assert isinstance(status["current_model"], str)
        assert isinstance(status["year"], str)

    def test_with_loaded_cards(self, window):
        _inject_card(window, _make_card())
        status = window.get_status_for_script()
        assert status["loaded_count"] == 1

    def test_analyzing_status(self, window):
        window._ai_batch_running = True
        status = window.get_status_for_script()
        assert status["is_analyzing"] is True
        window._ai_batch_running = False


# ── get_card_info_for_script / get_all_cards_for_script ──────────────────


class TestGetCardInfoForScript:
    def test_found_card(self, window):
        card = _make_card()
        _inject_card(window, card)
        result = window.get_card_info_for_script("test.pdf")
        assert result is card

    def test_not_found(self, window):
        assert window.get_card_info_for_script("nope.pdf") is None


class TestGetAllCardsForScript:
    def test_returns_all(self, window):
        _inject_card(window, _make_card(card_id=1, file_hash="h1"))
        _inject_card(window, _make_card(card_id=2, filename="other.pdf", file_hash="h2"))
        cards = window.get_all_cards_for_script()
        assert len(cards) == 2


# ── set_card_name_for_script ────────────────────────────────────────────


class TestSetCardNameForScript:
    def test_set_name(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch("app.core.card_service.set_manual_name"):
            result = window.set_card_name_for_script("test.pdf", "Jones")

        assert result["success"] is True
        assert card.manual_override == "Jones"
        assert card.family_name == "Jones"
        assert card.confidence == Confidence.MANUAL
        assert card.method == "manual"

    def test_clear_name(self, window):
        card = _make_card(manual_override="Jones")
        _inject_card(window, card)

        with (
            patch("app.core.card_service.set_manual_name"),
            patch("app.core.card_service.load_card_state_from_db"),
        ):
            result = window.set_card_name_for_script("test.pdf", "")

        assert result["success"] is True
        assert card.manual_override == ""

    def test_not_found(self, window):
        result = window.set_card_name_for_script("nope.pdf", "Smith")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_updates_db(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch("app.core.card_service.set_manual_name") as mock_db:
            window.set_card_name_for_script("test.pdf", "NewName")
            mock_db.assert_called_once_with("abc123", "NewName", card.remove_family)


# ── select_candidate_for_script ──────────────────────────────────────────


class TestSelectCandidateForScript:
    def test_valid_rank(self, window):
        card = _make_card(
            candidates=[
                CandidateInfo(id=10, family_name="Alpha", method="ocr", confidence="high"),
                CandidateInfo(id=11, family_name="Beta", method="ai", confidence="medium"),
            ]
        )
        _inject_card(window, card)

        with patch("app.core.card_service.select_candidate"):
            result = window.select_candidate_for_script("test.pdf", 2)

        assert result["success"] is True
        assert card.family_name == "Beta"
        assert card.selected_candidate_id == 11

    def test_invalid_rank(self, window):
        card = _make_card(
            candidates=[
                CandidateInfo(id=10, family_name="Alpha", method="ocr", confidence="high"),
            ]
        )
        _inject_card(window, card)
        result = window.select_candidate_for_script("test.pdf", 5)
        assert result["success"] is False
        assert "invalid rank" in result["error"].lower()

    def test_not_found(self, window):
        result = window.select_candidate_for_script("nope.pdf", 1)
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ── set_remove_family_for_script ────────────────────────────────────────


class TestSetRemoveFamilyForScript:
    def test_toggle_on(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch("app.core.card_service.update_remove_family"):
            result = window.set_remove_family_for_script("test.pdf", True)

        assert result["success"] is True
        assert card.remove_family is True

    def test_not_found(self, window):
        result = window.set_remove_family_for_script("nope.pdf", True)
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ── load_paths_for_script ────────────────────────────────────────────────


class TestLoadPathsForScript:
    def test_returns_count(self, window):
        fake_pdfs = [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]

        with (
            patch("app.core.processing_service.scan_for_pdfs", return_value=fake_pdfs),
            patch.object(window, "_start_processing") as mock_proc,
        ):
            result = window.load_paths_for_script(["/tmp/cards"])

        assert result["success"] is True
        assert result["count"] == 2
        mock_proc.assert_called_once()

    def test_skips_already_loaded(self, window):
        existing = Path("/tmp/a.pdf")
        window._card_store._hash_by_path[existing] = "hash_a"

        with (
            patch(
                "app.core.processing_service.scan_for_pdfs",
                return_value=[existing, Path("/tmp/b.pdf")],
            ),
            patch.object(window, "_start_processing"),
        ):
            result = window.load_paths_for_script(["/tmp/cards"])

        assert result["count"] == 1

    def test_nonexistent_returns_zero(self, window):
        with patch("app.core.processing_service.scan_for_pdfs", return_value=[]):
            result = window.load_paths_for_script(["/nonexistent"])
        assert result["success"] is True
        assert result["count"] == 0


# ── rename_card_for_script ──────────────────────────────────────────────


class TestRenameCardForScript:
    def test_not_found(self, window):
        result = window.rename_card_for_script("nope.pdf", "Smith", None)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_invalid_year(self, window):
        card = _make_card()
        _inject_card(window, card)
        result = window.rename_card_for_script("test.pdf", "Smith", "abc")
        assert result["success"] is False
        assert "year" in result["error"].lower()

    def test_success(self, window):
        from app.models.card import RenameResult

        card = _make_card()
        _inject_card(window, card)
        old_path = card.primary_path
        new_path = Path("/tmp/Holiday Cards 2025 - Smith Family.pdf")

        mock_result = RenameResult(old_path, new_path, True, "Renamed", card=card)

        with (
            patch("app.core.rename_service.build_rename_plan"),
            patch("app.core.rename_service.execute_rename_plan", return_value=[mock_result]),
        ):
            result = window.rename_card_for_script("test.pdf", "Smith", "2025")

        assert result["success"] is True
        assert result["old_path"] == str(old_path)
        assert result["new_path"] == str(new_path)

    def test_custom_year(self, window):
        from app.models.card import RenameResult

        card = _make_card()
        _inject_card(window, card)
        mock_result = RenameResult(card.primary_path, Path("/tmp/out.pdf"), True, "Renamed", card=card)

        with (
            patch("app.core.rename_service.build_rename_plan") as mock_plan,
            patch("app.core.rename_service.execute_rename_plan", return_value=[mock_result]),
        ):
            window.rename_card_for_script("test.pdf", "Smith", "2024")
            # Verify build_rename_plan was called with the custom year
            mock_plan.assert_called_once()
            assert mock_plan.call_args[0][1] == "2024"

    def test_os_error(self, window):
        from app.models.card import RenameResult

        card = _make_card()
        _inject_card(window, card)
        mock_result = RenameResult(card.primary_path, Path("/tmp/out.pdf"), False, "Permission denied", card=card)

        with (
            patch("app.core.rename_service.build_rename_plan"),
            patch("app.core.rename_service.execute_rename_plan", return_value=[mock_result]),
        ):
            result = window.rename_card_for_script("test.pdf", "Smith", "2025")

        assert result["success"] is False
        assert result["error"] == "Permission denied"


# ── analyze_for_script ──────────────────────────────────────────────────


class TestAnalyzeForScript:
    def test_all_cards(self, window):
        from PIL import Image

        card = _make_card()
        card.preview_image = Image.new("RGB", (10, 10))
        _inject_card(window, card)

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value="sk-test"),
            patch.object(window, "_start_ai_all") as mock_ai,
        ):
            result = window.analyze_for_script(None)

        assert result["success"] is True
        assert result["count"] == 1
        mock_ai.assert_called_once()

    def test_single_card(self, window):
        from PIL import Image

        card = _make_card()
        card.preview_image = Image.new("RGB", (10, 10))
        _inject_card(window, card)

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value="sk-test"),
            patch.object(window, "_start_ai_all") as mock_ai,
        ):
            result = window.analyze_for_script("test.pdf")

        assert result["success"] is True
        assert result["count"] == 1
        mock_ai.assert_called_once()

    def test_not_found(self, window):
        _inject_card(window, _make_card())

        with patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value="sk-test"):
            result = window.analyze_for_script("nope.pdf")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_no_api_key(self, window):
        _inject_card(window, _make_card())

        with patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value=""):
            result = window.analyze_for_script(None)
        assert result["success"] is False
        assert "api key" in result["error"].lower()


# ── clear_ai_for_script ─────────────────────────────────────────────────


class TestClearAiForScript:
    def test_all_cards(self, window):
        card = _make_card()
        _inject_card(window, card)

        with (
            patch("app.core.card_service.clear_ai_results", return_value=1) as mock_clear,
            patch("app.core.card_service.load_card_state_from_db"),
        ):
            result = window.clear_ai_for_script(None)

        assert result["success"] is True
        assert result["count"] == 1
        mock_clear.assert_called_once_with(["abc123"])

    def test_single_card(self, window):
        card = _make_card()
        _inject_card(window, card)

        with (
            patch("app.core.card_service.clear_ai_results", return_value=1),
            patch("app.core.card_service.load_card_state_from_db"),
        ):
            result = window.clear_ai_for_script("test.pdf")

        assert result["success"] is True
        assert result["count"] == 1

    def test_not_found(self, window):
        result = window.clear_ai_for_script("nope.pdf")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ── reload_for_script ────────────────────────────────────────────────────


class TestReloadForScript:
    def test_no_loaded_paths(self, window):
        result = window.reload_for_script()
        assert result["success"] is False
        assert "no paths" in result["error"].lower()

    def test_reload_no_changes(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch.object(window, "_reload_cards", return_value=False):
            result = window.reload_for_script()
        assert result["success"] is True
        assert result["changed"] is False

    def test_reload_with_changes(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch.object(window, "_reload_cards", return_value=True):
            result = window.reload_for_script()
        assert result["success"] is True
        assert result["changed"] is True


# ── clear_all_for_script ─────────────────────────────────────────────────


class TestClearAllForScript:
    def test_clears_state(self, window):
        card = _make_card()
        _inject_card(window, card)
        assert len(window._card_store._cards_by_hash) == 1

        result = window.clear_all_for_script()
        assert result["success"] is True
        assert len(window._card_store._cards_by_hash) == 0


# ── quit_for_script ──────────────────────────────────────────────────────


class TestQuitForScript:
    def test_calls_frame_close(self, window):
        """quit_for_script must delegate to _frame.Close() to trigger _on_close."""
        from unittest.mock import patch

        with patch.object(window._frame, "Close") as mock_close:
            window.quit_for_script()

        mock_close.assert_called_once_with()


# ── Properties ───────────────────────────────────────────────────────────


class TestProperties:
    def test_is_ai_running_default(self, window):
        assert window.is_ai_running is False

    def test_is_ai_running_when_set(self, window):
        window._ai_batch_running = True
        assert window.is_ai_running is True
        window._ai_batch_running = False

    def test_is_processing_default(self, window):
        assert window.is_processing is False


# ── DB-backed clear_ai_for_script tests ──────────────────────────────────


class TestClearAiForScriptWithDB:
    """DB-backed tests for clear_ai_for_script using in_memory_db fixture."""

    @pytest.fixture(autouse=True)
    def _use_db(self, in_memory_db):
        return in_memory_db

    def _make_window_with_card(self, window, filename: str, file_hash: str, card_id: int = 1) -> CardResult:
        """Create a card and inject it into the window."""
        card = _make_card(card_id=card_id, filename=filename, file_hash=file_hash)
        _inject_card(window, card)
        return card

    def test_clear_all_returns_count(self, window):
        """clear_ai_for_script(None) returns affected count from DB."""
        from app.core.database import add_candidate, create_or_update_card, save_raw_ai

        with (
            patch("app.core.naming.family_name.clean_and_filter_family_names", return_value=["Smith"]),
            patch("app.core.naming.family_name.smart_title_case_family_name", side_effect=lambda x: x),
        ):
            create_or_update_card("h1")
            ai_cid = add_candidate("h1", "Smith", "ai", "high")
            save_raw_ai("h1", "Smith", [])

            from app.core.database import select_candidate as db_select_candidate

            db_select_candidate("h1", ai_cid)

        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            result = window.clear_ai_for_script(None)

        assert result["success"] is True
        assert result["count"] == 1

    def test_clear_specific_path_only_affects_target(self, window):
        """clear_ai_for_script(filename) only clears the named card."""
        from app.core.database import add_candidate, create_or_update_card, get_card_state, save_raw_ai

        with (
            patch("app.core.naming.family_name.clean_and_filter_family_names", return_value=["Smith"]),
            patch("app.core.naming.family_name.smart_title_case_family_name", side_effect=lambda x: x),
        ):
            create_or_update_card("h1")
            create_or_update_card("h2")
            ai_cid1 = add_candidate("h1", "Smith", "ai", "high")
            ai_cid2 = add_candidate("h2", "Jones", "ai", "high")
            save_raw_ai("h1", "Smith", [])
            save_raw_ai("h2", "Jones", [])

            from app.core.database import select_candidate as db_select_candidate

            db_select_candidate("h1", ai_cid1)
            db_select_candidate("h2", ai_cid2)

        card1 = self._make_window_with_card(window, "alpha.pdf", "h1", card_id=1)
        card2 = self._make_window_with_card(window, "beta.pdf", "h2", card_id=2)
        card1.file_hash = "h1"
        card2.file_hash = "h2"

        with patch.object(window, "_review_panel"):
            result = window.clear_ai_for_script("alpha.pdf")

        assert result["success"] is True
        assert result["count"] == 1

        # h1 should be cleared, h2 untouched
        state1 = get_card_state("h1")
        state2 = get_card_state("h2")
        assert state1.method == "missing"
        assert state2.method == "ai"

    def test_clear_returns_zero_for_ocr_only_card(self, window):
        """clear_ai_for_script returns count=0 when no AI was selected."""
        from app.core.database import add_candidate, create_or_update_card

        with (
            patch("app.core.naming.family_name.clean_and_filter_family_names", return_value=["Smith"]),
            patch("app.core.naming.family_name.smart_title_case_family_name", side_effect=lambda x: x),
        ):
            create_or_update_card("h1")
            add_candidate("h1", "Smith", "ocr", "high")

        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            result = window.clear_ai_for_script(None)

        assert result["success"] is True
        assert result["count"] == 0

    def test_clear_not_found_returns_error(self, window):
        """clear_ai_for_script returns error for unknown filename."""
        result = window.clear_ai_for_script("nonexistent.pdf")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_clear_preserves_manual_override(self, window):
        """clear_ai_for_script preserves manual name override in DB."""
        from app.core.database import add_candidate, create_or_update_card, get_card_state, set_manual_name

        with (
            patch("app.core.naming.family_name.clean_and_filter_family_names", return_value=["Smith"]),
            patch("app.core.naming.family_name.smart_title_case_family_name", side_effect=lambda x: x),
        ):
            create_or_update_card("h1")
            add_candidate("h1", "Smith", "ai", "high")
            set_manual_name("h1", "ManualName")

        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            result = window.clear_ai_for_script(None)

        assert result["success"] is True
        state = get_card_state("h1")
        assert state.display_name == "ManualName"
        assert state.method == "manual"

    def test_clear_all_removes_ai_candidates(self, window):
        """AI candidate rows are deleted from the DB after clear."""
        from app.core.database import add_candidate, create_or_update_card, get_candidates, get_raw_ai, save_raw_ai

        with (
            patch("app.core.naming.family_name.clean_and_filter_family_names", return_value=["Smith"]),
            patch("app.core.naming.family_name.smart_title_case_family_name", side_effect=lambda x: x),
        ):
            create_or_update_card("h1")
            add_candidate("h1", "Smith", "ai", "high")
            add_candidate("h1", "Smith", "ocr", "medium")
            save_raw_ai("h1", "Smith", [])

        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            window.clear_ai_for_script(None)

        # AI candidates must be gone from the candidates table
        candidates = get_candidates("h1")
        assert all(c.method != "ai" for c in candidates)
        # Raw AI result must also be deleted
        assert get_raw_ai("h1") is None

    def test_clear_reselects_ocr_after_ai_removed(self, window):
        """After AI clear, card falls back to best OCR candidate (DB state verified)."""
        from app.core.database import add_candidate, create_or_update_card, get_candidates, get_card_state
        from app.core.database import select_candidate as db_select

        with (
            patch("app.core.naming.family_name.clean_and_filter_family_names", return_value=["Smith"]),
            patch("app.core.naming.family_name.smart_title_case_family_name", side_effect=lambda x: x),
        ):
            create_or_update_card("h1")
            ocr_cid = add_candidate("h1", "Smith", "ocr", "high")
            ai_cid = add_candidate("h1", "AiName", "ai", "high")
            db_select("h1", ai_cid)

        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            window.clear_ai_for_script(None)

        # OCR candidate must still exist
        candidates = get_candidates("h1")
        assert any(c.method == "ocr" for c in candidates)
        assert all(c.method != "ai" for c in candidates)

        # Card must have fallen back to the OCR candidate
        state = get_card_state("h1")
        assert state.method == "ocr"
        assert state.selected_candidate_id == ocr_cid


# ── DB-backed mixin mutation tests ───────────────────────────────────────


class TestAppleEventsMixinWithDB:
    """DB-backed tests for set_card_name_for_script, select_candidate_for_script,
    and set_remove_family_for_script."""

    @pytest.fixture(autouse=True)
    def _use_db(self, in_memory_db):
        return in_memory_db

    def _make_window_with_card(self, window, filename: str, file_hash: str, card_id: int = 1) -> CardResult:
        """Create a card and inject it into the window."""
        card = _make_card(card_id=card_id, filename=filename, file_hash=file_hash)
        _inject_card(window, card)
        return card

    def test_set_card_name_writes_manual_to_db(self, window):
        """set_card_name_for_script persists a manual name to the DB."""
        from app.core.database import add_candidate, create_or_update_card, get_card_state

        create_or_update_card("h1")
        add_candidate("h1", "Smith", "ocr", "high")
        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            result = window.set_card_name_for_script("alpha.pdf", "Johnson")

        assert result["success"] is True
        state = get_card_state("h1")
        assert state.display_name == "Johnson"
        assert state.method == "manual"
        assert state.selected_candidate_id is None

    def test_select_candidate_updates_db(self, window):
        """select_candidate_for_script writes the selected candidate ID to the DB."""
        from app.core.database import add_candidate, create_or_update_card, get_card_state
        from app.core.database import select_candidate as db_select

        create_or_update_card("h1")
        ocr_cid = add_candidate("h1", "Smith", "ocr", "high")
        ai_cid = add_candidate("h1", "AiName", "ai", "high")
        db_select("h1", ocr_cid)

        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"
        card.candidates = [
            CandidateInfo(id=ocr_cid, family_name="Smith", method="ocr", confidence="high"),
            CandidateInfo(id=ai_cid, family_name="AiName", method="ai", confidence="high"),
        ]

        with patch.object(window, "_review_panel"):
            result = window.select_candidate_for_script("alpha.pdf", 2)

        assert result["success"] is True
        state = get_card_state("h1")
        assert state.selected_candidate_id == ai_cid
        assert state.method == "ai"

    def test_set_remove_family_updates_db(self, window):
        """set_remove_family_for_script persists the remove_family flag to the DB."""
        from app.core.database import create_or_update_card, get_card_state

        create_or_update_card("h1")
        card = self._make_window_with_card(window, "alpha.pdf", "h1")
        card.file_hash = "h1"

        with patch.object(window, "_review_panel"):
            result = window.set_remove_family_for_script("alpha.pdf", True)

        assert result["success"] is True
        state = get_card_state("h1")
        assert state.remove_family is True
