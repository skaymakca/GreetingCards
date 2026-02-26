"""Tests for app.core.database module."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.database as db_mod
from app.core.database import (
    Base,
    Candidate,
    Card,
    RawAIResult,
    RawOCRResult,
    Settings,
    _add_candidate_inline,
    _compute_schema_version,
    _ensure_schema,
    _session_scope,
    add_candidate,
    clear_ai_results,
    clear_unselected_candidates,
    compute_file_hash,
    create_or_update_card,
    get_candidates,
    get_card_state,
    get_raw_ai,
    get_raw_ocr,
    reprocess_candidates_from_raw,
    reset_database,
    save_raw_ai,
    save_raw_ocr,
    select_candidate,
    set_manual_name,
    should_reprocess,
    update_remove_family,
)


@pytest.fixture(autouse=True)
def in_memory_db():
    """Override database globals to use an in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    session_factory = sessionmaker(bind=engine)

    # Save originals
    orig_engine = db_mod._engine
    orig_session = db_mod._Session

    # Override module globals
    db_mod._engine = engine
    db_mod._Session = session_factory

    # Create schema
    Base.metadata.create_all(engine)
    session = session_factory()
    session.add(Settings(key="schema_version", value=_compute_schema_version()))
    session.commit()
    session.close()

    yield engine

    # Clean up
    engine.dispose()

    # Restore
    db_mod._engine = orig_engine
    db_mod._Session = orig_session


class TestSchemaVersion:
    """Tests for schema versioning."""

    def test_compute_schema_version_is_hex(self):
        version = _compute_schema_version()
        assert len(version) == 16
        int(version, 16)  # Should not raise

    def test_schema_version_deterministic(self):
        v1 = _compute_schema_version()
        v2 = _compute_schema_version()
        assert v1 == v2


class TestCreateOrUpdateCard:
    """Tests for create_or_update_card()."""

    def test_creates_card(self):
        create_or_update_card("hash1")
        state = get_card_state("hash1")
        assert state is not None
        assert state.display_name == ""
        assert state.method == "missing"

    def test_idempotent(self):
        create_or_update_card("hash1")
        create_or_update_card("hash1")  # Should not raise
        state = get_card_state("hash1")
        assert state is not None

    def test_remove_family_flag(self):
        create_or_update_card("hash1", remove_family=True)
        state = get_card_state("hash1")
        assert state.remove_family is True


class TestAddCandidate:
    """Tests for add_candidate()."""

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_adds_candidate(self, mock_title, mock_clean):
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid > 0
        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].family_name == "Smith"

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_dedup_same_name_method(self, mock_title, mock_clean):
        cid1 = add_candidate("hash1", "Smith", "ocr", "high")
        cid2 = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid1 == cid2
        candidates = get_candidates("hash1")
        assert len(candidates) == 1

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=[])
    def test_filtered_name_returns_zero(self, mock_clean):
        cid = add_candidate("hash1", "unknown", "ocr", "low")
        assert cid == 0

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_auto_creates_card(self, mock_title, mock_clean):
        """Card is auto-created if it doesn't exist."""
        add_candidate("newhash", "Smith", "ai", "high")
        state = get_card_state("newhash")
        assert state is not None


