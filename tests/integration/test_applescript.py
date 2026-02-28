"""Integration tests for Apple Events — end-to-end via osascript.

Prerequisites:
  - Built app bundle at dist/Greeting Cards.app (``make app``)
  - Run with: ``uv run pytest tests/integration/ -x -m applescript``

These tests are excluded from the default ``pytest`` run.
"""

from __future__ import annotations

import json

import pytest

from tests.integration.conftest import tell, wait_until_idle

pytestmark = [pytest.mark.integration, pytest.mark.applescript]


# ── Loading & Status ─────────────────────────────────────────────────────


class TestLoadAndStatus:
    def test_get_status_returns_json(self, clean_state):
        raw = tell("get status")
        assert raw is not None
        data = json.loads(raw)
        assert data["is_processing"] is False
        assert data["is_analyzing"] is False
        assert data["loaded_count"] == 0
        assert isinstance(data["current_model"], str) and data["current_model"] != ""
        assert isinstance(data["year"], str) and len(data["year"]) == 4

    def test_load_folder_returns_count(self, clean_state, test_pdfs):
        raw = tell(f'load paths {{"{test_pdfs}"}}')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True
        assert data["count"] == 2

    def test_load_processes_pdfs(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)
        raw = tell("get loaded cards")
        assert raw is not None
        cards = json.loads(raw)
        assert len(cards) >= 2

    def test_load_mixed_files_and_folders(self, clean_state, test_pdfs):
        pdf_file = test_pdfs / "Alpha Card.pdf"
        raw = tell(f'load paths {{"{pdf_file}", "{test_pdfs}"}}')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True
        assert data["count"] >= 2


# ── Card Queries ─────────────────────────────────────────────────────────


