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
        assert "is_processing" in data
        assert "is_analyzing" in data
        assert "loaded_count" in data
        assert "current_model" in data
        assert "year" in data

    def test_load_folder_returns_count(self, clean_state, test_pdfs):
        raw = tell(f'load paths {{"{test_pdfs}"}}')
        assert raw is not None
        count = int(raw)
        assert count >= 1

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
        count = int(raw)
        assert count >= 1


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
        assert "file_hash" in data
        assert "candidates" in data

    def test_get_loaded_cards(self):
        raw = tell("get loaded cards")
        assert raw is not None
        cards = json.loads(raw)
        assert isinstance(cards, list)
        assert len(cards) >= 2
        for card in cards:
            assert "filename" in card
            assert "file_hash" in card

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
        result = tell('set card name "Alpha Card.pdf" to "TestFamily"')
        assert result == "true"

        raw = tell('get card info "Alpha Card.pdf"')
        data = json.loads(raw)
        assert data["family_name"] == "TestFamily"
        assert data["method"] == "manual"

    def test_set_remove_family(self):
        result = tell('set remove family "Alpha Card.pdf" to true')
        assert result == "true"

        raw = tell('get card info "Alpha Card.pdf"')
        data = json.loads(raw)
        assert data["remove_family"] is True


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
        result = tell('set model "claude-haiku-4-5"')
        assert result == "true"

        raw = tell("get status")
        data = json.loads(raw)
        assert data["current_model"] == "claude-haiku-4-5"

        # Reset to default
        tell('set model "claude-sonnet-4-6"')

    def test_set_invalid_model(self):
        result = tell('set model "nonexistent"')
        assert result == "false"


# ── Clear Operations ────────────────────────────────────────────────────


class TestClearOperations:
    def test_clear_all(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

        result = tell("clear all")
        assert result == "true"

        raw = tell("get loaded cards")
        cards = json.loads(raw)
        assert len(cards) == 0

    def test_reload(self, clean_state, test_pdfs):
        tell(f'load paths {{"{test_pdfs}"}}')
        assert wait_until_idle(timeout=60)

        result = tell("reload")
        assert result is not None
        # Result is either "true" or "false" depending on file changes
        assert result in ("true", "false")