class TestGetCandidates:
    """Tests for get_candidates()."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_sorted_by_method_then_confidence(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "OcrLow", "ocr", "low")
        add_candidate("hash1", "AiHigh", "ai", "high")
        add_candidate("hash1", "OcrHigh", "ocr", "high")

        candidates = get_candidates("hash1")
        methods = [c.method for c in candidates]
        # AI should come before OCR
        assert methods.index("ai") < methods.index("ocr")

    def test_empty_for_nonexistent(self):
        assert get_candidates("nonexistent") == []


class TestSetManualName:
    """Tests for set_manual_name()."""

    def test_sets_manual_name(self):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Johnson")
        state = get_card_state("hash1")
        assert state.display_name == "Johnson"
        assert state.method == "manual"
        assert state.confidence == "manual"

    def test_clears_candidate_id(self):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Johnson")
        state = get_card_state("hash1")
        assert state.selected_candidate_id is None

    def test_creates_card_if_missing(self):
        set_manual_name("newhash", "Smith")
        state = get_card_state("newhash")
        assert state.display_name == "Smith"


class TestSelectCandidate:
    """Tests for select_candidate()."""

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_selects_candidate(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        select_candidate("hash1", cid)
        state = get_card_state("hash1")
        assert state.display_name == "Smith"
        assert state.selected_candidate_id == cid

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_clears_manual_name(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Manual")
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        select_candidate("hash1", cid)
        state = get_card_state("hash1")
        assert state.method != "manual"


class TestUpdateRemoveFamily:
    """Tests for update_remove_family()."""

    def test_updates_flag(self):
        create_or_update_card("hash1")
        update_remove_family("hash1", True)
        state = get_card_state("hash1")
        assert state.remove_family is True

    def test_no_error_for_nonexistent(self):
        """Silently does nothing for nonexistent card."""
        update_remove_family("nonexistent", True)


class TestGetCardState:
    """Tests for get_card_state()."""

    def test_nonexistent_returns_none(self):
        assert get_card_state("nonexistent") is None

    def test_missing_state(self):
        create_or_update_card("hash1")
        state = get_card_state("hash1")
        assert state.method == "missing"
        assert state.confidence == "none"
        assert state.display_name == ""

    def test_manual_state(self):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Smith")
        state = get_card_state("hash1")
        assert state.method == "manual"
        assert state.confidence == "manual"
        assert state.display_name == "Smith"

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Jones"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_candidate_state(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "Jones", "ai", "high")
        select_candidate("hash1", cid)
        state = get_card_state("hash1")
        assert state.method == "ai"
        assert state.confidence == "high"
        assert state.display_name == "Jones"


class TestRawOcr:
    """Tests for save_raw_ocr() and get_raw_ocr()."""

    def test_save_and_get(self):
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "OCR text here")
        assert get_raw_ocr("hash1") == "OCR text here"

    def test_get_nonexistent(self):
        assert get_raw_ocr("nonexistent") is None

    def test_update_existing(self):
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "first")
        save_raw_ocr("hash1", "second")
        assert get_raw_ocr("hash1") == "second"

    def test_auto_creates_card(self):
        save_raw_ocr("newhash", "text")
        assert get_raw_ocr("newhash") == "text"


class TestRawAi:
    """Tests for save_raw_ai() and get_raw_ai()."""

    def test_save_and_get(self):
        create_or_update_card("hash1")
        save_raw_ai("hash1", "Smith", ["Jones", "Williams"])
        result = get_raw_ai("hash1")
        assert result == ("Smith", ["Jones", "Williams"])

    def test_get_nonexistent(self):
        assert get_raw_ai("nonexistent") is None

    def test_update_existing(self):
        create_or_update_card("hash1")
        save_raw_ai("hash1", "First", [])
        save_raw_ai("hash1", "Second", ["Alt"])
        assert get_raw_ai("hash1") == ("Second", ["Alt"])

    def test_auto_creates_card(self):
        save_raw_ai("newhash", "Name", [])
        assert get_raw_ai("newhash") is not None


class TestClearUnselectedCandidates:
    """Tests for clear_unselected_candidates()."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_clears_unselected(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "A", "ocr", "high")
        cid = add_candidate("hash1", "B", "ocr", "medium")
        select_candidate("hash1", cid)
        clear_unselected_candidates("hash1", "ocr")
        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].family_name == "B"

    def test_no_error_nonexistent(self):
        clear_unselected_candidates("nonexistent", "ocr")


