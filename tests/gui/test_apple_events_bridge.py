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
    """Inject a card into the window's state dictionaries."""
    window._cards_by_hash[card.file_hash] = card
    window._id_to_card[card.id] = card
    for p in card.file_paths:
        window._hash_by_path[p] = card.file_hash


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

        with patch("app.gui.main_window_mixins.apple_events_mixin.set_manual_name"):
            result = window.set_card_name_for_script("test.pdf", "Jones")

        assert result is True
        assert card.manual_override == "Jones"
        assert card.family_name == "Jones"
        assert card.confidence == Confidence.MANUAL
        assert card.method == "manual"

    def test_clear_name(self, window):
        card = _make_card(manual_override="Jones")
        _inject_card(window, card)

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.set_manual_name"),
            patch("app.gui.main_window_mixins.apple_events_mixin.load_card_state_from_db"),
        ):
            result = window.set_card_name_for_script("test.pdf", "")

        assert result is True
        assert card.manual_override == ""

    def test_not_found(self, window):
        result = window.set_card_name_for_script("nope.pdf", "Smith")
        assert result is False

    def test_updates_db(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch("app.gui.main_window_mixins.apple_events_mixin.set_manual_name") as mock_db:
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

        with patch("app.core.database.select_candidate"):
            result = window.select_candidate_for_script("test.pdf", 2)

        assert result is True
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
        assert result is False

    def test_not_found(self, window):
        result = window.select_candidate_for_script("nope.pdf", 1)
        assert result is False


# ── set_remove_family_for_script ────────────────────────────────────────


class TestSetRemoveFamilyForScript:
    def test_toggle_on(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch("app.core.database.update_remove_family"):
            result = window.set_remove_family_for_script("test.pdf", True)

        assert result is True
        assert card.remove_family is True

    def test_not_found(self, window):
        result = window.set_remove_family_for_script("nope.pdf", True)
        assert result is False


# ── load_paths_for_script ────────────────────────────────────────────────


class TestLoadPathsForScript:
    def test_returns_count(self, window):
        fake_pdfs = [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.scan_for_pdfs", return_value=fake_pdfs),
            patch.object(window, "_start_processing") as mock_proc,
        ):
            count = window.load_paths_for_script(["/tmp/cards"])

        assert count == 2
        mock_proc.assert_called_once()

    def test_skips_already_loaded(self, window):
        existing = Path("/tmp/a.pdf")
        window._hash_by_path[existing] = "hash_a"

        with (
            patch(
                "app.gui.main_window_mixins.apple_events_mixin.scan_for_pdfs",
                return_value=[existing, Path("/tmp/b.pdf")],
            ),
            patch.object(window, "_start_processing"),
        ):
            count = window.load_paths_for_script(["/tmp/cards"])

        assert count == 1

    def test_nonexistent_returns_zero(self, window):
        with patch("app.gui.main_window_mixins.apple_events_mixin.scan_for_pdfs", return_value=[]):
            count = window.load_paths_for_script(["/nonexistent"])
        assert count == 0


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
            patch("app.gui.main_window_mixins.apple_events_mixin.build_rename_plan"),
            patch("app.gui.main_window_mixins.apple_events_mixin.execute_rename_plan", return_value=[mock_result]),
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
            patch("app.gui.main_window_mixins.apple_events_mixin.build_rename_plan") as mock_plan,
            patch("app.gui.main_window_mixins.apple_events_mixin.execute_rename_plan", return_value=[mock_result]),
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
            patch("app.gui.main_window_mixins.apple_events_mixin.build_rename_plan"),
            patch("app.gui.main_window_mixins.apple_events_mixin.execute_rename_plan", return_value=[mock_result]),
        ):
            result = window.rename_card_for_script("test.pdf", "Smith", "2025")

        assert result["success"] is False
        assert result["error"] == "Permission denied"


# ── analyze_for_script ──────────────────────────────────────────────────


class TestAnalyzeForScript:
    def test_all_cards(self, window):
        card = _make_card()
        _inject_card(window, card)

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value="sk-test"),
            patch.object(window, "_start_ai_all") as mock_ai,
        ):
            count = window.analyze_for_script(None)

        assert count == 1
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
            count = window.analyze_for_script("test.pdf")

        assert count == 1
        mock_ai.assert_called_once()

    def test_not_found(self, window):
        _inject_card(window, _make_card())

        with patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value="sk-test"):
            count = window.analyze_for_script("nope.pdf")
        assert count == 0

    def test_no_api_key(self, window):
        _inject_card(window, _make_card())

        with patch("app.gui.main_window_mixins.apple_events_mixin.get_api_key", return_value=""):
            count = window.analyze_for_script(None)
        assert count == 0


# ── clear_ai_for_script ─────────────────────────────────────────────────


class TestClearAiForScript:
    def test_all_cards(self, window):
        card = _make_card()
        _inject_card(window, card)

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.clear_ai_results", return_value=1) as mock_clear,
            patch("app.gui.main_window_mixins.apple_events_mixin.load_card_state_from_db"),
        ):
            count = window.clear_ai_for_script(None)

        assert count == 1
        mock_clear.assert_called_once_with(["abc123"])

    def test_single_card(self, window):
        card = _make_card()
        _inject_card(window, card)

        with (
            patch("app.gui.main_window_mixins.apple_events_mixin.clear_ai_results", return_value=1),
            patch("app.gui.main_window_mixins.apple_events_mixin.load_card_state_from_db"),
        ):
            count = window.clear_ai_for_script("test.pdf")

        assert count == 1

    def test_not_found(self, window):
        count = window.clear_ai_for_script("nope.pdf")
        assert count == 0


# ── reload_for_script ────────────────────────────────────────────────────


class TestReloadForScript:
    def test_no_loaded_paths(self, window):
        assert window.reload_for_script() is False

    def test_reload_no_changes(self, window):
        card = _make_card()
        _inject_card(window, card)

        with patch.object(window, "_reload_cards"):
            result = window.reload_for_script()
        # Since _reload_cards is mocked and doesn't modify state, hashes remain same
        assert result is False


# ── clear_all_for_script ─────────────────────────────────────────────────


class TestClearAllForScript:
    def test_clears_state(self, window):
        card = _make_card()
        _inject_card(window, card)
        assert len(window._cards_by_hash) == 1

        result = window.clear_all_for_script()
        assert result is True
        assert len(window._cards_by_hash) == 0


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