class TestCardQueries:
    @pytest.fixture(autouse=True)
    def _load_cards(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

    def test_get_card_info(self):
        raw = tell('get card info "Alpha Card.pdf"')
        assert raw is not None
        data = json.loads(raw)
        assert data["filename"] == "Alpha Card.pdf"
        assert isinstance(data["file_hash"], str)
        assert isinstance(data["file_paths"], list) and len(data["file_paths"]) >= 1
        assert isinstance(data["family_name"], str)
        assert data["family_name"] != ""  # OCR should detect "Alpha"
        assert isinstance(data["confidence"], str)
        assert isinstance(data["method"], str)
        assert isinstance(data["manual_override"], (str, type(None)))
        assert isinstance(data["remove_family"], bool)
        assert isinstance(data["ai_analyzed"], bool)
        assert isinstance(data["candidates"], list)
        assert isinstance(data["error"], (str, type(None)))

    def test_get_loaded_cards(self):
        raw = tell("get loaded cards")
        assert raw is not None
        cards = json.loads(raw)
        assert isinstance(cards, list)
        assert len(cards) == 2
        filenames = {c["filename"] for c in cards}
        assert filenames == {"Alpha Card.pdf", "Beta Card.pdf"}
        for card in cards:
            assert isinstance(card["filename"], str)
            assert isinstance(card["file_hash"], str)
            assert isinstance(card["family_name"], str)
            assert isinstance(card["confidence"], str)

    def test_get_card_info_not_found(self):
        raw = tell('get card info "nonexistent.pdf"')
        assert raw is not None
        data = json.loads(raw)
        assert "error" in data


# ── Card Mutations ───────────────────────────────────────────────────────


class TestCardMutations:
    @pytest.fixture(autouse=True)
    def _load_cards(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

    def test_set_card_name(self):
        raw = tell('set card name "Alpha Card.pdf" to "TestFamily"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True

        raw = tell('get card info "Alpha Card.pdf"')
        card_data = json.loads(raw)
        assert card_data["family_name"] == "TestFamily"
        assert card_data["method"] == "manual"

    def test_set_remove_family(self):
        raw = tell('set remove family "Alpha Card.pdf" to true')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True

        raw = tell('get card info "Alpha Card.pdf"')
        card_data = json.loads(raw)
        assert card_data["remove_family"] is True


# ── Model Management ────────────────────────────────────────────────────


class TestModelManagement:
    def test_get_models(self):
        raw = tell("get models")
        assert raw is not None
        models = json.loads(raw)
        assert isinstance(models, list)
        assert len(models) == 3
        model_ids = [m["model_id"] for m in models]
        assert "claude-haiku-4-5" in model_ids
        assert "claude-sonnet-4-6" in model_ids
        assert "claude-opus-4-6" in model_ids

    def test_set_model(self):
        raw = tell('set model "claude-haiku-4-5"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True

        status_raw = tell("get status")
        status = json.loads(status_raw)
        assert status["current_model"] == "claude-haiku-4-5"

        # Reset to default
        tell('set model "claude-sonnet-4-6"')

    def test_set_invalid_model(self):
        raw = tell('set model "nonexistent"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data


# ── Clear Operations ────────────────────────────────────────────────────


class TestClearOperations:
    def test_clear_all(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

        raw = tell("clear all")
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True

        cards_raw = tell("get loaded cards")
        cards = json.loads(cards_raw)
        assert len(cards) == 0

    def test_reload(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

        raw = tell("reload")
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True
        assert isinstance(data["changed"], bool)


# ── Rename Card ──────────────────────────────────────────────────────────


class TestRenameCard:
    @pytest.fixture(autouse=True)
    def _load_cards(self, clean_state, rename_pdfs):
        tell(f'load paths {{"{rename_pdfs}"}}')
        assert wait_until_idle(timeout=60)

    def test_rename_success(self, rename_pdfs):
        raw = tell('rename card "RenameTarget.pdf" to "TestFamily" year "2025"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True
        assert "RenameTarget.pdf" in data["old_path"]
        assert data["new_path"] != data["old_path"]
        assert data["error"] == ""

    def test_rename_not_found(self):
        raw = tell('rename card "nonexistent.pdf" to "TestFamily" year "2025"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data

    def test_rename_invalid_year(self, rename_pdfs):
        raw = tell('rename card "RenameTarget.pdf" to "TestFamily" year "bad"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data


# ── Select Candidate ─────────────────────────────────────────────────────


class TestSelectCandidate:
    @pytest.fixture(autouse=True)
    def _load_cards(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

    def test_select_not_found(self):
        raw = tell('select candidate "nonexistent.pdf" rank 1')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data

    def test_select_invalid_rank(self):
        raw = tell('select candidate "Alpha Card.pdf" rank 999')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data

    def test_select_valid_rank(self):
        # Query candidates first — skip if none available
        info_raw = tell('get card info "Alpha Card.pdf"')
        assert info_raw is not None
        info = json.loads(info_raw)
        if not info.get("candidates"):
            pytest.skip("No candidates available for Alpha Card.pdf")

        first_candidate = info["candidates"][0]
        raw = tell('select candidate "Alpha Card.pdf" rank 1')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True

        # Verify card state matches the selected candidate
        updated_raw = tell('get card info "Alpha Card.pdf"')
        assert updated_raw is not None
        updated = json.loads(updated_raw)
        assert updated["family_name"] == first_candidate["name"]
        assert updated["method"] == first_candidate["method"]


# ── AI Operations ────────────────────────────────────────────────────────


class TestClearAiResults:
    @pytest.fixture(autouse=True)
    def _load_cards(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

    def test_clear_ai_all(self):
        raw = tell("clear ai results")
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True
        assert isinstance(data["count"], int)
        assert data["count"] >= 0

    def test_clear_ai_single_card(self):
        raw = tell('clear ai results "Alpha Card.pdf"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is True
        assert isinstance(data["count"], int)

    def test_clear_ai_not_found(self):
        raw = tell('clear ai results "nonexistent.pdf"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data


class TestAnalyzeCards:
    def test_analyze_no_cards_loaded(self, clean_state):
        raw = tell("analyze cards")
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data

    def test_analyze_not_found(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

        raw = tell('analyze cards "nonexistent.pdf"')
        assert raw is not None
        data = json.loads(raw)
        assert data["success"] is False
        assert "error" in data