class TestShouldReprocess:
    """Tests for should_reprocess()."""

    def test_true_when_no_candidates(self):
        create_or_update_card("hash1")
        assert should_reprocess("hash1", "ocr") is True

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_false_when_candidates_exist(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "Smith", "ocr", "high")
        assert should_reprocess("hash1", "ocr") is False

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_method_specific(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "Smith", "ocr", "high")
        assert should_reprocess("hash1", "ai") is True


class TestReprocessCandidatesFromRaw:
    """Tests for reprocess_candidates_from_raw()."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_reprocesses_ocr(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "The Smith Family")
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        assert len(candidates) > 0

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_reprocesses_ai(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        save_raw_ai("hash1", "Johnson", ["Williams"])
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        names = [c.family_name for c in candidates]
        assert "Johnson" in names

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_preserves_manual_entry(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Manual")
        save_raw_ocr("hash1", "The Smith Family")
        reprocess_candidates_from_raw("hash1")
        state = get_card_state("hash1")
        # Manual entry should be preserved
        assert state.display_name == "Manual"
        assert state.method == "manual"

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_reprocesses_both_ocr_and_ai(self, mock_title, mock_clean):
        """When both OCR and AI raw data exist, both are processed as candidates."""
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "The Smith Family")
        save_raw_ai("hash1", "Johnson", ["Williams"])
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        names = [c.family_name for c in candidates]
        # AI primary should be present
        assert "Johnson" in names
        # OCR candidates should also be present
        assert len(candidates) >= 2

    def test_nonexistent_card_noop(self):
        reprocess_candidates_from_raw("nonexistent")  # Should not raise


class TestComputeFileHash:
    """Tests for compute_file_hash()."""

    def test_computes_sha256(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        result = compute_file_hash(f)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert compute_file_hash(f1) != compute_file_hash(f2)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = compute_file_hash(f)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected


class TestEnsureSchema:
    """Tests for _ensure_schema() — schema migration logic."""

    def test_schema_mismatch_recreates(self):
        """When schema version doesn't match, tables are dropped and recreated."""
        session = db_mod._Session()
        # Tamper with the stored schema version
        row = session.query(Settings).filter_by(key="schema_version").first()
        row.value = "badhash000000000"
        session.commit()
        session.close()

        # _ensure_schema should detect mismatch and recreate
        _ensure_schema()

        # Verify schema version is now correct
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        assert row.value == _compute_schema_version()
        session.close()

    def test_missing_settings_table_recreates(self):
        """When settings table is missing, schema is created from scratch."""
        from sqlalchemy import text

        # Drop the settings table
        with db_mod._engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS settings"))

        _ensure_schema()

        # Verify schema was recreated
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        assert row is not None
        assert row.value == _compute_schema_version()
        session.close()

    def test_orphaned_tables_dropped(self):
        """Orphaned tables not in current metadata are dropped during migration."""
        from sqlalchemy import inspect, text

        # Create an orphaned table
        with db_mod._engine.begin() as conn:
            conn.execute(text("CREATE TABLE orphan_table (id INTEGER PRIMARY KEY)"))

        # Tamper schema version to force migration
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        row.value = "badhash000000000"
        session.commit()
        session.close()

        _ensure_schema()

        # Verify orphaned table was dropped
        inspector = inspect(db_mod._engine)
        assert "orphan_table" not in inspector.get_table_names()


class TestResetDatabase:
    """Tests for reset_database()."""

    def test_clears_all_data(self):
        """reset_database drops and recreates all tables."""
        # Add some data first
        create_or_update_card("hash1")
        set_manual_name("hash1", "Smith")
        assert get_card_state("hash1") is not None

        reset_database()

        # Data should be gone but tables should exist
        assert get_card_state("hash1") is None

    def test_schema_version_preserved(self):
        """After reset, schema version is set correctly."""
        reset_database()
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        assert row is not None
        assert row.value == _compute_schema_version()
        session.close()

    def test_reset_when_engine_is_none(self):
        """reset_database creates engine if it doesn't exist."""
        orig_engine = db_mod._engine
        orig_session = db_mod._Session
        try:
            db_mod._engine = None
            db_mod._Session = None
            # Should not raise — creates engine internally
            reset_database()
        finally:
            db_mod._engine = orig_engine
            db_mod._Session = orig_session


class TestSelectCandidateNewCard:
    """Tests for select_candidate() when card doesn't exist yet."""

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_creates_card_on_select(self, mock_title, mock_clean):
        """select_candidate creates a Card row if one doesn't exist."""
        # Add a candidate (auto-creates card)
        cid = add_candidate("newhash2", "Smith", "ocr", "high")
        # Delete the card but keep the candidate
        session = db_mod._Session()
        session.query(Card).filter_by(file_hash="newhash2").delete()
        session.commit()
        session.close()

        # select_candidate should create a new card
        select_candidate("newhash2", cid)
        state = get_card_state("newhash2")
        assert state is not None
        assert state.selected_candidate_id == cid


class TestGetCardStateDeletedCandidate:
    """Tests for get_card_state() when selected candidate was deleted."""

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_missing_candidate_returns_missing(self, mock_title, mock_clean):
        """When selected candidate no longer exists, state shows missing."""
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        select_candidate("hash1", cid)

        # Delete the candidate directly
        session = db_mod._Session()
        session.query(Candidate).filter_by(id=cid).delete()
        session.commit()
        session.close()

        state = get_card_state("hash1")
        assert state.display_name == ""
        assert state.method == "missing"
        assert state.confidence == "none"


class TestClearUnselectedCandidatesEdgeCases:
    """Tests for clear_unselected_candidates() edge cases."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_selected_candidate_same_method_preserved(self, mock_title, mock_clean):
        """When selected candidate is of the same method being cleared, it's preserved."""
        create_or_update_card("hash1")
        cid1 = add_candidate("hash1", "A", "ocr", "high")
        add_candidate("hash1", "B", "ocr", "medium")
        select_candidate("hash1", cid1)

        clear_unselected_candidates("hash1", "ocr")

        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].id == cid1

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_selected_candidate_different_method_deletes_all(self, mock_title, mock_clean):
        """When selected candidate is of a different method, all of target method are deleted."""
        create_or_update_card("hash1")
        ai_cid = add_candidate("hash1", "AI_Name", "ai", "high")
        add_candidate("hash1", "OCR_A", "ocr", "high")
        add_candidate("hash1", "OCR_B", "ocr", "medium")
        select_candidate("hash1", ai_cid)

        clear_unselected_candidates("hash1", "ocr")

        candidates = get_candidates("hash1")
        methods = [c.method for c in candidates]
        assert "ocr" not in methods
        assert "ai" in methods

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_no_selection_deletes_all_of_method(self, mock_title, mock_clean):
        """When no candidate is selected, all candidates of the method are deleted."""
        create_or_update_card("hash1")
        add_candidate("hash1", "A", "ocr", "high")
        add_candidate("hash1", "B", "ocr", "medium")
        add_candidate("hash1", "C", "ai", "high")

        clear_unselected_candidates("hash1", "ocr")

        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].method == "ai"


class TestClearAIResults:
    """Tests for clear_ai_results()."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_deletes_ai_candidates_and_raw(self, mock_title, mock_clean):
        """AI candidates and raw_ai_results are deleted for given hashes."""
        create_or_update_card("hash1")
        add_candidate("hash1", "AiName", "ai", "high")
        save_raw_ai("hash1", "AiName", ["Alt"])

        clear_ai_results(["hash1"])

        candidates = get_candidates("hash1")
        assert all(c.method != "ai" for c in candidates)
        assert get_raw_ai("hash1") is None

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_preserves_ocr_candidates(self, mock_title, mock_clean):
        """OCR candidates and raw_ocr_results survive clearing."""
        create_or_update_card("hash1")
        add_candidate("hash1", "OcrName", "ocr", "high")
        add_candidate("hash1", "AiName", "ai", "high")
        save_raw_ocr("hash1", "OCR text")
        save_raw_ai("hash1", "AiName", [])

        clear_ai_results(["hash1"])

        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].family_name == "OcrName"
        assert candidates[0].method == "ocr"
        assert get_raw_ocr("hash1") == "OCR text"

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_reselects_ocr_after_ai_cleared(self, mock_title, mock_clean):
        """Card with selected AI candidate reverts to best OCR candidate."""
        create_or_update_card("hash1")
        ocr_cid = add_candidate("hash1", "OcrName", "ocr", "high")
        ai_cid = add_candidate("hash1", "AiName", "ai", "high")
        select_candidate("hash1", ai_cid)

        clear_ai_results(["hash1"])

        state = get_card_state("hash1")
        assert state.display_name == "OcrName"
        assert state.method == "ocr"
        assert state.selected_candidate_id == ocr_cid

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_clears_selection_when_no_ocr(self, mock_title, mock_clean):
        """Card with only AI candidates gets empty selection after clearing."""
        create_or_update_card("hash1")
        ai_cid = add_candidate("hash1", "AiName", "ai", "high")
        select_candidate("hash1", ai_cid)

        clear_ai_results(["hash1"])

        state = get_card_state("hash1")
        assert state.display_name == ""
        assert state.method == "missing"
        assert state.selected_candidate_id is None

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_preserves_manual_entries(self, mock_title, mock_clean):
        """Manual entries (selected_family_name) are untouched."""
        create_or_update_card("hash1")
        add_candidate("hash1", "AiName", "ai", "high")
        set_manual_name("hash1", "ManualName")

        clear_ai_results(["hash1"])

        state = get_card_state("hash1")
        assert state.display_name == "ManualName"
        assert state.method == "manual"

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_preserves_remove_family(self, mock_title, mock_clean):
        """remove_family flag survives clearing."""
        create_or_update_card("hash1")
        ai_cid = add_candidate("hash1", "AiName", "ai", "high")
        select_candidate("hash1", ai_cid, remove_family=True)

        clear_ai_results(["hash1"])

        state = get_card_state("hash1")
        assert state.remove_family is True

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_returns_affected_count(self, mock_title, mock_clean):
        """Returns count of cards whose selection changed."""
        create_or_update_card("hash1")
        create_or_update_card("hash2")
        ai_cid1 = add_candidate("hash1", "Ai1", "ai", "high")
        select_candidate("hash1", ai_cid1)
        add_candidate("hash2", "Ocr2", "ocr", "high")  # No AI selected

        changed = clear_ai_results(["hash1", "hash2"])
        assert changed == 1  # Only hash1 had AI selected

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_scoped_to_given_hashes(self, mock_title, mock_clean):
        """Cards NOT in the list are untouched."""
        create_or_update_card("hash1")
        create_or_update_card("hash2")
        ai_cid1 = add_candidate("hash1", "Ai1", "ai", "high")
        ai_cid2 = add_candidate("hash2", "Ai2", "ai", "high")
        select_candidate("hash1", ai_cid1)
        select_candidate("hash2", ai_cid2)
        save_raw_ai("hash1", "Ai1", [])
        save_raw_ai("hash2", "Ai2", [])

        # Only clear hash1
        clear_ai_results(["hash1"])

        # hash1 cleared
        state1 = get_card_state("hash1")
        assert state1.method == "missing"
        assert get_raw_ai("hash1") is None

        # hash2 untouched
        state2 = get_card_state("hash2")
        assert state2.display_name == "Ai2"
        assert state2.method == "ai"
        assert get_raw_ai("hash2") is not None

    def test_empty_hashes_returns_zero(self):
        """Passing empty list returns 0 without error."""
        assert clear_ai_results([]) == 0


class TestClearAIResultsEdgeCases:
    """Edge case tests for clear_ai_results()."""

    def test_nonexistent_hash(self):
        """Nonexistent hash doesn't error and returns 0."""
        changed = clear_ai_results(["nonexistent_hash"])
        assert changed == 0

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_manual_plus_ai_preserves_manual(self, mock_title, mock_clean):
        """Card with manual entry + AI selected: manual preserved, AI cleared."""
        create_or_update_card("hash1")
        add_candidate("hash1", "AiName", "ai", "high")
        # Set manual name (this clears selected_candidate_id)
        set_manual_name("hash1", "ManualName")
        # Now also have AI candidate (but not selected due to manual)
        save_raw_ai("hash1", "AiName", [])

        changed = clear_ai_results(["hash1"])

        state = get_card_state("hash1")
        assert state.display_name == "ManualName"
        assert state.method == "manual"
        # AI candidate should be gone
        candidates = get_candidates("hash1")
        assert all(c.method != "ai" for c in candidates)
        # No selection changed (manual was already selected)
        assert changed == 0

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_multi_ocr_selects_best(self, mock_title, mock_clean):
        """After clearing AI, best OCR candidate (by confidence) is selected."""
        create_or_update_card("hash1")
        add_candidate("hash1", "LowName", "ocr", "low")
        ocr_high = add_candidate("hash1", "HighName", "ocr", "high")
        ai_cid = add_candidate("hash1", "AiName", "ai", "high")
        select_candidate("hash1", ai_cid)

        clear_ai_results(["hash1"])

        state = get_card_state("hash1")
        assert state.selected_candidate_id == ocr_high
        assert state.display_name == "HighName"
        assert state.confidence == "high"


class TestReprocessCandidatesEdgeCases:
    """Edge case tests for reprocess_candidates_from_raw()."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_empty_ocr_text(self, mock_title, mock_clean):
        """Empty OCR text produces no OCR candidates."""
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "")
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        # No meaningful names from empty text
        assert len(candidates) == 0

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_empty_best_name_and_alternates(self, mock_title, mock_clean):
        """AI result with empty best_name and no alternates produces no AI candidates."""
        create_or_update_card("hash1")
        save_raw_ai("hash1", "", [])
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        ai_candidates = [c for c in candidates if c.method == "ai"]
        assert len(ai_candidates) == 0

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_no_alternates(self, mock_title, mock_clean):
        """AI result with only best_name and no alternates produces one AI candidate."""
        create_or_update_card("hash1")
        save_raw_ai("hash1", "Smith", [])
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        ai_candidates = [c for c in candidates if c.method == "ai"]
        assert len(ai_candidates) == 1
        assert ai_candidates[0].family_name == "Smith"
        assert ai_candidates[0].confidence == "high"

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_corrupted_json(self, mock_title, mock_clean):
        """Corrupted JSON in raw_ai_results is handled gracefully during reprocessing."""
        create_or_update_card("hash1")
        # Directly insert corrupted JSON into raw_ai_results
        session = db_mod._Session()

        session.query(Card).filter_by(file_hash="hash1").first()
        ai_result = RawAIResult(file_hash="hash1", raw_response="not valid json{{{")
        session.add(ai_result)
        session.commit()
        session.close()

        # Should not raise — corrupted JSON is logged and skipped
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        ai_candidates = [c for c in candidates if c.method == "ai"]
        assert ai_candidates == []


class TestSessionScope:
    """Tests for _session_scope context manager."""

    def test_commits_on_success(self):
        """Changes are committed when block exits normally."""
        with _session_scope() as session:
            session.add(Card(file_hash="scope_test"))
        # Verify persisted
        state = get_card_state("scope_test")
        assert state is not None

    def test_rollback_on_exception(self):
        """Changes are rolled back on exception."""
        with pytest.raises(ValueError), _session_scope() as session:
            session.add(Card(file_hash="rollback_test"))
            session.flush()
            raise ValueError("test error")
        # Verify NOT persisted
        state = get_card_state("rollback_test")
        assert state is None

    def test_yields_session(self):
        """Context manager yields a usable Session."""
        with _session_scope() as session:
            assert session is not None
            # Should be able to query
            result = session.query(Card).all()
            assert isinstance(result, list)


class TestDefensiveGuards:
    """Tests for defensive guard clauses that raise on uninitialized state."""

    def test_get_engine_raises_when_none(self):
        """_get_engine raises RuntimeError when engine is not initialized."""
        from app.core.database import _get_engine

        orig = db_mod._engine
        try:
            db_mod._engine = None
            with pytest.raises(RuntimeError, match="Database not initialized"):
                _get_engine()
        finally:
            db_mod._engine = orig

    def test_get_session_factory_raises_when_none(self):
        """_get_session_factory raises RuntimeError when session factory is not initialized."""
        from app.core.database import _get_session_factory

        orig = db_mod._Session
        try:
            db_mod._Session = None
            with pytest.raises(RuntimeError, match="Database not initialized"):
                _get_session_factory()
        finally:
            db_mod._Session = orig

    def test_get_session_initializes_when_none(self):
        """get_session() creates engine and session factory when not initialized."""
        from app.core.database import get_session

        orig_engine = db_mod._engine
        orig_session = db_mod._Session
        try:
            db_mod._engine = None
            db_mod._Session = None
            with (
                patch("app.core.database.get_db_path", return_value=":memory:"),
                patch("app.core.database._ensure_schema"),
            ):
                session = get_session()
                assert session is not None
                session.close()
                # Engine and session factory should now be set
                assert db_mod._engine is not None
                assert db_mod._Session is not None
        finally:
            db_mod._engine = orig_engine
            db_mod._Session = orig_session


class TestAddCandidateDuplicateRace:
    """Tests for add_candidate() handling concurrent duplicate inserts."""

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_concurrent_duplicate_no_error(self, mock_title, mock_clean):
        """Calling add_candidate twice with the same args returns the same ID without error."""
        create_or_update_card("hash1")

        cid1 = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid1 > 0

        cid2 = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid1 == cid2

        # Only one candidate should exist
        candidates = get_candidates("hash1")
        assert len(candidates) == 1

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_direct_duplicate_insert_no_error(self, mock_title, mock_clean):
        """Directly inserting a duplicate via DB then calling add_candidate recovers."""
        create_or_update_card("hash1")

        # Pre-insert the candidate directly via session (bypassing add_candidate's check)
        with _session_scope() as session:
            candidate = Candidate(file_hash="hash1", family_name="Smith", method="ocr", confidence="high")
            session.add(candidate)
            session.flush()
            expected_id = candidate.id

        # add_candidate should find the existing one via its check-before-insert
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid == expected_id

        # Still only one candidate
        candidates = get_candidates("hash1")
        assert len(candidates) == 1

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_integrity_error_recovery(self, mock_title, mock_clean):
        """When a race causes IntegrityError on flush, add_candidate recovers."""
        create_or_update_card("hash1")

        # Pre-insert candidate directly (simulating another thread winning the race)
        with _session_scope() as session:
            candidate = Candidate(file_hash="hash1", family_name="Smith", method="ocr", confidence="high")
            session.add(candidate)
            session.flush()
            expected_id = candidate.id

        # Patch the existence check to return None (simulating TOCTOU race window)
        original_query = db_mod.Session.query
        check_count = [0]

        def query_interceptor(self, model, *args, **kwargs):
            result = original_query(self, model, *args, **kwargs)
            if model is Candidate:

                class WrappedQuery:
                    def __init__(self, real):
                        self._real = real

                    def __getattr__(self, name):
                        return getattr(self._real, name)

                    def filter_by(self, **kw):
                        real_result = self._real.filter_by(**kw)
                        # First Candidate filter_by with family_name is the existence check
                        if "family_name" in kw and check_count[0] == 0:
                            check_count[0] += 1

                            class EmptyResult:
                                def first(self):
                                    return None

                            return EmptyResult()
                        return real_result

                return WrappedQuery(result)
            return result

        with patch.object(db_mod.Session, "query", query_interceptor):
            cid = add_candidate("hash1", "Smith", "ocr", "high")

        # Should recover and return the existing candidate's ID
        assert cid == expected_id
        assert check_count[0] == 1  # Existence check was intercepted


class TestClearAIResultsFKOrdering:
    """Tests that clear_ai_results nulls FK before deleting candidates."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_no_dangling_fk_during_delete(self, mock_title, mock_clean):
        """selected_candidate_id is nulled before AI candidates are deleted."""
        create_or_update_card("hash1")
        ai_cid = add_candidate("hash1", "AiName", "ai", "high")
        select_candidate("hash1", ai_cid)

        # Track the order of operations
        operations = []
        original_flush = db_mod.Session.flush

        def tracking_flush(self, *args, **kwargs):
            # Check if any card has selected_candidate_id set to None
            for obj in self.dirty:
                if isinstance(obj, Card) and obj.selected_candidate_id is None:
                    operations.append("null_fk")
            return original_flush(self, *args, **kwargs)

        with patch.object(db_mod.Session, "flush", tracking_flush):
            clear_ai_results(["hash1"])

        # FK should have been nulled
        assert "null_fk" in operations

        # Final state should be correct
        state = get_card_state("hash1")
        assert state.method == "missing"


class TestAddCandidateInline:
    """Tests for _add_candidate_inline helper."""

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_adds_within_session(self, mock_title, mock_clean):
        """_add_candidate_inline adds candidate in the given session."""
        create_or_update_card("hash1")
        with _session_scope() as session:
            cid = _add_candidate_inline(session, "hash1", "Smith", "ocr", "high")
            assert cid > 0
        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].family_name == "Smith"

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=[])
    def test_filtered_name_returns_zero(self, mock_clean):
        """_add_candidate_inline returns 0 for filtered names."""
        create_or_update_card("hash1")
        with _session_scope() as session:
            cid = _add_candidate_inline(session, "hash1", "unknown", "ocr", "low")
            assert cid == 0

    @patch("app.core.family_name.clean_and_filter_family_names", return_value=["Smith"])
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_dedup_within_session(self, mock_title, mock_clean):
        """_add_candidate_inline deduplicates within the same session."""
        create_or_update_card("hash1")
        with _session_scope() as session:
            cid1 = _add_candidate_inline(session, "hash1", "Smith", "ocr", "high")
            cid2 = _add_candidate_inline(session, "hash1", "Smith", "ocr", "high")
            assert cid1 == cid2
        candidates = get_candidates("hash1")
        assert len(candidates) == 1


class TestReprocessSingleTransaction:
    """Tests that reprocess_candidates_from_raw uses a single transaction."""

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_clears_fk_before_deleting(self, mock_title, mock_clean):
        """selected_candidate_id is cleared before candidates are deleted."""
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "OldName", "ocr", "high")
        select_candidate("hash1", cid)
        save_raw_ocr("hash1", "The Smith Family")

        # Should not raise any FK errors
        reprocess_candidates_from_raw("hash1")

        # Old candidate should be gone, new ones from OCR should exist
        state = get_card_state("hash1")
        assert state is not None

    @patch("app.core.family_name.clean_and_filter_family_names", side_effect=lambda x: x)
    @patch("app.core.family_name.smart_title_case_family_name", side_effect=lambda x: x)
    def test_autoselects_best_after_reprocess(self, mock_title, mock_clean):
        """After reprocessing, the best candidate is auto-selected."""
        create_or_update_card("hash1")
        save_raw_ai("hash1", "AiBest", ["AiAlt"])

        reprocess_candidates_from_raw("hash1")

        state = get_card_state("hash1")
        # AI best should be auto-selected
        assert state.display_name == "AiBest"
        assert state.method == "ai"
        assert state.confidence == "high"
